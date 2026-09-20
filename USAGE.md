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

## 第 3 步：放三個檔案

### `.github/workflows/code-review.yml`

確定性檢查 + SAST，不花 AI token。

```yaml
name: code review

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

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

jobs:
  post:
    uses: tznthou/deepseek-code-review/.github/workflows/reusable-ai-review-post.yml@v1
    secrets:
      DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
```

---

## 三個最容易踩的坑

**1. `.github/` 一定要在 repo 根目錄。** GitHub Actions 只掃
`<repo-root>/.github/workflows/`。放在子目錄下的 workflow **不會觸發、也不會報錯**，
`gh run list` 是空的但沒有任何錯誤訊號。這個 kit 自己就因此「未驗證」了三天。

**2. `ai-review-post.yml` 要先合併進 default branch，AI review 才會動。**
`workflow_run` 只認 default branch 上的 workflow 檔與名稱。還在 PR 分支上的話，
第二段永遠不會被觸發——而且一樣不會報錯。

**3. `workflows: ["ai review collect"]` 要填你自己那支的 `name:`，不是檔名。**
兩邊不一致的症狀同樣是「第二段安靜地不動」。

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
