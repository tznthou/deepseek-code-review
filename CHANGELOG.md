# Changelog

本專案所有值得注意的變更都記錄在這個檔案。

格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號依循 [語意化版本](https://semver.org/lang/zh-TW/)。

> **關於 `v1` 這個浮動 tag**：`@v1` 會跟著 v1.x.x 移動（同 `actions/checkout@v4` 的慣例），
> 引用它的 repo 不必改任何東西就會拿到修正版。代價是破壞性變更也會自動推播——
> 所以 v1 這條線上的相容性承諾見 README §5，本檔的 `BREAKING` 標記請特別留意。

## [Unreleased]

### Fixed

- **`extract_json` 不再讓「內容不完整」偽裝成「格式錯誤」。** 第二層 fallback 用
  `text.rfind("}")` 找結尾，內容被切斷時它抓到的是**中途某一筆的收尾 `}`**，
  切出來的片段必然語法錯誤，於是 `JSONDecodeError` 指向片段裡的奇怪位置
  （實例：`Expecting ',' delimiter: line 1 column 92`）——讀起來像模型吐了畸形
  JSON，真因卻是少了尾巴。現在先掃一遍括號與字串狀態，講明「JSON 在中途結束
  （還有 N 層括號沒有收尾）」或「JSON 在字串中途結束」。有 `{` 卻連一個 `}`
  都沒有的情況，原本報「回應中找不到 JSON 物件」，也一併改成報不完整。
  ⚠️ 與 `v1.2.2` 修的截斷偵測是**不同路徑**：那條看 `finish_reason == "length"`，
  是 API 自己說了它截斷；這條處理的是 finish_reason 正常、content 卻真的不完整。
  括號平衡但語法錯（`{"a": }`）與收尾多過開頭（`{"a": 1}}`）仍然報格式錯誤，
  不會被講成不完整——兩者都有測項釘著。
- **解析失敗時印的原始輸出改成頭尾都印、並標明總長度**（原本只印 `content[:2000]`）。
  內容不完整時斷點在尾巴，印開頭正好把唯一有診斷價值的地方切掉，而且看不出總長度
  ——「被切斷」和「模型從頭就亂吐」在 log 上長得一模一樣。

### Changed

- `tools/selftest.py` 從 12 組 49 項增加到 **14 組 65 項**，新增的兩組涵蓋上述兩項修正
  （含「括號平衡但語法錯」「收尾多過開頭」兩個誤報探針，以及字串內含括號、
  跳脫引號這些不可誤判的護欄）。README badge 與 `SETUP-CHECKLIST.md` §9 一併更新
  ——後兩處先前分別停在 `49` 與 `9 項`，是發版時漏掃的。

- `codeql-config.yml` 加上 `threat-models: local`。**預設的 threat model 只把「遠端」
  輸入當汙染源**，命令列參數、環境變數、檔案系統屬於 local source——所以
  `sys.argv` 流進 `subprocess.run(..., shell=True)` 這種本機工具的 command injection，
  預設設定下**不會被報出來**。實測（刻意寫壞的 104 行 Python）：預設 4 筆告警，
  加上這個設定變 7 筆，多出來的三筆全是需要追資料流的
  （`py/command-line-injection`、`py/partial-ssrf`、`py/path-injection`）。
  複製這份設定的 repo 若掃的是 CLI 工具或 CI 腳本，這個設定通常才是你要的。

### Docs

- `USAGE.md` 釘版本的範例從 `@v1.2.1` 更新到 `@v1.2.2`（v1.2.2 發版時漏掃）。
- README §8 補上「本 repo 零告警」那句的前提，以及查 PR alert 要用
  `refs/pull/<n>/merge` 而不是 `refs/heads/<branch>`。

## [1.2.2] - 2026-09-21

### Fixed

- `review-local.sh` 沒有傳 `--rules-dir`，本機跑**永遠不會套用** `prompts/rules/*.md`。
  CI 走 reusable workflow 時 `typed-rules` 預設開啟，所以同一份 diff 在本機與 CI
  會得到不一樣的結果，而兩邊都不會提示。
- 模型輸出被 `max_tokens` 砍斷時，錯誤訊息是「回應中找不到 JSON 物件」——
  JSON 格式其實完全正確，只是少了尾巴。症狀指向格式、真因是長度，而 token 費用照算。
  現在會直接說明是截斷，並區分兩種成因（額度不足 vs thinking 吃光額度）。
- 截斷提示的分流條件從「`content` 空不空」改成「thinking 開著沒」。
  thinking 開著時就算已經有部分輸出，首要嫌疑仍然是 reasoning 吃掉額度
  （2026-09-19 實測：`--max-tokens` 給到 32768 仍被截斷，reasoning 自己用掉 31408），
  舊的分流會在這種情況下叫使用者去調一個沒用的參數。
  **這筆是 kit 自己的 review 在 PR #17 報出來的**（3 筆裡唯一完全成立的一筆）。
- `truncation_error` 接受 `content` 為 `None`——OpenAI 相容回應的 `content` 可能是 null，
  偵測本身不應該先崩掉。
- `deepseek_review.py` 檔頭 docstring 寫著 `DEEPSEEK_MODEL` 預設 `deepseek-flash`，
  實際預設是 `deepseek-v4-pro`。

### Added

- `review-local.sh` 支援 `MAX_TOKENS` 環境變數。截斷訊息會要求使用者調高額度，
  本機入口就必須真的調得動。
- README §9「為什麼會有這個 repo」。
- `tools/selftest.py` 新增兩組測試（37 → 49 項）：截斷偵測的四種情境，
  以及本機入口與 CI 的參數對齊檢查。

## [1.2.1] - 2026-09-21

### Fixed

- 把 `reusable-ai-review-post.yml` 的 `filter-findings` input 加回成 no-op。
  v1.2.0 移除它是**掛在 minor 版號上的破壞性變更**，而 `v1` 是浮動 tag ——
  打 tag 的那一刻就自動推播給所有引用 `@v1` 的 caller，傳了那個參數的人會直接
  `startup_failure`。零受害純屬運氣（0 star / 0 fork，暴露窗口 68 分鐘）。

### Deprecated

- `filter-findings` 標記為 deprecated，傳入時印 `::warning::`。v2 才會真的移除。

### Added

- README §5 補上「上游可以隨時換掉你跑的 code」這一格威脅，含 `v1` 浮動 tag 的
  三條相容性承諾，以及自己破過一次的紀錄。

## [1.2.0] - 2026-09-21

### Removed

- **BREAKING:** 移除 `reusable-ai-review-post.yml` 的 `filter-findings` input。
  ⚠️ 這是個錯誤——破壞性變更不該掛在 minor 版號上，v1.2.1 已修正為 no-op。
- 移除 review filter 那一層。用 700 則人工標註資料實測：**誤刪 15 筆正確的、
  只刪對 4 筆**，precision 反而變差。評估工具保留在 `tools/eval/`，
  任何人都能拿自己的 prompt 重跑。
- 移除一個構成衍生作品的檔案。

### Added

- MIT LICENSE。先前沒有 LICENSE 等於保留所有權利，而文件卻在教人複製檔案。
- `tools/eval/` 評估框架（AACR-Bench、`workflow_dispatch` 觸發、API key 不離開 GitHub）。

### Changed

- README 分段對齊現狀。

## [1.1.1] - 2026-09-21

### Fixed

- 兩個**靜默失效**：不報錯、step 全 success、log 看起來正常。
  - review filter 因為兩邊比對邏輯分岔（一邊用原始子字串、一邊壓縮空白），
    永遠不會刪掉任何 finding。
  - 定位層把模型**報對的**行號改成錯的——`existing_code` 裡的反引號被當成散文
    挖取片段，導致比對到錯誤位置。

## [1.1.0] - 2026-09-21

### Added

- 定位機制 `locate.py`：行號改由程式用程式碼片段文字比對算出，不採信模型自報的值。
  實測 16 筆 finding 只有 **1 筆**真的指向它自己引用的那段 code，其餘偏移 +1 到 +24 行。
- 依 diff 涵蓋的檔案型態附加補充規則（`prompts/rules/github-workflows.md`、`python.md`）。
  規則走 user message 不走 system prompt，不影響 context caching 命中。
- review filter（v1.2.0 實測後移除）。

## [1.0.2] - 2026-09-21

### Fixed

- `gh pr review` 少了 `--repo`：走 reusable workflow 時 kit 被 checkout 到 `.kit`
  子目錄，工作目錄根沒有 git repo，導致摘要貼不出去——而 job 仍然回報 success，
  症狀是「全綠但零留言」。
- USAGE.md 的錯誤建議：DeepSeek 平台沒有消費上限設定，計費是預付制。

### Changed

- kit 自己的 `03`／`04` 改用 reusable workflow（dogfood）。上線第一天就抓到
  只有 reusable 版才會出現的 bug（即上述 `--repo`）。

### Added

- USAGE.md 補上 fork PR 核可政策的設定指令。

## [1.0.1] - 2026-09-21

### Security

- 修掉 shell injection：不帶引號的 heredoc（`<<EOF`）內插使用者可控的值時，
  `toJSON()` 只做 JSON 跳脫、擋不住命令替換——PR 標題寫 `$(whoami)` 就會執行。
  改為「值走 `env:`、heredoc 帶引號」。這筆是 `actionlint` 抓到的，AI review 沒報。

### Fixed

- 修掉 AI review 報的兩個 finding。

## [1.0.0] - 2026-09-21

### Added

- 四支可重用 workflow（`reusable-static-review`、`reusable-codeql`、
  `reusable-ai-review-collect`、`reusable-ai-review-post`），其他 repo 可以用引用的
  方式導入，不必複製腳本也不必複製 rubric。
- `USAGE.md`：三步驟導入說明與可直接複製的 caller 範本。

[1.2.2]: https://github.com/tznthou/deepseek-code-review/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/tznthou/deepseek-code-review/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/tznthou/deepseek-code-review/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/tznthou/deepseek-code-review/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/tznthou/deepseek-code-review/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/tznthou/deepseek-code-review/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/tznthou/deepseek-code-review/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/tznthou/deepseek-code-review/releases/tag/v1.0.0
