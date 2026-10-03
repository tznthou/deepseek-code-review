# 三個 reviewer 看同一份標的：召回與定位差多少（2026-09-21）

[← 實測紀錄](README.md)

## 問題

同一份 code，`deepseek-v4-pro`、`deepseek-flash`、Codex 各抓到多少？模型自己報的行號，能不能直接拿來貼行內留言？

## 跑前定好的事

預期表在跑之前定稿，跑完沒改。

- **埋 10 個點**：7 個該報；2 個誤報探針（上面幾行已經擋掉的寫法；跟某個該報的點同形狀、只差一個條件）；1 個預期不會報（缺測試：rubric 有一條要報、`python.md` 卻寫明不要報，預期照 `python.md`）
- **判讀**：位置對、機制講錯的，不算命中
- **只跑一次**：量的是各自的絕對表現，不做「誰比較好」的因果結論

## 方法

- **標的**：一份 104 行的 Python，整檔新增，缺陷密度遠高於真實 code
- **DeepSeek 兩個模型**：kit 的 review 程式，套用 `python.md`、關閉 thinking、`max_tokens` 32768，各跑一次
- **Codex**：給沒有行號的完整檔案，加一份對抗式 review 的 prompt（改寫自 [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) 的 adversarial-review，Apache-2.0），要它附上行號，跑一次
- **行號**：DeepSeek 的 finding 由程式用程式碼片段比對重新定位，貼出去用的是重新定位後的行號；這裡另外比對模型自己報的行號
- **花費**：金額沒有記；兩次 DeepSeek 的 token 用量在執行 log 裡

## 結果

| | `deepseek-v4-pro` | `deepseek-flash` | Codex |
|---|---|---|---|
| 7 個該報的點抓到幾個 | **7** | 6（漏了迴圈裡重複的 HTTP 呼叫） | 1 |
| 2 個誤報探針中了幾個 | 0 | 0 | 0 |
| finding 數 | 9 | 7 | 1 |
| 耗時 | 24.5 秒 | 9.1 秒 | 31 秒 |
| 自己報的行號指對幾筆 | **0/9** | **0/7** | 1/1 |

- v4-pro 的第 7 個點（迴圈裡重複的 HTTP 呼叫），算進來的那筆講的是 `collect_authors` 與 `main` 的迴圈各把同一批 PR 抓一次。09-21 與 09-24 兩次判讀都算命中，但預期表寫的是第 31 行「迴圈裡每個 PR 發一次請求」，兩者不完全是同一件事
- 缺測試：三個都沒報
- 預期表以外：v4-pro 還有 2 筆（`classify` 假設欄位一定在，09-24 算有爭議；輸出路徑由 repo 名稱組成、再進 shell，成立），flash 還有 1 筆（沒檢查命令列參數的個數）
- Codex 的原始回應沒有存檔，表裡 Codex 那欄都來自當時的筆記（另記了它給這份 code 整體 3/10 分）

### 行號：DeepSeek 自報的一筆都沒指對

- 16 筆 DeepSeek finding，模型自己報的行號沒有一筆指到它引用的那段 code，偏移 1～29 行。少了重新定位這一層，行內留言會全部貼錯位置
- 重新定位之後，兩個模型的裸 `except` 那筆都停在第 24 行，比引用的 `except:` 早 1 行：`except:` 只有 7 個字元，程式只拿 8 個字元以上的片段比對，改用內文提到的其他程式碼去找。v4-pro 那筆找到的 `collect_authors` 在檔案裡出現兩次，程式不猜、沿用模型報的行號；flash 那筆找到的 `json.loads` 在前一行。這個限制現在的程式還是一樣
- Codex 的 1/1 只有一筆，不能拿來比。兩邊的輸入也不同（Codex 是沒有行號的完整檔案，DeepSeek 是 diff），但這份是整檔新增，兩邊其實都得從第 1 行自己數
- [README §8](../README.md#已驗證) 的 1/16（16 筆裡只有 1 筆指向自己引用的那段 code）是另一批：本 repo 真實 PR 上的 16 筆。這裡的 16 筆是這份合成標的上的

### 誤報探針：兩個模型都讀懂了守衛

「上面幾行已經擋掉」那個探針，兩個模型都沒報空清單，改報事件沒排序、欄位可能不存在。當時兩筆都算成立；09-24 按內容重看 v4-pro 那筆時，改算「有爭議」：缺陷的形狀存在，但這份 code 看不出會不會發生。flash 那筆是同一種說法，沒有另外重看。

### Codex 多看到一條路徑

Codex 的原話是「supplying no PR numbers bypasses API fetching and reaches `archive()` directly」：不帶 PR 編號執行，就跳過所有 API 呼叫，直接走到 shell injection 那一行。DeepSeek 兩個模型都指出 `repo` 來自命令列參數，但都沒講到這條路徑。

### 順帶撈到 kit 的兩個 bug

- 本機入口 `review-local.sh` 沒傳規則目錄：本機跑的 review 一律不套用 `prompts/rules/`，CI 卻會套。第一次就是用它跑的：沒套到規則，`max_tokens` 是當時預設的 8192，輸出也解析失敗，一筆 finding 都沒有。上面兩份 DeepSeek 的結果，是改成直接呼叫、帶上規則、`max_tokens` 改成 32768 之後跑的（兩次的輸出都只用了約 2,000 個 token）
- 輸出被 `max_tokens` 截斷時，舊版不會說是截斷，只報一般的解析錯誤（內容整段是空的時候，就是「回應中找不到 JSON 物件」，見 [README §4.1](../README.md#41-max_tokens-那個坑不處理就-100-失敗)）：症狀指向格式，真因是長度。第一次那則失敗的原因，log 判斷不了：額度是後來實際用量的 4 倍，而且 code fence 那個解析 bug 也會報同一則訊息（見 [flash 那組](2026-09-21-flash-3x.md)）

## 限制

- **只跑一次，而且這個工具不可重現**：同一份 diff 重跑，結果會不同。[flash 那組](2026-09-21-flash-3x.md)在同一份標的上每個模型再跑 3 次：v4-pro 按內容每次抓到 6 個（跟這次的 7 同一種算法），3 次都漏了迴圈裡重複的 HTTP 呼叫
- **Codex 的 1/7 不是召回率**：它的 prompt 寫「一個強的 finding 勝過幾個弱的」。只報 1 筆跟這條指示一致，但只跑一次，分不出是沒看到還是看到了不報。拿它比 v4-pro 的 7/7，是比錯東西
- **標的對 DeepSeek 有利**：Python（有專屬規則檔）、整檔新增。缺陷密度遠高於真實 code，影響方向跑前就寫了不確定。7/7 不能外推到真實 PR
- 題目是我們自己出、自己改；判讀的是語言模型（Claude）

## 因此改了什麼

- 兩個 bug 在 `v1.2.2` 修掉：`review-local.sh` 補傳規則目錄；截斷會直接說是截斷（[CHANGELOG 1.2.2](../CHANGELOG.md#122---2026-09-21)）
- 重新定位行號那一層在這次之前就有了，這次確認它非有不可
- flash 在 Python 上的結果，跟「不要用 flash」（[README §4.2](../README.md#42-為什麼預設用-deepseek-v4-pro)，原本的證據是 Shell 上的技術斷言錯）對不上，所以補做了 [flash 那組](2026-09-21-flash-3x.md)

## 原始資料

[`2026-09-21-three-way-review/`](https://github.com/tznthou/deepseek-code-review-data/tree/main/2026-09-21-three-way-review)：預期表、標的的 diff（branch 已刪；flash 那組的 `python.diff` 是同一份）、兩個模型的 finding 與貼文、送給 Codex 的完整 prompt，以及三次 DeepSeek 呼叫的執行 log（`run-log.txt`，含作廢的第一次；當時沒有存進實驗目錄，2026-10-03 從工具輸出摘出）。
