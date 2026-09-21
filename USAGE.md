# 在別的 repo 用這套 code review

複製三個檔案、設一把 key、開一個開關。**不用複製腳本，也不用複製 rubric**——
邏輯留在這個 repo，你那邊只放引用。這個 repo 改了，你下次跑就是新版。

> 這份是最短路徑。每一項「為什麼」與踩過的坑在 `SETUP-CHECKLIST.md`。

---

## 第 1 步：設 secret

Repo → Settings → Secrets and variables → Actions → New repository secret

| Name | 去哪拿 |
|---|---|
| `DEEPSEEK_API_KEY` | https://platform.deepseek.com/api_keys |

**每個 repo 都要設自己的一把，費用算你自己的帳號。** GitHub 的 secret 綁 repo，
被引用的 workflow 只拿得到「呼叫方」的 secret——所以這個 kit 碰不到你的 key，
你也花不到別人的額度。

或用指令（不會留在 shell history）：

```bash
gh secret set DEEPSEEK_API_KEY --repo <owner>/<repo>
```

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

## 第 3 步：放三個檔案

### `.github/workflows/code-review.yml`

確定性檢查 + SAST，不花 AI token。

```yaml
name: code review

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

# ⚠️ 這段不能省，理由見下面「三個最容易踩的坑」的第 4 點
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

這個失敗特別難查：`gh run view` 只說「This run likely failed because of a workflow
file issue」，`--log-failed` 是空的，`actionlint` 也驗不出來——因為 workflow 檔案
本身沒有任何語法問題。2026-09-20 實測，上面三份範本的 `permissions:` 區塊都是照這個
踩出來的，照抄就不會遇到。

> 對照組：只要 `contents: read` 的 `ai review collect` 在沒宣告 permissions 時
> 照樣跑得動——**所以你可能會看到一部分 workflow 正常、一部分整個不啟動**。

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
```

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
| `min-confidence` | `0.7` | 低於此信心的 finding 不貼 inline |
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

`@v1` 是穩定 tag。想跟最新改動用 `@main`，但那代表這個 repo 一改你就跟著變——
正式環境建議 pin tag 或 commit SHA。

## 這套不會幫你做的事

* **AI review 的 finding 不要直接採信。** 它位置通常對、推論不一定對，而且同一個位置
  重跑會給出不同的理由。定位是粗篩，每筆都要實跑驗證。
* **不要把 AI review 設成 required status check**，不要給它擋合併的權力。
  要擋就擋在 `reusable-static-review` 那三個確定性檢查上。
* **fork PR 的隔離路徑還沒驗過。** 兩段式架構的設計目的就是它，但驗證需要第二個帳號。
  在你自己驗過之前，別把這套裝到會收外部 PR 的 repo 上。
