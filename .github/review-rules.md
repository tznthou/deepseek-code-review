# deepseek-code-review 的 review 規範

這份給 AI review 的「repo 規範那次呼叫」用（reusable-ai-review-post.yml 的 `repo-rules-path`）。
每個 `- ` 條目算一條，`## ` 標題當分組；這段說明本身不會送出。

## GitHub Actions workflow
- 外部 action 一律釘 40 字元的 commit SHA，行尾註解寫完整版本號（例如 `# v7.0.1`）。只寫 `# v7`、或版本號後面還接著別的字，Dependabot 換 SHA 時不會跟著更新註解
- `run:` 區塊不直接內插 `${{ inputs.* }}`、PR 標題這類值；一律走 `env:`，在 shell 裡引用環境變數
- `run:` 區塊的註解裡不寫完整的 `${{ }}` expression：expression 在 shell 之前展開，`#` 註解擋不住
- secret 要在每個用到它的 step 的 `env:` 明確傳；漏傳不會報錯，只會變成空字串，功能安靜地失效
- reusable workflow 在 `v1` 這條線上不移除、不改名 input；要淘汰就留成沒有作用的 input，並印 `::warning::`
- 呼叫 reusable workflow 的 caller 要宣告 `permissions:`；少了會整個 startup_failure，而且 CLI 看不出原因

## prompt 與補充規則
- `prompts/review-rubric.md` 與 `prompts/rules/` 整份都會送進 prompt，不寫給人看的註記、元評論或修改紀錄

## Python 腳本
- `.github/scripts/` 與 `tools/` 只用標準函式庫，不新增需要 pip install 的依賴
- log 與錯誤訊息不印出禁用詞清單的內容、API key 或其他 secret；只給條號、長度這類不洩漏內容的資訊
- 外部指令（`gh`、`git`）失敗要看得見：印 `::warning::` 或回傳錯誤，不要被 `check=False`、空字串或空集合吞掉

## 文件
- 給人照做的文件不寫「檔名:行號」，改標那一行的內容
