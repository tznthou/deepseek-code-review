# 導入 Checklist — deepseek-code-review

> 適用於 `code-review-kit/`。每一項都標了「檔案:行號」與「不做會怎樣」。
> 勾選方式：`- [ ]` → `- [x]`。

---

## 0. 前置：先確認你有這些東西

- [ ] **DeepSeek API key**（https://platform.deepseek.com/api_keys）— 走 `04` 才需要
- [ ] **目標 repo 的 admin 權限** — 要設定 secrets 與 branch protection
- [ ] **決定要走哪幾層**：
  - 只要靜態檢查 → 只複製 `01`（+ 可選 `02`）
  - 要 AI review、repo 有 fork PR → `01` + `02` + `03` + `04`
  - ⛔ `05` 評估後不建議採用（理由見 README §4.6），下面所有 `05` 相關項目可整段跳過
- [ ] **決定 AI review 的定位**：只是「參考意見」，還是要能影響合併？（建議前者，見 §5）

---

## 1. 必做 — 不做就跑不起來

- [ ] **加入 repo secret `DEEPSEEK_API_KEY`**
  - 位置：Repo → Settings → Secrets and variables → Actions → New repository secret
  - 不做會怎樣：`04` / `05` 直接失敗（`deepseek_review.py` 偵測不到 key 會 `return 1`）

- [ ] **確認 `03-ai-review-collect.yml` 已合併進 default branch**
  - 位置：`.github/workflows/03-ai-review-collect.yml`
  - 為什麼：`workflow_run` **只認 default branch 上的 workflow 檔與名稱**（`04-ai-review-post.yml:19` 的 `workflows: ["03 ai review collect"]`）
  - 不做會怎樣：`04` **永遠不會被觸發**，你會以為 AI review 壞了 —— 這是最容易漏的一項
  - 驗證：合併後在 Actions 頁面確認 `04 ai review post` 曾出現過一次 run

- [ ] **把 `01` 的 linter 換成你們的**
  - 位置：`.github/workflows/01-static-review.yml:48`（`# TODO: 換成你的 linter`）
  - 現況：範例是 `shellcheck` 掃所有 `*.sh`
  - 不做會怎樣：若 repo 沒有 shell script，這步等於空跑（不會壞，但沒有價值）
  - 也可以改用官方包好的 action：`reviewdog/action-eslint@v1`、`action-hadolint@v1`、`action-rubocop@v1`

- [ ] **把要複製的檔案放進 repo**
  ```bash
  cd ~/Documents/deepseek-code-review/code-review-kit
  cp -R .github  /path/to/your-repo/
  cp -R prompts  /path/to/your-repo/
  cp -R tools    /path/to/your-repo/
  cp    review-local.sh /path/to/your-repo/

  # .gitignore 用附加、不要覆蓋目標 repo 既有規則
  cat  .gitignore >> /path/to/your-repo/.gitignore
  ```
  - ⚠️ **最後一行別跳過**：2026-09-20 實測，少了那幾條規則時 `.env`、`*.key`、
    `.DS_Store`、`.claude/` 會被 `git add -A` 直接收進 repo——而這個 kit 正好需要一把 API key
  - 不做會怎樣：`tools/` 漏掉的話 `selftest.py` 與 `check-dsh-version.py` 不在手邊，
    之後想驗證時得回頭找

---

## 2. 依 repo 語言必改

- [ ] **`02-codeql.yml:34`** — `language: [javascript-typescript]` 換成你們的語言
  - 可用值：`javascript-typescript`、`python`、`go`、`java-kotlin`、`c-cpp`、`csharp`、`ruby`、`swift`…
  - 多語言就寫成 `[go, python]`（矩陣會平行跑）

- [ ] **`02-codeql.yml:39`** — `build-mode: none` 的調整
  - 直譯式語言（JS/TS、Python、Ruby）：維持 `none`
  - 編譯式語言（Go/Java/C++/C#/Swift）：改成 `autobuild`，或改成手動 build 步驟

- [ ] **`02-codeql.yml` 的排程時間**（`cron: '27 3 * * 1'`）
  - 如果你的 repo 在尖峰時段 CI 很擠，避開整點

---

## 3. GitHub 端設定

- [ ] **把三個確定性檢查設為 required status check**
  - 位置：Settings → Branches / Rulesets → Require status checks to pass
  - 要勾的 job 名稱：`reviewdog (diff-only)`、`gitleaks`、`dependency review`
  - **AI review 先不要設 required**（理由見 §5）
  - ⚠️ 注意：required check 必須**過去七天內在同 repo 成功跑過一次**；且必須在**最新 commit SHA** 上通過

- [x] ~~**建立 label `review:deep`**~~ — **整項跳過，`05` 不建議採用（README §4.6）**
  - 順帶記下這條教訓：label 觸發的品質關卡實測等於不會跑。同帳號下另一個 repo 的
    label 觸發 workflow，**22 次執行紀錄裡 19 次 skipped、3 次 cancelled、0 次跑完**，
    因為沒有人記得加那個 label。**要跑就自動觸發，別靠人類自律。**

- [ ] **確認沒有 workflow 用 `paths:` 過濾卻同時是 required check**
  - 為什麼：workflow 因 path filter **根本沒被觸發**時，其 check 會停在 `Pending`，**永久擋住 PR**
  - 注意區別：**被 skip 的 job** 回報 `success`（不擋）；**沒觸發的 workflow** 才是 Pending

- [ ] **public repo：檢查 fork approval policy**
  - 位置：Settings → Actions → Fork pull request workflows
  - 決定來自 fork 的 PR 要不要人工核可才跑 workflow

- [ ] **（可選）建立 environment `ai-review`**
  - 只在你要「貼留言前人工核可」時需要：把 `04-ai-review-post.yml:31` 的 `# environment: ai-review` 取消註解
  - 並在 Settings → Environments 設定 required reviewers

---

## 4. 品質與穩定性

- [ ] **先在本機驗證 review 品質，再開 CI**（最省時間的一步）
  ```bash
  cd /path/to/your-repo
  export DEEPSEEK_API_KEY=sk-xxxx
  /path/to/review-local.sh origin/main
  ```
  - 建議對 **3–5 個歷史 PR** 跑一次，看它有沒有抓到你們真正在意的問題
  - 不做會怎樣：你會在 CI 上反覆燒 token 做 prompt 調校，每次都要等 workflow

- [ ] **確認模型與 thinking 設定**（不確認就不能用）
  - 位置：`.github/scripts/deepseek_review.py` 的 `DEFAULT_MODEL` 與 `--thinking`
  - kit 預設：`deepseek-v4-pro` + `--thinking disabled`
  - 不做會怎樣：thinking 沒關的話 reasoning 會吃光 `max_tokens`，
    模型回傳**空字串**、exit code 2，而費用照算。這不是偶發，diff 稍有複雜度就必中
  - 可用模型只有 `deepseek-flash` 與 `deepseek-v4-pro` 兩個；`deepseek-v4.1-flash` 不存在（回 400）
  - 改用 flash 的話記得把 `--min-confidence` 降到 0.6（它自評普遍落 0.55–0.75）

- [ ] **客製化 `prompts/review-rubric.md`**（影響最大的一步）
  - 這是整個 AI review 品質的來源，`04` 與 `05` 都靠它
  - 建議加入：你們的禁區（例如「不可在 handler 直接寫 SQL」）、必須遵守的約定、已知的歷史坑
  - 不做會怎樣：**只會拿到泛泛的通用意見**。實測同一份 diff、同一個模型，
    加一段專案禁區後從漏報變成抓到，而且 findings 從 4 筆降到 2 筆、信心從 0.6–0.8 升到 0.85–0.9
  - 為什麼差這麼多：diff-only 的 review 看不到「不在 diff 裡的前提」。
    測試用的那個缺陷要看出來，得先知道「這支 script 會被 source 進互動 shell」，
    而那句話寫在檔案開頭第 4 行，不在該次 diff 範圍內
  - ⚠️ 反面風險：rubric 等於告訴模型「這個 repo 常犯 X」，它會傾向找 X，
    而你因為知道自己常犯 X 也會傾向相信。**命中已知模式的 finding 更要驗，不是更可信**
  - ⚠️ **保持檔案內容穩定**：穩定的前綴會命中 DeepSeek 的 context caching（cache hit 單價是 cache miss 的 1/30）

- [x] ~~**確認並 pin `05-dsh-agent-review.yml` 的 `DSH_VERSION`**~~ — **整項跳過，`05` 不建議採用（README §4.6）**
  - 下面的版本對照仍保留作為評估紀錄：它本身就是「不該把 CI 押在 developer preview 上」的證據
  - kit 已預設 `0.1.5-rc.1`（2026-09-17 查到的 CLI `latest`）
  - 查詢目前版本：`npm view @deepseek-ai/dsh dist-tags`
  - ⚠️ **monorepo 的 dist-tag 不一致，只看一個數字會誤判**：

    2026-09-17 首查：

    | 套件 | latest | next | alpha |
    |---|---|---|---|
    | `@deepseek-ai/dsh`（CLI，**CI 要 pin 這個**） | 0.1.5-rc.1 | 0.1.5-rc.2 | 0.1.6-alpha.1 |
    | `@deepseek-ai/dsh-agent`（元件） | 0.1.0-rc.6 | 0.1.5-rc.2 | 0.1.6-alpha.1 |

    2026-09-19 複查，**兩天內 latest 與 alpha 都動了**：

    | 套件 | latest | next | alpha |
    |---|---|---|---|
    | `@deepseek-ai/dsh`（CLI） | **0.1.5-rc.2** | 0.1.5-rc.2 | **0.1.6-alpha.2** |
    | `@deepseek-ai/dsh-agent`（元件） | 0.1.0-rc.6 | 0.1.5-rc.2 | **0.1.6-alpha.2** |

    這張表本身就是「為什麼不要用浮動版本」的證據——兩天一版，而且 CLI 的 latest
    直接追上了原本的 next。

  - 要穩定 → 用 CLI 的 `latest`；想嘗鮮 → `next`。**不要用浮動版本**（developer preview）
  - 升版後建議重跑一次 `npx -y @deepseek-ai/dsh@<ver> --profile headless --dump-default-config` 確認 profile 結構沒變

- [ ] **（資訊）你這個對話的 runtime 版本不是你能控制的**
  - 這個 Agent session 跑的是 **Cherry Studio 內建的 DSH 元件**，版本綁在 app 裡，無法單獨升級
  - 查法：`python3 tools/check-dsh-version.py`（會同時比對 npm 上的最新版）
  - 2026-09-17 實測：Cherry Studio app `2.0.14`（當時最新），內建 DSH 元件 `0.1.0-rc.7`（**不是**最新）
  - ⚠️ **不要用對話中觀察到的 dsh 行為當成 CI 上的基準** —— 兩者版本不同

- [ ] **把 action 版本 pin 到 commit SHA**
  - kit 內的版本**已於 2026-09-17 對照 GitHub API 驗證為當時最新**，且已確認用到的 inputs 仍存在：
    `actions/checkout@v7`、`actions/setup-node@v7`、`actions/cache@v6`、
    `actions/upload-artifact@v7`、`actions/download-artifact@v8`、
    `actions/dependency-review-action@v5`、`github/codeql-action@v4`（子動作分別驗證）、
    `gitleaks/gitleaks-action@v3`、`reviewdog/action-setup@v1`
  - ⚠️ `aquasecurity/trivy-action` 的 tag **有 `v` 前綴**（`v0.36.0`）；寫成 `0.36.0` 會找不到 ref
  - 你只需要決定是否進一步 pin 到 commit SHA（供應鏈要求）

---

## 5. 選擇性 — 可跳過，但請先看過理由

- [ ] **讓 AI 有否決權（我不建議）**
  - 做法：`04-ai-review-post.yml` 的 `post_review.py` 呼叫加上 `--request-changes-on-blocker`
  - 不建議的理由：模型輸出有變異性，把 merge 權交給它會製造偽陽性阻塞；而且 PR 內容是攻擊者可寫的輸入（prompt injection 可能讓它濫發 request-changes）
  - 若真要開：只讓 `blocker` 有否決權，且明訂「AI 意見可被人工覆寫」的流程

- [ ] **成本／雜訊微調**
  - `--min-confidence 0.7`（預設）：調高 → 更少雜訊、可能漏報
  - `--min-severity minor`（預設）：調成 `major` → 只報重要問題
  - `--max-inline 8`（預設）：最多貼幾則 inline，其餘摺進摘要
  - `03-ai-review-collect.yml` 的 `head -c 400000`：diff 截斷上限

- [ ] **`02-codeql.yml` 的 Trivy job**：若你們不做容器/依賴掃描，可整段刪掉

- [ ] **完全跳過 `05`**：只想要輕量路線的話，不要複製 `05-dsh-agent-review.yml`，`01`~`04` 自成一套

---

## 6. 建議的上線順序

### Day 1 — 確定性檢查（零 AI 成本、零風險）

- [ ] 完成 §1 的第 4 項（複製檔案，但先不要複製 `05`）
- [ ] 完成 §2（語言設定）
- [ ] 完成 §1 的 linter 替換
- [ ] 進 §3：把三個檢查設為 required
- [ ] **觀察一週**：確認沒有造成偽陽性阻塞

### Day 2 — AI review（先本機、後 CI）

- [ ] 完成 §1 的第 1 項（API key）
- [ ] 完成 §4 的「本機驗證」「模型／thinking 確認」「rubric 客製」三項
      —— 順序就照這個走，**沒關 thinking 的話本機驗證會直接拿到空字串**
- [ ] 複製 `03`、`04`，**合併進 default branch**
- [ ] 完成 §1 的第 2 項（驗證 `04` 有被觸發）
- [ ] **用一個 fork PR 實測**：確認收集段有跑、回報段有跑、**而且 fork 真的拿不到 secret**

### Day 3 — 按需的深度審查

- [ ] 複製 `05`，完成 §4 第 3 項（pin 版本）
- [ ] 完成 §3 的 label 建立
- [ ] 寫一份 repo 專屬的 `AGENTS.md`（團隊慣例、禁區）—— `dsh` 會自動載入
- [ ] 觀察成本，決定是否把 rubric 擴充成 dsh skills

---

## 7. 怎麼確認每一層真的成功

| 層 | 成功的樣子 | 怎麼驗證 |
|---|---|---|
| `01` | PR 上出現 inline comment，或 check 變紅 | 故意推一個有小問題的 commit；確認 reviewdog 只對**變更行**留言 |
| `02` | Actions 跑完後，Security → Code scanning 出現 alert | 看 SARIF 是否上傳成功（缺 `security-events: write` 會 403） |
| `03` | artifact `ai-review-input` 產生 | Actions run 頁面下載 artifact 看 `pr.diff` 內容 |
| `04` | PR 出現 `🤖 DeepSeek Code Review` 留言 | 看 `04` 的 run log：`[info] findings=N inline=M skipped=K` |
| `05` | PR 出現 `<!-- dsh-review -->` 標記的留言 | 看 debug artifact 裡的 `dsh-stderr.log` |

**健康指標（建議每月看一次）**
- AI review 的**偽陽性率**：被 dismiss 的 finding 比例
- **漏報案例**：人工 reviewer 抓到但 AI 沒抓到的問題類型 → 回饋進 rubric

---

## 8. 常見失敗與處理

| 症狀 | 原因 | 處理 |
|---|---|---|
| **模型回空字串、exit 2（「回應中找不到 JSON 物件」）** | thinking 沒關，reasoning 吃光 `max_tokens`（`finish_reason=length`） | 確認有 `--thinking disabled`；要保留 reasoning 就把 `--max-tokens` 拉到 65536 以上 |
| 模型名稱回 HTTP 400 | 只有 `deepseek-flash` 與 `deepseek-v4-pro` 兩個有效名稱 | `deepseek-v4.1-flash` 不存在（`deepseek-flash` 本身就是 V4.1-Flash） |
| review 淨是通用意見、抓不到真正在意的問題 | rubric 沒寫專案禁區 | 見 §4 的 rubric 客製那條，這是影響最大的一項 |
| `04` 完全沒被觸發 | `03` 不在 default branch，或 workflow 名稱不符 | 確認 `04:19` 的 `workflows: ["03 ai review collect"]` 與 `03` 的 `name:` 完全一致 |
| `04` 執行但找不到 PR | commit 不屬於任何 PR（例如 direct push） | 這是預期行為，腳本會 `exit 0` |
| inline comment 貼不上去（422） | 行號不在 diff hunk 內 | `post_review.py` 已做行號驗證並降級進摘要；確認有傳 `--diff` |
| review 重複貼好幾次 | `04` 用 `gh pr review --comment`，每次 push 新增一則 | 想單一留言：改成 `gh pr comment --edit-last --create-if-none`（`05` 已這樣做） |
| `05` 永遠不跑 | 沒有 label `review:deep` | 建立 label 並加到 PR 上 |
| `05` 工具呼叫被拒 | headless 無互動審批通道，fail-closed | 確認 agent 只需唯讀權限；寫檔交給 shell（`> review.md`） |
| `05` 說 `SANDBOX_UNAVAILABLE` | runner 容器缺 bwrap/Landlock | 唯讀工具通常不受影響；需要寫入請改走 `04` |
| CodeQL 上傳 SARIF 失敗 403 | 缺 `security-events: write` | 補上權限（`02` 已設定，確認沒被你們改掉） |
| required check 卡在 Pending | workflow 沒被觸發（`paths:` 過濾） | 移除 path filter，或改用 always-run 的 gate job |

---

## 9. 已驗證 vs 未驗證（誠實聲明）

**已在本機驗證**
- [x] `python3 tools/selftest.py` → 9 項全通過（diff 行號解析、finding 正規化、JSON 解析容忍、截斷、Markdown 產生、行號過濾）
- [x] 5 個 workflow YAML 全部可被解析
- [x] Python / Bash 語法檢查通過
- [x] 檔案複製到 `~/Documents` 後內容一致、自測仍通過
- [x] **所有 action 版本與 inputs**：2026-09-17 首驗、2026-09-19 複驗，皆以 GitHub API
      （`releases/latest`、`matching-refs/tags`）與 `raw action.yml` 逐一實測 —— 首驗時因此**修掉一個真 bug**：
      trivy-action 的 tag 需 `v` 前綴。複驗結果十項全數仍為最新
- [x] **DSH 版本三層比對**：`tools/check-dsh-version.py` 可解析 app.asar 取出內建元件版本，並比對 npm dist-tags
- [x] **對真實 DeepSeek API 端到端執行**（2026-09-19／20）：12 次呼叫、5 個真實歷史 commit 當標的、
      總花費 $0.08。涵蓋 TypeScript／React、Rust、Shell 三種標的，以及一次「拿已修好的正確 code 餵它」
      的假陽性測試（0 findings、判定 approve）。**這一條在 09-17 的版本裡還是「未驗證」**
- [x] **`post_review.py` 的行號驗證與過濾**：用真實 findings 走過 `--dry-run`，
      5 筆經門檻與 hunk 檢查後剩 1 筆可貼 inline，其餘正確降級進摘要
- [x] **`.gitignore` 攔截範圍**：建臨時 repo 實測，補上 `.env` / `*.key` / `.claude/` / `.DS_Store` 四類

**未驗證（需要你的環境）**
- [ ] 未在**真實 GitHub repo / PR** 上跑過任何 workflow。未驗的是機制不是品質：
      `workflow_run` 觸發鏈、fork PR 隔離路徑、inline comment 實際貼上 PR 的行為
- [ ] `05` 的 `dsh` 旗標來自官方 CLI README 與原始碼，未在本機執行驗證。
      **09-17 到 09-19 兩天內 npm `latest` 就從 `0.1.5-rc.1` 跳到 `0.1.5-rc.2`**，升版前務必重驗
- [ ] 模型價格隨官方調整，以 https://api-docs.deepseek.com/quick_start/pricing 為準

**已知的不穩定**
- ⚠️ 同一份 diff、同樣 `temperature 0.2`，**兩次跑出的 findings 不一樣**；第二次還冒出第一次沒有的問題。
      「跑一次沒報」不等於「沒問題」，也別把它當可重現的閘門

**因此第一次上線的順序是**：§1 第 1 項（API key）→ §4 的模型／thinking 確認 →
§4 的 `review-local.sh` 本機驗證與 rubric 客製 → 才進 CI。不要跳過本機驗證那一步。
