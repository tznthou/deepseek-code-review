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

    # ⚠️ 紅綠對照：existing_code 是整段程式碼，而程式碼的 docstring／註解裡含反引號
    # 是完全正常的。舊版把 existing_code 與 evidence 走同一條路徑，看到反引號就去挖
    # 裡面的內容當片段 → 拿 `helper.func` 比對，命中了 docstring 裡提到它的那一行，
    # 而不是這段程式碼的開頭。2026-09-21 在真實 PR 上實際錯位 3 行。
    backtick_diff = (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -1,0 +1,5 @@\n"
        "+def normalize_ws(text):\n"
        '+    """壓縮空白。\n'
        "+\n"
        "+    公開的原因：`helper.func` 驗證時要用同一套正規化。\n"
        '+    """\n'
    )
    bt_index = locator.index_diff(backtick_diff)
    code_with_backticks = (
        'def normalize_ws(text):\n    """壓縮空白。\n\n    公開的原因：`helper.func` 驗證時要用同一套正規化。\n    """'
    )
    check(
        "literal_snippets 不挖反引號，整段當一個片段",
        locator.literal_snippets(code_with_backticks) == [code_with_backticks],
        locator.literal_snippets(code_with_backticks),
    )
    bt_finding = {"path": "m.py", "line": 1, "existing_code": code_with_backticks}
    line, how = locator.resolve_line(bt_finding, bt_index)
    check("含反引號的整段程式碼定位到它的第一行", line == 1, f"{line} / {how}")
    # 對照組：同樣內容放在 evidence（散文欄位）才該挖反引號
    check(
        "散文欄位仍然挖反引號",
        "helper.func" in locator.extract_snippets("依據：`helper.func` 這個呼叫"),
        locator.extract_snippets("依據：`helper.func` 這個呼叫"),
    )

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

    print("[10] select_rules：依 diff 的檔案型態挑補充規則")
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

    print("[11] truncation_error：輸出被 max_tokens 砍斷要講實話，不要讓它偽裝成解析失敗")
    check(
        "正常結束不報錯",
        reviewer.truncation_error("stop", '{"summary":"x"}', 8192, "disabled") is None,
    )
    check(
        "沒有 finish_reason 不報錯",
        reviewer.truncation_error(None, '{"summary":"x"}', 8192, "disabled") is None,
    )
    cut = reviewer.truncation_error("length", '{"summary":"半截', 8192, "disabled")
    check("截斷時回傳訊息", cut is not None, cut)
    check("訊息點出 max_tokens 與數值", cut is not None and "max_tokens=8192" in cut, cut)
    check("訊息給的是調高額度的指示", cut is not None and "--max-tokens" in cut, cut)
    # thinking 開啟時 reasoning tokens 與輸出共用額度，content 會是空字串——
    # 同樣是 finish_reason=length，但要修的地方不一樣。
    empty = reviewer.truncation_error("length", "", 8192, "high")
    check(
        "thinking 吃光額度時指向 thinking 而不是 max_tokens",
        empty is not None and "--thinking disabled" in empty,
        empty,
    )
    check(
        "thinking=disabled 但內容空白時仍走一般訊息",
        (reviewer.truncation_error("length", "", 8192, "disabled") or "").find("--max-tokens") != -1,
    )
    # 2026-09-19 實測：max-tokens 給到 32768 仍被 reasoning 吃光（用掉 31408），
    # 而那次 content 是有東西的。只按「content 空不空」分流會在這裡給錯建議。
    partial = reviewer.truncation_error("length", '{"summary":"半截', 8192, "high")
    check(
        "thinking 開著且已有部分輸出時仍指向 thinking",
        partial is not None and "--thinking disabled" in partial,
        partial,
    )
    # content 在 OpenAI 相容回應裡可能是 null，不能讓偵測本身先崩掉
    none_content = reviewer.truncation_error("length", None, 8192, "disabled")
    check("content 為 None 時不崩潰且仍回訊息", none_content is not None, none_content)

    print("[12] review-local.sh：本機入口的參數必須跟 CI 對齊")
    local_sh = (ROOT / "review-local.sh").read_text(encoding="utf-8")
    # 少了 --rules-dir，同一份 diff 在本機與 CI 會得到不同結果，而兩邊都不提示。
    check("有傳 --rules-dir", "--rules-dir" in local_sh, "review-local.sh")
    check("指向 prompts/rules", "prompts/rules" in local_sh, "review-local.sh")
    # 截斷訊息叫使用者調高 --max-tokens，本機入口就必須真的調得動。
    check("--max-tokens 可由環境變數覆寫", "MAX_TOKENS" in local_sh, "review-local.sh")

    print("[13] extract_json：內容不完整不可以偽裝成格式錯誤")
    # 2026-09-22：第二層 fallback 的 rfind("}") 會抓到「中途某一筆的收尾 }」，
    # 切出來的片段必然語法錯誤，於是錯誤訊息指向片段裡的奇怪位置（實例：column 92）
    # ——讀起來像模型吐了畸形 JSON，真因卻是內容少了尾巴。
    # 與 [11] 是不同路徑：那條看 finish_reason == "length"，這條 finish_reason 正常。
    def parse_err(text: str) -> str:
        try:
            reviewer.extract_json(text)
        except Exception as err:  # noqa: BLE001 - 這裡要驗的就是錯誤訊息本身
            return str(err)
        return ""

    # 字串都收好了，但 { [ { 三層沒收尾
    cut_obj = (
        '{"verdict": "changes_requested", "findings": ['
        '{"path": "a.py", "line": 3, "evidence": "ok"}, {"path": "b.py", "line": 9,'
    )
    msg = parse_err(cut_obj)
    check("物件中途截斷講的是不完整", "不完整" in msg, msg)
    check("物件中途截斷點出還差幾層括號", "括號" in msg, msg)
    # 真實截斷最常見的樣子：前面有一筆完整的 finding，後面切在 evidence 字串中途。
    # rfind("}") 在這裡抓得到第一筆的收尾 }，正是偽裝發生的地方。
    cut_mixed = (
        '{"verdict": "changes_requested", "findings": ['
        '{"path": "a.py", "line": 3, "evidence": "ok"}, '
        '{"path": "b.py", "line": 9, "evidence": "這裡被切'
    )
    check("有完整前綴的截斷也不偽裝", "不完整" in parse_err(cut_mixed), parse_err(cut_mixed))
    check(
        "字串中途截斷指向字串沒收尾",
        "字串中途" in parse_err('{"summary": "講到一半就沒了'),
        parse_err('{"summary": "講到一半就沒了'),
    )
    # 有開頭 { 卻連一個 } 都沒有，舊版報「找不到 JSON 物件」會把人帶去查格式
    check("有 { 無 } 報不完整", "不完整" in parse_err('{"findings": [{"path": "a.py"'), "")
    # 誤報探針：以下兩種是真的畸形，不可以被講成「不完整」
    check("括號平衡但語法錯仍報格式錯誤", "不完整" not in parse_err('{"a": }'), parse_err('{"a": }'))
    # `{"a": 1}}` 兩種實作都解析不了（Extra data），這裡要驗的是它**不會被講成**
    # 「不完整」——收尾多過開頭是畸形，方向剛好相反。
    check("收尾多過開頭不判成不完整", "不完整" not in parse_err('{"a": 1}}'), parse_err('{"a": 1}}'))
    # never-break 護欄：字串裡的括號與跳脫引號不可以被當成結構
    check("字串內的括號不誤判", reviewer.extract_json('{"msg": "a } b { c"}') == {"msg": "a } b { c"})
    check("跳脫引號不誤判", reviewer.extract_json(r'{"msg": "說\"嗨\""}') == {"msg": '說"嗨"'})

    print("[14] diagnostic_excerpt：解析失敗要印得出斷點")
    # 原本只印 content[:2000]。內容不完整時斷點在尾巴，印開頭正好把唯一
    # 有診斷價值的地方切掉，而且看不出總長度——「被切斷」和「從頭就亂吐」在 log 上同形。
    big = "H" * 3000 + "TAILMARK"
    excerpt = reviewer.diagnostic_excerpt(big)
    check("有講總長度", str(len(big)) in excerpt, excerpt[:60])
    check("印得到尾巴", "TAILMARK" in excerpt, "尾巴被切掉了")
    check("短內容整份印出", reviewer.diagnostic_excerpt("abc").endswith("abc"))
    check("content 為 None 時不崩潰", isinstance(reviewer.diagnostic_excerpt(None), str))
    # 函式對了但沒接上去等於沒修：釘住解析失敗那條路徑真的走這個函式。
    # 只看那一行，不掃全檔——docstring 裡留著 `content[:2000]` 講歷史，掃全檔會誤判。
    src = (ROOT / ".github/scripts/deepseek_review.py").read_text(encoding="utf-8")
    fail_path = [ln for ln in src.splitlines() if "無法解析模型輸出" in ln]
    check("找得到解析失敗那行", len(fail_path) == 1, fail_path)
    check(
        "解析失敗路徑有接上 diagnostic_excerpt",
        any("diagnostic_excerpt(content)" in ln for ln in fail_path),
        fail_path,
    )
    check(
        "沒有退回只印開頭的寫法",
        not any("content[:2000]" in ln for ln in fail_path),
        fail_path,
    )

    print()
    if failures:
        print(f"FAILED: {len(failures)} 項 -> {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
