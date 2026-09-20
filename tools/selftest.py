#!/usr/bin/env python3
"""不需網路、不需 API key 的自測：驗證 diff 解析、finding 正規化、Markdown 產生。

用法：python3 tools/selftest.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SAMPLE_DIFF = """diff --git a/src/handler.ts b/src/handler.ts
--- a/src/handler.ts
+++ b/src/handler.ts
@@ -10,6 +10,9 @@
   const user = req.user;
+  const id = req.query.id;
+  db.query("SELECT * FROM t WHERE id=" + id);
+  return user.name;
 }
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,2 +1,2 @@
 # Title
+new line
"""


def main() -> int:
    reviewer = load(".github/scripts/deepseek_review.py", "deepseek_review")
    poster = load(".github/scripts/post_review.py", "post_review")
    failures: list[str] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        if condition:
            print(f"  PASS  {label}")
        else:
            failures.append(label)
            print(f"  FAIL  {label}  {detail}")

    print("[1] parse_valid_lines：行號必須精準對到新增側")
    valid = poster.parse_valid_lines(SAMPLE_DIFF)
    check("新增行被辨識", valid.get("src/handler.ts") == {10, 11, 12, 13, 14}, valid)
    check("第二個檔案被辨識", valid.get("README.md") == {1, 2}, valid)

    print("[2] normalize：過濾壞資料、排序、補 verdict")
    result = reviewer.normalize(
        {
            "summary": "s",
            "findings": [
                {"path": "a.ts", "line": 3, "severity": "nit", "confidence": 0.5},
                {"path": "src/handler.ts", "line": 12, "severity": "blocker", "confidence": 0.9, "title": "SQLi", "body": "x"},
                {"path": "", "line": 1, "severity": "major", "confidence": 0.9},
                {"path": "x.ts", "line": "NaN", "severity": "major"},
            ],
        }
    )
    check("verdict 自動升級為 request_changes", result["verdict"] == "request_changes", result["verdict"])
    check("依嚴重度排序且壞資料被丟棄", [f["severity"] for f in result["findings"]] == ["blocker", "nit"], result["findings"])

    print("[3] extract_json：容忍 code fence 與前後綴")
    check("code fence", reviewer.extract_json('```json\n{"a":1}\n```') == {"a": 1})
    check("雜訊前後綴", reviewer.extract_json('好的：\n{"a": 2}\n以上。') == {"a": 2})

    print("[4] truncate：超大 diff 要在檔案邊界截斷")
    big, truncated = reviewer.truncate(SAMPLE_DIFF * 20, 1200)
    check("有標記截斷", truncated and "已被截斷" in big)
    check("保留整數個檔案區塊", big.count("diff --git") >= 2, big.count("diff --git"))

    print("[5] render_markdown：產出可貼的 Markdown")
    md = reviewer.render_markdown(
        result,
        {"number": 7, "base_ref": "main", "head_sha": "abc123"},
        "deepseek-flash",
        {"prompt_tokens": 10, "completion_tokens": 5, "prompt_cache_hit_tokens": 8},
        True,
    )
    check("含標記註解", "<!-- deepseek-review -->" in md)
    check("含嚴重度與模型資訊", "Blocker" in md and "deepseek-flash" in md)

    print("[6] post_review 過濾：不在 diff 行號內的 finding 必須被跳過")
    candidates = [
        {"path": "src/handler.ts", "line": 12},
        {"path": "src/handler.ts", "line": 999},
    ]
    selected = [f for f in candidates if f["line"] in valid.get(f["path"], set())]
    check("只留下合法行號", len(selected) == 1 and selected[0]["line"] == 12, selected)

    print("[7] existing_inline_keys：gh 失敗要回 None，不能回空集合")
    # 為什麼這條值得一個測試：前一版用 `gh(check=False)` 配 `except RuntimeError`，
    # 而 check=False 失敗時只 log warning、不拋例外——那個 except 是死碼。
    # 結果 gh 一失敗就回空集合，呼叫端讀成「一則都沒貼過」，每次 push 重貼一輪。
    # 空集合與 None 必須是兩種語意：前者是「查到了，沒有」，後者是「查不到」。
    original_gh = poster.gh
    try:
        poster.gh = lambda args, check=True: (_ for _ in ()).throw(
            RuntimeError("gh api 失敗：HTTP 403")
        )
        check("gh 失敗回 None", poster.existing_inline_keys("o/r", "1") is None)

        poster.gh = lambda args, check=True: ""
        check(
            "gh 成功但無結果回空集合",
            poster.existing_inline_keys("o/r", "1") == set(),
        )

        poster.gh = lambda args, check=True: "src/a.ts:12\nsrc/b.ts:7\n"
        check(
            "gh 成功時正確解析 path:line",
            poster.existing_inline_keys("o/r", "1") == {("src/a.ts", 12), ("src/b.ts", 7)},
        )
    finally:
        poster.gh = original_gh

    print("[8] 貼摘要的 `gh pr review` 必須帶 --repo")
    # 為什麼值得一個測試：`gh pr` 子命令靠**當前目錄的 git remote** 推斷 repo。
    # 走 reusable workflow 時 kit 被 checkout 到 `.kit` 子目錄，工作目錄根沒有 git repo，
    # 少了 --repo 就會 `fatal: not a git repository`——而 check=False 把它吞掉，
    # 結果是摘要一則都沒貼、job 卻回報 success（2026-09-21 在 PR #5 實際踩到）。
    #
    # ⚠️ 這是**靜態檢查**不是行為測試：它只確認呼叫參數裡有 --repo，
    # 擋的是「有人重構時把它拿掉」這種回歸，擋不了 args.repo 傳錯值。
    src = (ROOT / ".github/scripts/post_review.py").read_text(encoding="utf-8")
    m = re.search(r'\[\s*"pr",\s*"review".*?\]', src, re.S)
    check("原始碼中找得到 gh pr review 的呼叫", m is not None)
    if m:
        check("該呼叫帶 --repo", '"--repo"' in m.group(0), m.group(0)[:120])

    print()
    if failures:
        print(f"FAILED: {len(failures)} 項 -> {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
