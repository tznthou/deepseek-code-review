# 補充規則：GitHub Actions workflow

這次的改動含 `.github/workflows/` 下的檔案。除了通用規則，以下是這類檔案特有的缺陷形狀。

## 安全

- **在 `run:` 區塊裡內插使用者可控的值**。PR 標題、分支名、issue 內文、commit message
  全都由外部貢獻者控制。雙大括號的 expression **早於 shell 展開**，所以值裡的
  `$(...)` 或反引號會在展開後被執行——任何人開一個 PR 就能執行任意指令。
  正確做法是值走 `env:`，shell 裡再引用那個環境變數。
  ⚠️ 不帶引號的 heredoc（`<<EOF`）**擋不住這個**，`toJSON()` 也擋不住（它只做 JSON 跳脫）。
- **`pull_request_target` 搭配 checkout PR 的 head**。那等於用寫入權限執行不受信任的 code。
- **secret 被印進 log**，或被傳給不需要它的 step。
- **第三方 action 沒有 pin 到完整 commit SHA**。tag 是可變的，可以被重新指向。
  `actions/*` 這類第一方 action 用 `v4` 這種 major tag 可以接受。

## 正確性

- **缺少 `permissions:` 區塊**。被呼叫的 reusable workflow 拿不到超過呼叫方的權限；
  呼叫方沒宣告就用 repo 預設（通常唯讀），於是 reusable 裡需要寫入權限的部分會在
  **啟動階段整個失敗**，而且症狀是「一部分 job 正常、另一部分完全不啟動」。
- **`workflow_run` 觸發的 workflow 執行的是 default branch 上的那一份**，不是 PR 的版本。
  在 PR 裡修改這類 workflow 的內容不會生效——這是它的安全性質，但也代表
  「在 branch 上改它來測試」是無效的。
- **`needs:` 指向不存在的 job id**，或形成循環。
- **action 的 input 名稱拼錯**會被靜默忽略，不會報錯。
- **需要 git 歷史（tag、merge-base、changelog）卻沒設 `fetch-depth: 0`**。
- **`gh pr` / `gh issue` 這類子命令沒帶 `--repo`**。它們靠當前工作目錄的 git remote
  推斷 repo，而 workflow 裡的工作目錄不保證是目標 repo——被 checkout 到子目錄時
  根目錄根本沒有 git repo。

## 可靠性

- **錯誤被 `|| true` 或 `continue-on-error` 吞掉**，而那個 step 的失敗其實是該知道的。
  症狀是所有 step 都 success 但功能沒發生。
- **job 沒有 `timeout-minutes`**。
- **浮動的 major tag（如 `@v1`）指向的版本必須已經存在**，否則呼叫方第一次跑就在
  checkout 失敗。

## 不要報的

- 不要報「沒有 `concurrency`」或「沒有快取」這類最佳化建議，除非 diff 顯示它造成實際問題。
- 不要報 `${{ }}` 在 `if:`、`env:`、`with:` 裡的一般用法——**只有 `run:` 區塊內插才是注入風險**。
- 不要把「這個 workflow 沒有做 X」當成缺陷，除非 diff 裡有東西顯示它應該做 X。
- 不要報「應該 pin 到 SHA」兩次以上；同一份 diff 裡多個 action 都沒 pin 時，合併成一筆。
