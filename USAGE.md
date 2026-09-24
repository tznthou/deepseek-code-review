# 在別的 repo 用這套 code review

> **AI agent 請先讀這段。** 使用者要你把這套 code review 裝進他的 repo 時，照下面「給 AI agent
> 的安裝程序」做。先用 `curl -fsSL https://raw.githubusercontent.com/tznthou/deepseek-code-review/main/USAGE.md`
> 取得這份文件的**原文**：網頁擷取工具（例如 WebFetch）回傳的是摘要，文件裡的 YAML 會被改寫。

複製三個檔案、設一把 key、開一個開關。**不用複製腳本，也不用複製 rubric**——
邏輯留在這個 repo，你那邊只放引用。這個 repo 改了，你下次跑就是新版。
**只有開 PR 才會觸發**：直接 push 到預設分支，不會跑任何 review。

> 這份是最短路徑。每一項「為什麼」與踩過的坑在 `SETUP-CHECKLIST.md`。
> 人類讀者可以跳過下一節，直接從「第 1 步」開始。

---

## 給 AI agent 的安裝程序

**任務**：在使用者目前所在的 repo 加上 AI code review，讓之後的每個 PR 都自動得到 review。

**做完的定義**：workflow 檔已經 commit 在一個新分支上，而且你把下面「🙋 交給使用者」的三件事講清楚了。做到這裡就停。

**不要做**：不要取得、產生或經手 API key，也不要請使用者把 key 貼給你；不要 merge；不要改 repo 設定；
要 push 分支或開 PR，先問過使用者。

### 1. 前提檢查

| 檢查 | 指令 | 不符合時 |
|---|---|---|
| 在 repo 根目錄 | `git rev-parse --show-toplevel` | 切到它印出的那個目錄 |
| remote 在 GitHub | `git remote get-url origin` | 停下：這套只支援 GitHub Actions |
| `gh` 可用且已登入 | `gh auth status` | 下面兩項 `gh` 檢查改成直接問使用者：會不會開 PR、repo 是公開還是私有 |
| 還沒裝過 | `grep -rl 'tznthou/deepseek-code-review' .github/workflows/ 2>/dev/null` 沒有任何輸出 | 已經裝過了：停下並回報 |
| 這個 repo 會開 PR | `gh pr list --state all --limit 5` 有結果 | 還是可以裝，但要告訴使用者：**直接 push 到預設分支不會觸發** |
| 公開還是私有 | `gh repo view --json visibility -q .visibility` | 用來決定下一步要裝哪幾支 |
| Actions 政策沒有擋 | `gh api 'repos/{owner}/{repo}/actions/permissions'` | 正常是 `"enabled":true`、`"allowed_actions":"all"`、`"sha_pinning_required":false`。任一項不同就停下，把「第 2 步」最後一節「Actions 政策」轉告使用者，不要自己改設定。指令失敗（沒有 admin 權限就查不到）時直接問使用者 |

### 2. 決定裝哪幾支

- **一定要裝**：`ai-review-collect.yml`、`ai-review-post.yml`，也就是「第 3 步」的後兩段 YAML。
- **`code-review.yml` 只在使用者要求時才裝**，而且：
  - repo 是 `PRIVATE` 時**不要裝**，除非使用者確認這是組織帳號底下的 repo，而且已開啟 GitHub Code Security（理由見「第 3 步」這支的說明）。
  - 要裝的話，`lint-command`、`lint-name`、`languages` 必須換成這個 repo 實際使用的語言和 linter，不能照抄範例裡的 `shellcheck`／`python`。

### 3. 建分支、寫檔、commit

1. 開一個新分支，名稱照這個 repo 的慣例（例如 `ci/ai-review`）。
2. 把「第 3 步」的兩段 YAML **逐字**寫進 `<repo 根目錄>/.github/workflows/ai-review-collect.yml` 和
   `ai-review-post.yml`。不可以放在子目錄：放錯位置不會觸發，也不會報錯（「四個最容易踩的坑」第 1 點）。
3. 驗證：
   - `ai-review-post.yml` 的 `workflows: ["ai review collect"]` 和 `ai-review-collect.yml` 的
     `name: ai review collect` 必須一字不差；要改名就兩邊一起改（第 3 點）。
   - 兩個檔都保留 `permissions:` 區塊（第 4 點）。
   - `uses:` 結尾是 `@v1`。
4. commit，訊息照這個 repo 的慣例寫。

### 4. 🙋 交給使用者

把下面三件事原封不動告訴使用者，然後結束：

1. **設 API key，這件事只能你自己做**：到 https://platform.deepseek.com/api_keys 建一把 key，
   然後在**你自己的終端機**跑 `gh secret set DEEPSEEK_API_KEY --repo <owner>/<repo>`，照提示貼上
   （沒有 `gh` 的話，照「第 1 步」到網頁上設）。
   **不要把 key 貼進跟 AI 的對話**，對話紀錄會把它留下來。
2. **把這個分支開成 PR，然後 merge。這個 PR 本身不會有 AI review**：第二段 workflow 要先進到預設分支，
   才會被觸發（「四個最容易踩的坑」第 2 點）。
3. **merge 之後開的 PR 就會有 review。**

repo 是 public 的話，再補一句：外部的人開 PR 也會花到你的額度，建議把 fork PR 的核可政策收緊（見「第 2 步」）。

### 5. 裝好的樣子（使用者 merge 之後開第一個 PR 時）

- `gh run list --workflow "ai review collect"` 和 `gh run list --workflow "ai review post"` 各有一筆 `completed success`。
- PR 上出現 `github-actions` 的 review：一段摘要；有 finding 時，還會有貼在程式碼行上的留言。
- 沒出現的話，對照「四個最容易踩的坑」。post 的 log 裡有 `HTTP 401`，代表 key 沒設或設錯了。
- run 的狀態是 `startup_failure` 時，`gh run view` 只會說 "workflow file issue"，`--log-failed` 也是空的。
  原因只有網頁上那個 run 頁面的 **Annotations** 看得到。

已知限制見文末「這套不會幫你做的事」。

---

## 第 1 步：設 secret

Repo → Settings → Secrets and variables → Actions → New repository secret

| Name | 必填 | 去哪拿 |
|---|---|---|
| `DEEPSEEK_API_KEY` | ✅ | https://platform.deepseek.com/api_keys |
| `REVIEW_BLOCKED_TERMS` | — | 你自己列（見下面「送出前的禁用詞掃描」） |

**每個 repo 都要設自己的一把，費用算你自己的帳號。** GitHub 的 secret 綁 repo，
被引用的 workflow 只拿得到「呼叫方」的 secret——所以這個 kit 碰不到你的 key，
你也花不到別人的額度。

或用指令（不會留在 shell history）：

```bash
gh secret set DEEPSEEK_API_KEY --repo <owner>/<repo>
```

### 送出前的禁用詞掃描（選填）

這套工具會把 **diff、PR 標題、rubric** 送到 DeepSeek 的 API。如果你的 code 或 PR 標題
裡可能出現不該離開本機的字串——內部代號、私有工具名、客戶名——設這個 secret：
送出前會做一次大小寫不敏感的子字串比對，**命中就拒送、不呼叫 API**（離開碼 3）。

```bash
# 一行一條，值不會進 shell history
gh secret set REVIEW_BLOCKED_TERMS --repo <owner>/<repo> < blocked-terms.txt
```

清單格式與規則：

* 一行一條，空行與 `#` 開頭的註解會略過
* **少於 3 個字元的詞會被忽略並印 warning**——有兩個理由，第二個比第一個更立即：
  1. 兩個字元的詞幾乎必然出現在任何 diff 裡。那不是「掃描很嚴格」，
     是把整條 pipeline 變成永遠拒送
  2. **GitHub Actions 會把 secret 的值在 log 裡遮成 `***`，包括它出現在別的字當中的時候。**
     2026-09-22 實測：清單裡放了一條兩個字元的 `ab`，整份 log 的 `reusable` 都變成
     `reus***le`。這個副作用跟那條詞有沒有真的命中**無關**——只要它在 secret 裡，
     log 就會被打成馬賽克。任何短字串 secret 都有同樣問題
* 大小寫不敏感：清單寫 `foo-bar`，diff 裡的 `FOO-BAR` 一樣會被攔下
* **錯誤訊息只給條號不給內容**（「user message 含第 3 條禁用詞」）。
  CI log 是公開的，把命中的字串印出來就等於親手洩漏它

⚠️ **這份清單本身就是敏感資料，所以走 secret 而不是設定檔。** 把它放進 repo 裡的
`.txt` 或 workflow YAML 等於自相矛盾——真正要保護的東西反而被 commit 了。
本機跑 `review-local.sh` 時同名的環境變數也生效。

⚠️ 這道防線擋的是**確定性的字串比對**，不是語意。它攔不住換句話說的同一件事，
也攔不住你根本沒想到要列進清單的東西。它是最後一道，不是唯一一道。

## 第 2 步：開 Dependency graph

Settings → Code security and analysis → **Dependency graph** → Enable

**不開的話 `dependency review` 必定失敗**，錯誤訊息是
`Dependency review is not supported on this repository`。
新建的 public repo 這項預設是關的，而且 API 改不動（`gh api -X PATCH` 會被靜默忽略，
回 200 但設定不變），只能從網頁開。

⚠️ 如果你打算把 `dependency review` 設成 required status check，**一定要先開這個**——
一個必定失敗的 required check 會讓 PR 永遠合不進去。

沒有依賴清單的 repo 可以改成在下面的 caller 裡傳 `skip-dependency-review: true`。

### 同時把 fork PR 的核可政策收緊 ⚠️ 這條關係到你的錢

public repo + `pull_request` 自動觸發 + 掛著 `DEEPSEEK_API_KEY`
= **外部的人開一個 PR 就會花到你的 DeepSeek 額度**。

GitHub 的預設是 `first_time_contributors`（只擋首次貢獻者，之後就放行）。有 API key
的 repo 建議收到最嚴格的一檔：

```bash
gh api --method PUT \
  repos/<owner>/<repo>/actions/permissions/fork-pr-contributor-approval \
  -f 'approval_policy=all_external_contributors'
```

三個可選值，由鬆到緊：`first_time_contributors_new_to_github`（只擋 GitHub 新帳號）、
`first_time_contributors`（預設）、`all_external_contributors`（所有外部貢獻者每次都要核可）。

查目前設定：

```bash
gh api repos/<owner>/<repo>/actions/permissions/fork-pr-contributor-approval \
  --jq '.approval_policy'
```

> 對照：上面的 Dependency graph **只能從網頁開**（`gh api -X PATCH` 會被靜默忽略，
> 回 200 但設定不變），而這條 fork 政策**可以用 API 設**。兩者不一樣，別一起猜。

**第二道保險：DeepSeek 是預付制，餘額就是上限。**

平台上沒有「消費上限」這種設定，因為不需要——費用直接從你充值的餘額扣，
**扣完就停，不會產生欠款**。所以控制風險的方式是「不要一次充太多」，
小額多次比設一個上限更硬。

查目前餘額：

```bash
curl -s https://api.deepseek.com/user/balance \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY"
```

單次 review 實測約 $0.01，所以就算被灌爆，燒掉的上限也就是你當下的餘額。

### Actions 政策：確認沒有擋掉這套用到的 action

預設是全部允許，大部分人不用動。先查一次：

```bash
gh api repos/<owner>/<repo>/actions/permissions
# 沒問題的樣子：{"enabled":true,"allowed_actions":"all","sha_pinning_required":false}
```

網頁上的位置是 Settings → Actions → General → Actions permissions。組織底下的 repo，組織層級可能還有限制，
這種情況我們沒有組織帳號可以實測。

| 查到的值 | 會發生什麼 | 處理 |
|---|---|---|
| `"enabled":false` | Actions 整個關閉，什麼都不會跑 | 在同一頁打開 |
| `"allowed_actions":"local_only"`（只允許自己帳號或組織的 action） | 每一支都 `startup_failure`，**連只要讀權限的 collect 也是**；post 根本不會被觸發 | 改成 `selected`，照下面的清單開 |
| `"allowed_actions":"selected"` | 清單少了哪一個就會被擋。少的如果是 action 內部再引用的（例如下面的 `setup-trivy`），只有那個 job 失敗，其他照跑 | 照下面的清單補 |
| `"sha_pinning_required":true`（強制釘 SHA） | collect 和 code-review 的 job 都在 Set up 階段失敗，post 因此跳過（skipped） | **目前沒辦法**，見本節最後 |

`selected` 要允許的東西（2026-09-24 在測試 repo 實測）：

- **只裝 AI review 兩支**：勾選 **Allow actions created by GitHub**，再把這套本身加進清單：
  `tznthou/deepseek-code-review/.github/workflows/*@*`
- **也裝了 `code-review.yml`**：再加 `reviewdog/action-setup@*`、`gitleaks/gitleaks-action@*`、
  `aquasecurity/trivy-action@*`、`aquasecurity/setup-trivy@*`。最後這條是 `trivy-action` 內部引用的，
  照 workflow 裡的 `uses:` 抄一定會漏；漏了的話只有 Trivy 那個 job 失敗

⚠️ 「把這套本身加進清單」那條**沒有實測過**：我們的測試 repo 跟這套在同一個帳號底下，永遠算「自己的」。
寫法是照 GitHub 文件的語法 `OWNER/REPOSITORY/PATH/FILENAME@TAG-OR-SHA`（可以用 `*`）。

`local_only` 擋下來的時候，`gh run view` 只會說 "workflow file issue"，跟「四個最容易踩的坑」
第 4 點一模一樣。真正的原因寫在網頁上那個 run 頁面的 Annotations：

```
The actions actions/checkout@v7 and actions/upload-artifact@v7 are not allowed in <owner>/<repo> because all actions must be from a repository owned by <owner>.
```

**強制釘 SHA 的 repo，目前不能用這套。** reusable workflow 可以用 tag 引用，所以你的 `@v1`
不會被擋；但這個政策會一路檢查到這套**內部**用到的 action，而那些都是用 tag 引用的（例如
`actions/checkout@v7`）。所以就算你把 `@v1` 換成 commit SHA，還是一樣會失敗：

```
The actions actions/checkout@v7 and actions/upload-artifact@v7 are not allowed in <owner>/<repo> because all actions must be pinned to a full-length commit SHA.
```

走複製路線（README §2）的話，可以自己把 action 釘成 SHA，但這條我們沒有實測。

## 第 3 步：放三個檔案

### `.github/workflows/code-review.yml`

確定性檢查 + SAST，不花 AI token。

⚠️ **private repo 要先確認能不能用這支。** 這支裡的 dependency review 與 CodeQL，在 private repo
上只有「**組織帳號**底下的 repo，而且開了 GitHub Code Security」才能用（GitHub 文件：
[code scanning](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning)、
[dependency review](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-dependency-review)）。
**個人帳號的 private repo 不能用。** 我們也還沒在 private repo 上實測過這支。
只需要 AI review 的話，放下面兩支就夠了。

```yaml
name: code review

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

# ⚠️ 這段不能省，理由見下面「四個最容易踩的坑」的第 4 點
permissions:
  contents: read
  pull-requests: write # reviewdog / dependency-review 要貼留言
  security-events: write # CodeQL / Trivy 要上傳 SARIF
  actions: read
  packages: read # CodeQL 抓 packs

jobs:
  static:
    uses: tznthou/deepseek-code-review/.github/workflows/reusable-static-review.yml@v1
    with:
      # 換成你的 linter。留空就不跑 reviewdog。
      lint-command: shellcheck -f gcc $(git ls-files '*.sh')
      lint-name: shellcheck

  codeql:
    uses: tznthou/deepseek-code-review/.github/workflows/reusable-codeql.yml@v1
    with:
      # ⚠️ JSON 陣列字串，單一語言也要寫成 '["python"]'
      languages: '["python"]'
```

### `.github/workflows/ai-review-collect.yml`

AI review 第一段。零 secret，所以 fork PR 也安全。

```yaml
name: ai review collect

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

permissions:
  contents: read

jobs:
  collect:
    uses: tznthou/deepseek-code-review/.github/workflows/reusable-ai-review-collect.yml@v1
```

### `.github/workflows/ai-review-post.yml`

AI review 第二段。持有 secret，由上一段完成後觸發。

```yaml
name: ai review post

on:
  workflow_run:
    workflows: ["ai review collect"]   # ⚠️ 必須與上面那支的 name: 完全一致
    types: [completed]

permissions:
  contents: read
  pull-requests: write # 貼 review comment
  actions: read # 下載上一段的 artifact

jobs:
  post:
    uses: tznthou/deepseek-code-review/.github/workflows/reusable-ai-review-post.yml@v1
    secrets:
      DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
      # 選填。沒設這個 secret 就是空字串，不掃，行為與不寫這行一樣
      REVIEW_BLOCKED_TERMS: ${{ secrets.REVIEW_BLOCKED_TERMS }}
```

---

## 四個最容易踩的坑

**1. `.github/` 一定要在 repo 根目錄。** GitHub Actions 只掃
`<repo-root>/.github/workflows/`。放在子目錄下的 workflow **不會觸發、也不會報錯**，
`gh run list` 是空的但沒有任何錯誤訊號。這個 kit 自己就因此「未驗證」了三天。

**2. `ai-review-post.yml` 要先合併進 default branch，AI review 才會動。**
`workflow_run` 只認 default branch 上的 workflow 檔與名稱。還在 PR 分支上的話，
第二段永遠不會被觸發——而且一樣不會報錯。

**3. `workflows: ["ai review collect"]` 要填你自己那支的 `name:`，不是檔名。**
兩邊不一致的症狀同樣是「第二段安靜地不動」。

**4. caller 自己的 `permissions:` 不能省——省了會 `startup_failure`。**
被呼叫的 workflow 拿不到超過呼叫方的權限。你的 caller 沒宣告時用的是 repo 預設
（新 repo 通常是 read-only），而 reusable 裡的 job 要求 `pull-requests: write`、
`security-events: write`，**超出上限就在啟動階段直接失敗，連一個 job 都不會出現**。

這個失敗從 CLI 查不出來：`gh run view` 只說「This run likely failed because of a workflow
file issue」，`--log-failed` 是空的，`actionlint` 也驗不出來——因為 workflow 檔案
本身沒有任何語法問題。**原因寫在網頁上那個 run 頁面的 Annotations**，例如：

```
The nested job 'review' is requesting 'actions: read, pull-requests: write', but is only allowed 'actions: none, pull-requests: none'.
```

2026-09-20 實測，上面三份範本的 `permissions:` 區塊都是照這個踩出來的，照抄就不會遇到。

> 對照組：只要 `contents: read` 的 `ai review collect` 在沒宣告 permissions 時
> 照樣跑得動——**所以你可能會看到一部分 workflow 正常、一部分整個不啟動**。
> 如果是**全部**不啟動、連 collect 也是，先查「第 2 步」最後一節的 Actions 政策：
> CLI 上的訊息一模一樣，只有 Annotations 分得出來。

---

## 客製：rubric 比換模型重要

實測結論：**把你這個 repo 常踩的坑寫進 rubric，比換模型有效得多。**
不客製的話 review 會淨是通用意見。

在你的 repo 放一份 rubric，然後在 caller 指過去：

```yaml
  post:
    uses: tznthou/deepseek-code-review/.github/workflows/reusable-ai-review-post.yml@v1
    with:
      rubric-path: .github/review-rubric.md    # 你自己那份
    secrets:
      DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
      REVIEW_BLOCKED_TERMS: ${{ secrets.REVIEW_BLOCKED_TERMS }}
```

⚠️ 用自訂 rubric 時特別注意：**rubric 也在掃描範圍內**。你自己那份 rubric 裡若寫了
內部代號當例子，一樣會被攔下——那是刻意的，它跟 diff 走同一個 request 送出去。

照著 `prompts/review-rubric.md` 改。⚠️ **那份檔案整份就是 system prompt**——
不要在裡面寫給人看的註解或元評論，它會進 prompt 並影響行為（實測過）。

---

## 其他可調的地方

`reusable-static-review.yml`

| input | 預設 | 說明 |
|---|---|---|
| `lint-command` | `''` | 留空則不跑 reviewdog |
| `lint-errorformat` | `%f:%l:%c: %m` | linter 輸出格式 |
| `skip-dependency-review` | `false` | 沒有依賴清單時設 true |

`reusable-codeql.yml`

| input | 預設 | 說明 |
|---|---|---|
| `languages` | **必填** | JSON 陣列字串 |
| `build-mode` | `none` | 編譯式語言改 `autobuild` |
| `skip-trivy` | `false` | |

`reusable-ai-review-post.yml`

| input | 預設 | 說明 |
|---|---|---|
| `rubric-path` | `''` | 你自己的 rubric，留空用內建 |
| `model` | `deepseek-v4-pro` | 只有這個與 `deepseek-flash` 是合法值 |
| `min-confidence` | `0.7` | 低於此信心的 finding 不貼 inline。內建 rubric 會直接告訴模型「0.7 以上貼成行內留言」，改了這個值，rubric 那句不會跟著變 |
| `max-inline` | `8` | 其餘降級進摘要 |
| `typed-rules` | `true` | 依 diff 涵蓋的檔案型態附加補充規則（目前有 GitHub workflow、Python 兩份）。**不增加 API 呼叫次數** |

### 曾經有一層「自動過濾誤報」，實測後移除了

`v1.1.0` 加過一個 `filter-findings`：第二次呼叫模型，刪掉「diff 裡有某一行字面反駁它」
的 finding。用 [AACR-Bench](https://huggingface.co/datasets/Alibaba-Aone/aacr-bench)
的 700 則人工標註 comment 實測之後移除了：

| | 錯誤的 comment | 正確的 comment |
|---|---|---|
| 被刪掉 | 4（刪對） | **15（誤刪）** |
| 保留 | 187 | 494 |

**誤刪是刪對的 3.75 倍**，precision 從 72.71% 掉到 72.54%。15 筆誤刪裡 9 筆是實質的
程式缺陷——括號不匹配、陣列重複項導致某個分支永遠不執行、變數賦值錯誤。
那些被無聲吃掉的代價，遠高於留下幾筆雜訊。

評估工具留在 `tools/eval/`。你要試自己的想法，可以拿同一套資料量一次誤刪率：

```bash
gh workflow run eval-filter.yml \
  -f filter-prompt=path/to/your-filter.md \
  -f limit=20      # 試水溫約 $0.08；limit=0 全跑 140 個 PR 約 $0.40
```

⚠️ 動手前先算一件事：**你的過濾規則射程內，「不該刪的」和「該刪的」比例是多少？**
我們事後才發現那個比例是 3.6:1（對的比錯的多三倍），而實測誤刪比是 3.75:1 ——
**射程內的組成，比模型的判斷力更早決定了上限**。這個估算不用花錢，只要有標註資料。

---

`reusable-ai-review-collect.yml`

| input | 預設 | 說明 |
|---|---|---|
| `max-diff-bytes` | `400000` | 在檔案邊界截斷，不會切半個 hunk |

---

## 版本

`@v1` 是**浮動 major tag**：它跟著 v1.x.x 發版移動（同 `actions/checkout@v4` 的慣例），
所以你不必為了拿到修正而改任何東西——代價是**我們一發版你就跟著變**，只是變動的粒度
是「每次發版」而不是 `@main` 的「每個 commit」。兩者的差別是粒度，不是「穩定 vs 會變」。

要不要承擔這件事，取決於你信不信任我們不亂動那個 tag。我們的承諾（`v1` 內不移除 input、
破壞性變更進 v2）寫在 README §5 最後一節，連同我們自己破過一次的紀錄。

不想承擔就釘死：`@v1.3.1` 這種不可變 tag，或直接用 commit SHA（GitHub 官方對第三方
workflow 的建議做法）。功能完全一樣，代價是修正不會自動到你手上。

## 這套不會幫你做的事

* **AI review 的 finding 不要直接採信。** 它位置通常對、推論不一定對，而且同一個位置
  重跑會給出不同的理由。定位是粗篩，每筆都要實跑驗證。
* **不要把 AI review 設成 required status check**，不要給它擋合併的權力。
  要擋就擋在 `reusable-static-review` 那三個確定性檢查上。
* **bot 開的 PR 一樣會觸發。** Renovate、Dependabot 開的依賴更新 PR 也會送去 review；
  目前沒有依作者跳過的選項（draft PR 預設會跳過：`skip-draft` 預設 `true`）。
* **大 PR 只審前 400 KB。** diff 超過 `max-diff-bytes`（預設 400000）時會在檔案邊界截斷，
  截斷點之後的檔案不會被審（見上面「其他可調的地方」）。
* **fork PR 的隔離路徑只驗過兩條。** 2026-09-21 實測通過的是「PR 改不動受信任段」
  與「artifact 內容不被採信」——那兩條不分 fork 還是同 repo 分支，行為相同（見 README §5）。
  **還沒驗的是 fork 專屬的部分**：外部貢獻者的核可政策實際跑起來長什麼樣。
  要收外部 PR 的話，這一段請自己先在你的 repo 上試一次。
