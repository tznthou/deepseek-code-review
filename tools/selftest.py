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

    print("[9] locate：行號要由片段文字比對算出來，不能照抄模型報的")
    # 為什麼值得一組測試：2026-09-21 拿八次真實 review 的 artifact 實測（n=16），
    # 模型報的行號只有 1 筆真的指向它自己 evidence 引用的那段 code，
    # 其餘 15 筆偏移 +1 到 +24 行。最誇張的一筆，evidence 明寫
    # 「第 48 行：`BASE='...base.sha'`」，而那行實際在 55。
    locator = load(".github/scripts/locate.py", "locate")
    index = locator.index_diff(SAMPLE_DIFF)
    check(
        "index_diff 留下行內容而不只是行號",
        index.get("src/handler.ts", {}).get(12) == '  db.query("SELECT * FROM t WHERE id=" + id);',
        index.get("src/handler.ts", {}).get(12),
    )

    # 模型把行號報錯（說 10，實際在 12），片段唯一命中要把它拉回來。
    drifted = {
        "path": "src/handler.ts",
        "line": 10,
        "existing_code": 'db.query("SELECT * FROM t WHERE id=" + id);',
    }
    line, how = locator.resolve_line(drifted, index)
    check("片段唯一命中時修正錯誤行號", line == 12, f"{line} / {how}")

    # 片段在該檔找不到 → 退回模型行號，不要自己猜一個。
    missing = {"path": "src/handler.ts", "line": 12, "existing_code": "this_string_is_not_in_the_diff_at_all()"}
    line, how = locator.resolve_line(missing, index)
    check("片段定不到時退回模型行號", line == 12 and "退回模型行號" in how, f"{line} / {how}")

    # 片段與模型行號都定不到 → 誠實回 None，交給呼叫端降級。
    hopeless = {"path": "src/handler.ts", "line": 999, "existing_code": "still_not_here_either()"}
    line, how = locator.resolve_line(hopeless, index)
    check("兩者都定不到時回 None", line is None, f"{line} / {how}")

    # 多重命中一律不猜：挑一個等於拿錯位置換錯位置。
    dup_diff = SAMPLE_DIFF.replace("+  return user.name;", "+  return user.name;\n+  const id = req.query.id;")
    dup_index = locator.index_diff(dup_diff)
    ambiguous = {"path": "src/handler.ts", "line": 999, "existing_code": "const id = req.query.id;"}
    line, how = locator.resolve_line(ambiguous, dup_index)
    check("多重命中時拒絕定位", line is None and "多重命中" in how, f"{line} / {how}")

    # finding 掛錯檔案但內容引對了 → 跨檔唯一命中要改寫 path。
    wrong_file = {"path": "README.md", "line": 1, "existing_code": 'db.query("SELECT * FROM t WHERE id=" + id);'}
    line, how = locator.resolve_line(wrong_file, index)
    check(
        "跨檔唯一命中時改寫 path",
        line == 12 and wrong_file["path"] == "src/handler.ts",
        f"{line} / {wrong_file['path']} / {how}",
    )

    # 太短的片段不拿來定位（`}`、`fi` 這類到處都命中）。
    check("過短的片段被忽略", locator.extract_snippets("`fi`", "`}`") == [], locator.extract_snippets("`fi`", "`}`"))

    # 摘要表格與 inline comment 必須指同一個位置。定位若放在下游的 post_review，
    # inline 會貼在修正後的行、而 review.md 還印著模型原本報的行號——
    # 兩邊對不起來，讀的人會以為系統壞了。所以定位在產 markdown 之前做。
    drift_result = {
        "summary": "s",
        "verdict": "comment",
        "findings": [
            {
                "path": "src/handler.ts",
                "line": 10,
                "side": "RIGHT",
                "severity": "blocker",
                "confidence": 0.9,
                "title": "SQLi",
                "body": "x",
                "existing_code": 'db.query("SELECT * FROM t WHERE id=" + id);',
                "evidence": "",
            }
        ],
    }
    for fnd in drift_result["findings"]:
        resolved, _ = locator.resolve_line(fnd, index)
        if resolved is not None:
            fnd["line"] = resolved
    md_after = reviewer.render_markdown(
        drift_result, {"number": 7, "base_ref": "main", "head_sha": "abc"}, "m", {}, False
    )
    check("摘要用的是修正後的行號", "src/handler.ts:12" in md_after, md_after[:0])
    check("摘要不再出現模型報錯的行號", "src/handler.ts:10" not in md_after, md_after[:0])

    print("[10] apply_filter：只刪 diff 能當場證偽的，其餘一律 fail-open")
    # 這一層只會讓 finding 消失、不會讓它出現，所以每一條異常路徑都必須是「不刪」。
    # 留下一筆該刪的，讀的人自己會判斷；刪掉一筆該留的，他連看都看不到。
    FIND = [
        {"path": "src/handler.ts", "line": 11, "severity": "minor", "title": "A", "body": "",
         "existing_code": "const id = req.query.id;", "evidence": ""},
        {"path": "src/handler.ts", "line": 12, "severity": "major", "title": "B", "body": "",
         "existing_code": 'db.query("SELECT', "evidence": ""},
    ]
    orig_chat = reviewer.chat_completion

    def fake_chat(payload_json):
        def _f(base_url, api_key, payload, timeout, retries):
            return {"choices": [{"message": {"content": payload_json}}], "usage": {}}
        return _f

    def run_filter():
        return reviewer.apply_filter(
            [dict(f) for f in FIND], SAMPLE_DIFF, "filter prompt",
            "http://x", "k", "m", 5, 0, "disabled",
        )

    try:
        # 正常刪除：反證行真的在 diff 裡
        reviewer.chat_completion = fake_chat(
            '{"remove":[{"index":0,"contradicting_line":"const id = req.query.id;","reason":"r"}]}')
        kept, removed, _ = run_filter()
        check("反證行在 diff 裡時正常刪除", len(kept) == 1 and len(removed) == 1 and kept[0]["title"] == "B",
              [f["title"] for f in kept])

        # 幻覺防線：模型宣稱的反證行根本不在 diff 裡
        reviewer.chat_completion = fake_chat(
            '{"remove":[{"index":0,"contradicting_line":"this_line_does_not_exist();","reason":"r"}]}')
        kept, removed, _ = run_filter()
        check("反證行不在 diff 裡時拒絕刪除", len(kept) == 2 and not removed, len(kept))

        # 縮排／空白有出入仍要視為同一行。兩邊比對邏輯若分岔（一邊正規化、一邊沒有），
        # filter 會因為對不上而永遠不刪，且不報錯——靜默失效。
        reviewer.chat_completion = fake_chat(
            '{"remove":[{"index":0,"contradicting_line":"const    id   =  req.query.id;","reason":"r"}]}')
        kept, removed, _ = run_filter()
        check("反證行只有空白差異時仍認得出來", len(kept) == 1 and len(removed) == 1, len(kept))

        # index 超出範圍
        reviewer.chat_completion = fake_chat(
            '{"remove":[{"index":99,"contradicting_line":"const id = req.query.id;","reason":"r"}]}')
        kept, _, _ = run_filter()
        check("index 超出範圍時不刪", len(kept) == 2, len(kept))

        # 空 remove（最常見的正確答案）
        reviewer.chat_completion = fake_chat('{"remove":[]}')
        kept, removed, _ = run_filter()
        check("remove 為空時全部保留", len(kept) == 2 and not removed, len(kept))

        # API 失敗
        def boom(*a, **k):
            raise RuntimeError("HTTP 500")
        reviewer.chat_completion = boom
        kept, removed, _ = run_filter()
        check("API 失敗時全部保留", len(kept) == 2 and not removed, len(kept))

        # 回傳不是 JSON
        reviewer.chat_completion = fake_chat("對不起，我不知道")
        kept, _, _ = run_filter()
        check("回傳無法解析時全部保留", len(kept) == 2, len(kept))
    finally:
        reviewer.chat_completion = orig_chat

    # 被刪掉的要在 review.md 留下痕跡，否則讀的人分不出「沒報」與「被吃掉」
    md_f = reviewer.render_markdown(
        {"summary": "s", "verdict": "comment", "findings": []},
        {"number": 1, "base_ref": "main", "head_sha": "a"}, "m", {}, False,
        [({"path": "a.ts", "line": 3, "severity": "minor", "title": "被刪的"}, "理由X")],
    )
    check("被 filter 刪掉的有列進 review.md", "被刪的" in md_f and "理由X" in md_f)
    check("過濾區塊是收合的", "<details>" in md_f or "<details><summary>" in md_f)

    print("[11] select_rules：依 diff 的檔案型態挑補充規則")
    RULES = ROOT / "prompts/rules"
    text, used = reviewer.select_rules(SAMPLE_DIFF, str(RULES))
    check("純 ts/markdown 的 diff 不套任何補充規則", used == [], used)

    wf_diff = "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n+  run: echo hi\n"
    text, used = reviewer.select_rules(wf_diff, str(RULES))
    check("workflow 檔案套到 github-workflows.md", used == ["github-workflows.md"], used)
    check("規則內容真的被讀進來", "pull_request_target" in text, len(text))

    py_diff = "diff --git a/tools/x.py b/tools/x.py\n+import os\n"
    text, used = reviewer.select_rules(py_diff, str(RULES))
    check("py 檔案套到 python.md", used == ["python.md"], used)

    both = wf_diff + py_diff
    text, used = reviewer.select_rules(both, str(RULES))
    check("混合 diff 兩份都套且不重複", used == ["github-workflows.md", "python.md"], used)

    # 一般 YAML 不該吃到 workflow 規則——順序敏感，RULE_MAP 靠 pattern 而非副檔名
    plain_yaml = "diff --git a/config/app.yml b/config/app.yml\n+key: v\n"
    _, used = reviewer.select_rules(plain_yaml, str(RULES))
    check("非 workflow 的 yml 不套 workflow 規則", used == [], used)

    _, used = reviewer.select_rules(wf_diff, "/nonexistent/dir")
    check("規則目錄不存在時安靜跳過", used == [], used)

    # 補充規則是 prompt，裡面不能有寫給人看的元評論——那會進到模型的輸入裡
    for rf in sorted(RULES.glob("*.md")):
        body = rf.read_text(encoding="utf-8")
        check(
            f"{rf.name} 沒有元評論標記",
            not re.search(r"(實測無效|待驗證|TODO|FIXME|這條沒用|先留著)", body),
            rf.name,
        )

    print()
    if failures:
        print(f"FAILED: {len(failures)} 項 -> {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
