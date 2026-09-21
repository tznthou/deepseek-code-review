#!/usr/bin/env python3
"""用「程式碼片段文字比對」決定 finding 的行號，而不是相信模型自己報的行號。

為什麼要這層（2026-09-21 實測，n=16，資料來自本 repo 八次真實 review 的 artifact）：

    模型報的行號 16 筆裡只有 1 筆真的指向它自己 evidence 引用的那段程式碼，
    其餘 15 筆偏移 +1 到 +24 行不等。最典型的一筆，模型的 evidence 明寫
    「第 48 行：`BASE='...base.sha'`」，而那行實際在 55——它自己引對了內容、
    數錯了行號。

    同一批資料改用「拿 evidence 裡的程式碼片段去 diff 裡做文字比對」來定位，
    13/16 唯一命中且全部指對，3 筆誠實定不到（其中 1 筆是「finding 在講被刪掉的
    東西」，新檔本來就沒有對應行，定不到才是正確行為）。

    結論：引用程式碼是模型擅長的，數 diff 偏移不是。所以行號由程式算，
    片段由模型給。

⚠️ 與 alibaba/open-code-review 的差異（那邊是這個做法的來源）：
    他們的階梯是「模型若給了行號就先用它」，片段比對只是退路。我們反過來，
    片段優先、模型行號當 fallback。理由是上面那組實測——他們的 agent 有
    file_read 工具讀得到真實檔案內容，行號有依據；我們是單次 API 呼叫，
    模型只看得到 diff，數行號等於在心算 @@ 偏移量。

定位不到不是錯誤，是訊號：片段在該檔 diff 裡找不到，通常代表這筆 finding
在描述不存在的東西。呼叫端可以據此降級處理，不要硬貼到一個猜出來的行號上。
"""

from __future__ import annotations

import re

__all__ = ["index_diff", "extract_snippets", "locate_snippet", "resolve_line", "normalize_ws"]

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_GIT_HEADER = re.compile(r" b/(.+)$")

# 片段太短會到處都命中（`return`、`}`、`fi`），短於這個長度就不拿來定位。
MIN_SNIPPET_LEN = 8


def index_diff(diff_text: str) -> dict[str, dict[int, str]]:
    """把 unified diff 拆成 {新檔路徑: {新增側行號: 該行內容}}。

    與 post_review.parse_valid_lines 掃的是同一份東西，差別在這裡**留下行內容**，
    才有辦法做文字比對。context 行（開頭是空白）同樣收錄——GitHub 允許在
    context 行留言，而模型引用的片段常常落在 context 行上。
    """
    index: dict[str, dict[int, str]] = {}
    current: str | None = None
    new_line = 0

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            match = _GIT_HEADER.search(raw)
            current = match.group(1).strip() if match else None
            if current:
                index.setdefault(current, {})
            new_line = 0
            continue
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            if target != "/dev/null":
                path = target[2:] if target.startswith("b/") else target
                current = path
                index.setdefault(current, {})
            continue
        m = _HUNK.match(raw)
        if m:
            new_line = int(m.group(1))
            continue
        if current is None or new_line == 0:
            continue
        if raw.startswith("+"):
            index[current][new_line] = raw[1:]
            new_line += 1
        elif raw.startswith("-"):
            pass  # 刪除行不佔新檔行號
        elif raw.startswith(" "):
            index[current][new_line] = raw[1:]
            new_line += 1
    return index


def normalize_ws(text: str) -> str:
    """把連續空白壓成單一空格，讓縮排差異不影響比對。

    公開的原因：`deepseek_review.apply_filter` 驗證「模型宣稱的反證行是否真的在
    diff 裡」時必須用同一套正規化。兩邊各寫一份的話會分岔——實測發現過一次：
    那邊用原始子字串比對，模型複製 YAML／Python 這類縮排敏感的行時只要空白稍有
    出入就被判成幻覺，filter 於是永遠不刪任何東西，而且不會報錯。
    """
    return re.sub(r"\s+", " ", text.strip())


def extract_snippets(*sources: str) -> list[str]:
    """從 finding 的文字欄位裡抽出候選程式碼片段，依可信度排序。

    `existing_code` 欄位（rubric 要求模型逐字複製的那段）最可信，直接整段拿來用；
    evidence / body 則是散文夾程式碼，只能把引號與反引號裡的東西挖出來。
    實測模型愛用的兩種括法：中文書名號『』與 markdown 反引號。
    """
    out: list[str] = []
    for src in sources:
        if not src:
            continue
        stripped = src.strip()
        # 整段就是程式碼（existing_code 的情況）：直接收，不必挖引號。
        if stripped and "『" not in stripped and "`" not in stripped:
            out.append(stripped)
            continue
        out.extend(m.group(1) for m in re.finditer(r"『(.+?)』", src, re.S))
        out.extend(m.group(1) for m in re.finditer(r"`([^`]+)`", src))
    seen: set[str] = set()
    result: list[str] = []
    for s in out:
        s = s.strip()
        if len(s) >= MIN_SNIPPET_LEN and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def locate_snippet(
    snippets: list[str], file_lines: dict[int, str]
) -> tuple[int | None, str]:
    """在單一檔案的行索引裡找片段，回傳 (行號, 說明)。

    **只有唯一命中才算數。** 多重命中一律放棄——同一段樣板程式碼出現在好幾行是
    正常的，在裡面挑一個等於拿一個錯位置換另一個錯位置。
    """
    for snippet in snippets:
        first = normalize_ws(snippet.splitlines()[0]) if snippet.splitlines() else ""
        if len(first) < MIN_SNIPPET_LEN:
            continue
        hits = [ln for ln, content in file_lines.items() if first in normalize_ws(content)]
        if len(hits) == 1:
            return hits[0], "片段唯一命中"
        if len(hits) > 1:
            return None, f"片段多重命中（{len(hits)} 處），不猜"
    return None, "片段在該檔 diff 內找不到"


def resolve_line(
    finding: dict, index: dict[str, dict[int, str]]
) -> tuple[int | None, str]:
    """決定一筆 finding 最終該用哪個行號。

    階梯（由可信到不可信）：
      1. 片段在**自己宣稱的檔案**裡唯一命中 → 用它
      2. 片段在**其他檔案**裡唯一命中 → 用它，同時改寫 path
         （模型把 finding 掛錯檔案、但內容引對了的情況）
      3. 片段定不到，但模型給的行號落在 diff 可留言範圍內 → 退回模型行號
      4. 都不行 → (None, 原因)，呼叫端降級處理

    第 2 層刻意排在 LLM 之前也排在「信任模型行號」之前：跨檔搜尋是確定性的，
    找不到就是找不到，不會像模型那樣硬掰一個答案出來。
    """
    path = finding.get("path", "")
    snippets = extract_snippets(
        finding.get("existing_code", ""),
        finding.get("evidence", ""),
        finding.get("body", ""),
    )
    own = index.get(path, {})

    if snippets and own:
        line, how = locate_snippet(snippets, own)
        if line is not None:
            return line, how
        if "多重命中" in how:
            # 本檔就有好幾處候選，答案在本檔、只是分不出是哪一處。這時候再去翻
            # 別的檔案是有害的：別檔若剛好唯一命中，就會把 finding 從「答案所在的
            # 檔案」搬到一個更不可能對的地方。直接回報不猜。
            return None, how

    # 跨檔：只在唯一一個檔案裡命中才接受。
    if snippets:
        cross: list[tuple[str, int]] = []
        for other_path, lines in index.items():
            if other_path == path:
                continue
            line, _ = locate_snippet(snippets, lines)
            if line is not None:
                cross.append((other_path, line))
        if len(cross) == 1:
            finding["path"] = cross[0][0]
            return cross[0][1], f"片段命中其他檔案（原報 {path}）"
        if len(cross) > 1:
            return None, f"片段跨 {len(cross)} 個檔案命中，不猜"

    model_line = finding.get("line")
    if isinstance(model_line, int) and model_line in own:
        return model_line, "片段定位失敗，退回模型行號"

    return None, "片段與模型行號都定不到"
