# 參考與致謝

這個 kit 的一些設計想法來自其他專案。**想法、方法與架構不受著作權保護**，
所以這裡列的是學術與工程上的誠信歸屬，不是授權義務。

## [alibaba/open-code-review](https://github.com/alibaba/open-code-review)（Apache-2.0）

精讀之後借用了三個**設計想法**（實作全部獨立撰寫）：

| 想法 | 我們怎麼做的 | 差異 |
|---|---|---|
| **行號不要問模型，要它給程式碼片段、由程式算** | `.github/scripts/locate.py` 的四層階梯 | 他們的階梯是「模型若給了行號就先用」，我們**反過來**：片段優先、模型行號當備援。因為他們的 agent 有讀檔工具、行號有依據，我們是單次呼叫只看得到 diff |
| **依檔案型態附加不同的 review 規則** | `prompts/rules/` + `select_rules()` | 他們 52 份規則、走 system prompt；我們兩份、走 **user message**（保住 context caching），而且刻意不做通用 fallback（我們的 rubric 本身就是） |
| **獨立一層過濾誤報的 prompt** | 試過，**實測失敗後移除** | 見 README §8。誤刪是刪對的 3.75 倍 |

⚠️ **一則更正。** 最後那項曾經內建為 `prompts/review-filter.md`，當時的 commit
message 寫「條文自己寫」——**那個說法不準確**：其中「受保護主題」一節五個條目
與原文逐條對應、順序相同，實質上是翻譯，而翻譯屬於衍生作品。
2026-09-21 盤點授權時發現並移除該檔案（它當時已因實測結果停用）。

其餘檔案逐一比對過，沒有同類問題：`prompts/rules/github-workflows.md` 約半數
條目是本 repo 自己踩過的坑，重疊部分是 GitHub 官方文件就有的公知事實；
`prompts/rules/python.md` 結構與內容都不同；`locate.py` 是演算法想法的獨立實作。

## [AACR-Bench](https://huggingface.co/datasets/Alibaba-Aone/aacr-bench)（Apache-2.0）

`tools/eval/` 用它的 2,145 則人工標註 review comment 做評估。
資料集**執行時才下載，不隨本 repo 散布**。

## 其他

* [hustcer/deepseek-review](https://github.com/hustcer/deepseek-review) — 選型階段的對照組，見研究報告。
