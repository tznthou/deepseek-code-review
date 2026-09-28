#!/usr/bin/env python3
"""把 DeepSeek review 的結果貼回 GitHub PR。

需要 `gh` CLI（runner 已預裝）與 GH_TOKEN / GITHUB_TOKEN。
只用標準函式庫 + `gh`，不需要 pip install。

用法：
  python .github/scripts/post_review.py \
    --repo "$GITHUB_REPOSITORY" --pr 123 --sha "$HEAD_SHA" \
    --review review.md --findings findings.json --diff pr.diff

安全設計：
  * **行號由程式算，不信模型報的**：先用 `locate.resolve_line` 拿 finding 引用的
    程式碼片段去 diff 裡做文字比對定位；定不到才退回模型自己報的行號。
    2026-09-21 對八次真實 review 的 artifact 實測（n=16），模型報的行號只有 1 筆
    真的指向它 evidence 引用的那段 code，其餘偏移 +1 到 +24 行。詳見 locate.py。
  * **再驗證行號**：只有落在 diff hunk 內的新增側行號才會貼 inline comment，
    否則 GitHub API 會回 422。驗證失敗的 finding 會被降級寫進 summary。
  * **冪等只做在 inline comment**：比對既有帶 `<!-- deepseek-review -->` 標記的留言，
    同一個 `(path, line)` 不重貼。摘要用 `gh pr review --comment`，每次執行都新建一則 review。
  * **不 gating**：預設只留 COMMENT review，不送 REQUEST_CHANGES，
    避免模型（或 prompt injection）取得擋 merge 的能力。要開啟請用 --request-changes-on-blocker。
  * **行內留言可以關掉**：`--no-inline` 只貼摘要（review.md 本身就有完整的 Findings 表）。
    定位、門檻與 --request-changes-on-blocker 的判斷照舊，只是不查既有留言、不貼 inline。
    reusable workflow 的 `inline-comments` 預設 false 時會帶這個參數；直接呼叫本腳本時預設照舊貼。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locate  # noqa: E402  （同目錄模組，必須在 sys.path 調整之後 import）

SEVERITY_RANK = {"nit": 0, "minor": 1, "major": 2, "blocker": 3}
MARKER = "deepseek-review"
# 規範那次呼叫的 finding 落在一般 finding 的同檔 ±3 行內，就併進那則留言（跟評估時的位置命中同一個寬度）
MERGE_WINDOW = 3


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


def inline_body(finding: dict) -> str:
    """一則 inline comment 的內文。一般 finding（沒有規範相關欄位）的格式跟 v1.4.1 逐字相同。"""
    body = f"<!-- {MARKER} -->\n**{finding['severity'].upper()}** — {finding['title']}\n\n{finding['body']}\n\n"
    for extra in finding.get("merged_rules", []):
        body += (
            f"---\n\n**同一處也違反 repo 規範 {extra['rule']}**（{extra.get('rule_text', '')}）"
            f"— {extra['title']}\n\n{extra['body']}\n\n"
        )
    if finding.get("rule"):
        body += f"<sub>違反 repo 規範 {finding['rule']}：{finding.get('rule_text', '')} ｜ "
        body += f"confidence {finding['confidence']:.2f} ｜ DeepSeek automated review</sub>"
    else:
        body += f"<sub>confidence {finding['confidence']:.2f} ｜ DeepSeek automated review</sub>"
    return body


def post_inline(repo: str, pr: str, sha: str, finding: dict) -> bool:
    body = inline_body(finding)
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
    p.add_argument(
        "--no-inline",
        action="store_true",
        help="只貼摘要、不貼行內留言；定位、門檻與 blocker 的判斷照舊",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rules-findings", default=None, help="repo 規範那次呼叫的 findings JSON（選填）")
    p.add_argument(
        "--rules-status",
        default="",
        help="規範那次呼叫的結果（workflow 傳 steps.<id>.outcome）。空字串或 skipped＝沒設規範檔，完全走原本的路徑",
    )
    return p.parse_args()


def load_findings(path: str | None) -> list[dict]:
    try:
        with open(path or "", "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def select_inline(
    findings: list[dict],
    min_rank: int,
    min_confidence: float,
    min_severity: str,
    valid: dict[str, set[int]],
    index: dict[str, dict[int, str]],
) -> tuple[list[dict], list[tuple[dict, str]], int]:
    """過濾出可以貼成 inline 的 finding，回傳 (要貼的, [(沒貼的, 原因)], 重新定位的筆數)。"""
    selected: list[dict] = []
    skipped: list[tuple[dict, str]] = []
    relocated = 0
    for f in findings:
        if SEVERITY_RANK.get(f.get("severity", "nit"), 0) < min_rank:
            skipped.append((f, f"嚴重度 {f.get('severity')} 未達 {min_severity}"))
            continue
        if float(f.get("confidence", 0)) < min_confidence:
            skipped.append((f, f"信心 {float(f.get('confidence', 0)):.2f} < {min_confidence}"))
            continue
        if index:
            # 片段優先、模型行號其次。resolve_line 可能改寫 f["path"]（跨檔命中），
            # 所以底下的 valid 檢查一定要在這之後、用改寫後的 path。
            model_line = f.get("line")
            resolved, how = locate.resolve_line(f, index)
            if resolved is None:
                skipped.append((f, how))
                continue
            if resolved != model_line:
                log(f"[info] 重新定位 {f['path']}:{model_line} → {resolved}（{how}）")
                f["line"] = resolved
                relocated += 1
        allowed = valid.get(f["path"])
        if valid and (allowed is None or f["line"] not in allowed):
            skipped.append((f, "行號不在 diff 可留言範圍內"))
            continue
        selected.append(f)
    return selected, skipped, relocated


def merge_into(selected: list[dict], rules_selected: list[dict]) -> list[dict]:
    """跨 pass 同位置合併：規範 finding 落在某則一般 finding 的同檔 ±3 行內，就併進那則留言。
    回傳沒被合併、要單獨貼的規範 finding。

    只合併跨 pass 的：一般那次自己的同位置 finding 照舊各貼各的（通用合併會改到所有 caller）。
    兩邊都已經過了行內門檻，低信心的規範 finding 不會搭著一般 finding 的留言貼出去。
    """
    standalone: list[dict] = []
    for extra in rules_selected:
        near = [
            f
            for f in selected
            if f["path"] == extra["path"] and abs(f["line"] - extra["line"]) <= MERGE_WINDOW
        ]
        if near:
            host = min(near, key=lambda f: abs(f["line"] - extra["line"]))
            host.setdefault("merged_rules", []).append(extra)
        else:
            standalone.append(extra)
    return standalone


def render_rules_section(findings: list[dict], ok: bool) -> str:
    """摘要裡「repo 規範」那一段。規範那次呼叫自己的 review.md 不拿來貼：那是模型對那次呼叫的
    結論，而且列的是過濾前的 finding。"""
    if not ok:
        return "\n\n### repo 規範\n\n> ⚠️ 規範那次呼叫沒有成功（原因在 workflow log），這次只有一般 review。\n"
    if not findings:
        return "\n\n### repo 規範\n\n這次沒有標了規範編號的 finding。\n"
    lines = [
        f"\n\n### 違反 repo 規範（{len(findings)} 筆）\n",
        "| 位置 | 規範 | 問題 | 信心 |",
        "|---|---|---|---|",
    ]
    for f in findings:
        title = str(f.get("title") or "")[:90].replace("|", "\\|")
        lines.append(
            f"| `{f.get('path')}:{f.get('line')}` | {f.get('rule', '')} | {title} "
            f"| {float(f.get('confidence', 0)):.2f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()

    if not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"):
        log("[error] 缺少 GH_TOKEN / GITHUB_TOKEN")
        return 1

    with open(args.review, "r", encoding="utf-8") as fh:
        review_body = fh.read()
    findings = load_findings(args.findings)

    valid: dict[str, set[int]] = {}
    index: dict[str, dict[int, str]] = {}
    if args.diff and os.path.exists(args.diff):
        with open(args.diff, "r", encoding="utf-8", errors="replace") as fh:
            diff_text = fh.read()
        valid = parse_valid_lines(diff_text)
        index = locate.index_diff(diff_text)

    min_rank = SEVERITY_RANK[args.min_severity]
    selected, skipped, relocated = select_inline(
        findings, min_rank, args.min_confidence, args.min_severity, valid, index
    )

    # repo 規範那次呼叫（opt-in）。沒設規範檔的 caller 不會進到這裡，輸出跟 v1.4.1 逐字相同
    # （tools/fixtures/post_review_golden.json 釘住）。
    # `skipped`＝沒設規範檔（那一步的 if 沒過）；其餘都算有設，不是 success 就註明沒成功
    # （被 timeout-minutes 砍掉時 outcome 可能是 cancelled，不能當成沒設）。
    if args.rules_status not in ("", "skipped"):
        rules_ok = args.rules_status == "success"
        rules_findings = load_findings(args.rules_findings) if rules_ok else []
        rules_selected, rules_skipped, rules_relocated = select_inline(
            rules_findings, min_rank, args.min_confidence, args.min_severity, valid, index
        )
        standalone = merge_into(selected, rules_selected)
        if standalone:
            # 兩邊合起來照嚴重度、信心排，上限才不會固定犧牲規範那一邊。沒有要單獨貼的就不排：
            # 規範那次失敗或全部併掉時，一般 review 的 inline 要跟沒開規範檔時一模一樣。
            selected = sorted(
                selected + standalone,
                key=lambda f: (-SEVERITY_RANK.get(f.get("severity", "nit"), 0), -float(f.get("confidence", 0))),
            )
        skipped += rules_skipped
        relocated += rules_relocated
        review_body += render_rules_section(rules_findings, rules_ok)
        log(
            f"[info] 規範那次呼叫：status={args.rules_status} findings={len(rules_findings)} "
            f"inline={len(rules_selected)} merged={len(rules_selected) - len(standalone)} "
            f"skipped={len(rules_skipped)}"
        )

    selected = selected[: args.max_inline]
    # 這幾個數字要印出來：dogfood 那次 bug（2026-09-21 PR #5）的症狀正是
    # 「每個 step 都 success、review.md 完整、PR 上零留言」，當時 log 裡沒有
    # 任何一個數字能揭穿它。
    log(
        f"[info] findings={len(findings)} inline={'off' if args.no_inline else len(selected)} "
        f"skipped={len(skipped)} relocated={relocated}"
    )

    # --no-inline 時不附這一段：review.md 的 Findings 表已經列出全部 finding
    if skipped and not args.no_inline:
        review_body += "\n\n### 未張貼為 inline 的 finding\n\n"
        for f, reason in skipped:
            review_body += (
                f"- `{f['path']}:{f['line']}` **{f['severity']}** — {f['title']}"
                f"（{reason}）\n"
            )

    # 要貼成行內留言的；--no-inline 時是空的。selected 本身留著給底下的 blocker 判斷用
    to_post = [] if args.no_inline else selected

    if args.dry_run:
        print(review_body)
        print(json.dumps(to_post, ensure_ascii=False, indent=2))
        return 0

    # 1) 摘要留言：每次執行都新建一則 review（冪等只做在下面的 inline comment）
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
    posted = 0
    if args.no_inline:
        log("[info] inline 關閉（--no-inline）：只貼摘要，不查既有留言")
        already = set()
    else:
        already = existing_inline_keys(args.repo, args.pr) if args.diff else set()
    if already is None:
        # 冪等性檢查失敗。寧可不貼也不要重複貼——摘要已經在上面貼了，
        # 資訊不會遺失，而重複的 inline comment 得由人工一則一則刪。
        log("[warn] 冪等性檢查失敗，本次跳過所有 inline comment（摘要不受影響）")
    else:
        for f in to_post:
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
