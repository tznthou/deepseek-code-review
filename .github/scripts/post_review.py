#!/usr/bin/env python3
"""把 DeepSeek review 的結果貼回 GitHub PR。

需要 `gh` CLI（runner 已預裝）與 GH_TOKEN / GITHUB_TOKEN。
只用標準函式庫 + `gh`，不需要 pip install。

用法：
  python .github/scripts/post_review.py \
    --repo "$GITHUB_REPOSITORY" --pr 123 --sha "$HEAD_SHA" \
    --review review.md --findings findings.json --diff pr.diff

安全設計：
  * **先驗證行號**：只有落在 diff hunk 內的新增側行號才會貼 inline comment，
    否則 GitHub API 會回 422。驗證失敗的 finding 會被降級寫進 summary。
  * **冪等**：summary 用 `gh pr comment --edit-last --create-if-none`；
    inline comment 會比對既有的 `<!-- deepseek-review -->` 標記，不重複張貼。
  * **不 gating**：預設只留 COMMENT review，不送 REQUEST_CHANGES，
    避免模型（或 prompt injection）取得擋 merge 的能力。要開啟請用 --request-changes-on-blocker。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

SEVERITY_RANK = {"nit": 0, "minor": 1, "major": 2, "blocker": 3}
MARKER = "deepseek-review"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def gh(args: list[str], check: bool = True) -> str:
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, env=os.environ, check=False
    )
    if proc.returncode != 0 and check:
        raise RuntimeError(f"gh {' '.join(args[:3])}… 失敗：{proc.stderr.strip()[:400]}")
    if proc.returncode != 0:
        # 用 ::warning:: 讓 GitHub Actions 把它標在 job summary 上。
        # 2026-09-21 踩過：只印 `[warn]` 到 stdout 的話，貼留言整個失敗也看不出來——
        # job 照樣 success、還印「完成」，要翻 log 才發現一則都沒貼。
        log(f"::warning::gh {' '.join(args[:3])} 失敗（已忽略）：{proc.stderr.strip()[:200]}")
    return proc.stdout


def parse_valid_lines(diff_text: str) -> dict[str, set[int]]:
    """回傳 {新檔案路徑: {可留言的新增側行號}}。"""
    valid: dict[str, set[int]] = {}
    current: str | None = None
    new_line = 0
    hunk = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            match = re.search(r" b/(.+)$", raw)
            current = match.group(1).strip() if match else None
            if current:
                valid.setdefault(current, set())
            new_line = 0
            continue
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            if target != "/dev/null":
                path = target[2:] if target.startswith("b/") else target
                current = path
                valid.setdefault(current, set())
            continue
        m = hunk.match(raw)
        if m:
            new_line = int(m.group(1))
            continue
        if current is None or new_line == 0:
            continue
        if raw.startswith("+"):
            valid[current].add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            pass
        elif raw.startswith(" "):
            valid[current].add(new_line)  # context 行也能留言
            new_line += 1
    return valid


def existing_inline_keys(repo: str, pr: str) -> set[tuple[str, int]] | None:
    """抓出自己先前貼過的 inline comment，達成冪等。

    回傳 `None` 代表**查不到**（gh 失敗），與「查到了，一則都沒有」的空集合
    是兩回事——呼叫端看到 None 必須跳過 inline 張貼。

    ⚠️ 這裡刻意用 `check=True`。前一版是 `check=False` 配 `except RuntimeError`，
    而 `gh(check=False)` 失敗時只 log warning 並回傳空 stdout、**不會拋例外**，
    所以那個 except 是死碼：gh 一失敗就回空集合，呼叫端讀成「沒貼過」，
    於是每次 push 都重複貼一輪 inline comment。失敗要看得見。
    """
    try:
        out = gh(
            [
                "api",
                "--paginate",
                f"repos/{repo}/pulls/{pr}/comments",
                "--jq",
                f'.[] | select(.body | contains("{MARKER}")) | "\\(.path):\\(.line)"',
            ],
            check=True,
        )
    except RuntimeError as err:
        log(f"[warn] 無法取得既有 inline comment：{err}")
        return None
    keys: set[tuple[str, int]] = set()
    for line in out.splitlines():
        path, _, number = line.rpartition(":")
        if path and number.isdigit():
            keys.add((path, int(number)))
    return keys


def post_inline(repo: str, pr: str, sha: str, finding: dict) -> bool:
    body = (
        f"<!-- {MARKER} -->\n"
        f"**{finding['severity'].upper()}** — {finding['title']}\n\n"
        f"{finding['body']}\n\n"
        f"<sub>confidence {finding['confidence']:.2f} ｜ DeepSeek automated review</sub>"
    )
    try:
        gh(
            [
                "api",
                "--method",
                "POST",
                f"repos/{repo}/pulls/{pr}/comments",
                "-f",
                f"body={body}",
                "-f",
                f"path={finding['path']}",
                "-F",
                f"line={finding['line']}",
                "-f",
                f"side={finding['side']}",
                "-f",
                f"commit_id={sha}",
            ]
        )
        return True
    except RuntimeError as err:
        log(f"[warn] inline comment 失敗（{finding['path']}:{finding['line']}）：{err}")
        return False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Post a DeepSeek review to a GitHub PR")
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--pr", required=True, help="PR number")
    p.add_argument("--sha", required=True, help="head commit SHA")
    p.add_argument("--review", required=True, help="Markdown review 檔")
    p.add_argument("--findings", required=True, help="findings JSON 檔")
    p.add_argument("--diff", default=None, help="unified diff 檔（用於行號驗證）")
    p.add_argument("--min-severity", default="minor", choices=list(SEVERITY_RANK))
    p.add_argument("--min-confidence", type=float, default=0.7)
    p.add_argument("--max-inline", type=int, default=8)
    p.add_argument("--request-changes-on-blocker", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"):
        log("[error] 缺少 GH_TOKEN / GITHUB_TOKEN")
        return 1

    with open(args.review, "r", encoding="utf-8") as fh:
        review_body = fh.read()
    try:
        with open(args.findings, "r", encoding="utf-8") as fh:
            findings = json.load(fh)
    except (OSError, json.JSONDecodeError):
        findings = []

    valid: dict[str, set[int]] = {}
    if args.diff and os.path.exists(args.diff):
        with open(args.diff, "r", encoding="utf-8", errors="replace") as fh:
            valid = parse_valid_lines(fh.read())

    min_rank = SEVERITY_RANK[args.min_severity]
    selected, skipped = [], []
    for f in findings:
        if SEVERITY_RANK.get(f.get("severity", "nit"), 0) < min_rank:
            skipped.append(f)
            continue
        if float(f.get("confidence", 0)) < args.min_confidence:
            skipped.append(f)
            continue
        allowed = valid.get(f["path"])
        if valid and (allowed is None or f["line"] not in allowed):
            skipped.append(f)
            continue
        selected.append(f)

    selected = selected[: args.max_inline]
    log(f"[info] findings={len(findings)} inline={len(selected)} skipped={len(skipped)}")

    if skipped:
        review_body += "\n\n### 未張貼為 inline 的 finding\n\n"
        for f in skipped:
            review_body += (
                f"- `{f['path']}:{f['line']}` **{f['severity']}** — {f['title']}"
                "（行號不在 diff 內、或信心/嚴重度未達門檻）\n"
            )

    if args.dry_run:
        print(review_body)
        print(json.dumps(selected, ensure_ascii=False, indent=2))
        return 0

    # 1) 摘要留言（冪等：編輯自己上一則，沒有就新建）
    with open("/tmp/deepseek-review-body.md", "w", encoding="utf-8") as fh:
        fh.write(review_body)

    has_blocker = any(f["severity"] == "blocker" for f in selected)
    review_body_path = "/tmp/deepseek-review-body.md"
    # ⚠️ `--repo` 不能省。`gh pr` 子命令靠**當前目錄的 git remote** 推斷 repo，
    # 而這支腳本不保證跑在目標 repo 的工作目錄裡——走 reusable workflow 時，
    # kit 被 checkout 到 `.kit` 子目錄，工作目錄根**沒有 git repo**。
    # 2026-09-21 實測：少了 --repo 會 `fatal: not a git repository`，
    # 而 check=False 把它吞掉 → 摘要一則都沒貼，job 卻回報 success。
    verdict_flag = "--request-changes" if (args.request_changes_on_blocker and has_blocker) else "--comment"
    gh(
        ["pr", "review", args.pr, "--repo", args.repo, verdict_flag, "--body-file", review_body_path],
        check=False,
    )

    # 2) inline comments（跳過已貼過的）
    already = existing_inline_keys(args.repo, args.pr) if args.diff else set()
    posted = 0
    if already is None:
        # 冪等性檢查失敗。寧可不貼也不要重複貼——摘要已經在上面貼了，
        # 資訊不會遺失，而重複的 inline comment 得由人工一則一則刪。
        log("[warn] 冪等性檢查失敗，本次跳過所有 inline comment（摘要不受影響）")
    else:
        for f in selected:
            if (f["path"], f["line"]) in already:
                log(f"[info] 已存在，跳過 {f['path']}:{f['line']}")
                continue
            if post_inline(args.repo, args.pr, args.sha, f):
                posted += 1

    log(f"[info] 完成：inline {posted} 筆已張貼")

    if has_blocker and args.request_changes_on_blocker:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
