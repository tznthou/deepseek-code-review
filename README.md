# code-review-kit — GitHub PR 自動化 Code Review 起手包

一份可以直接放進 repo 的實作範本：**便宜的先跑（linter/SAST），貴的才跑（LLM），
而且 fork PR 也安全。**

[![latest release](https://img.shields.io/github/v/release/tznthou/deepseek-code-review?style=flat-square&label=latest)](https://github.com/tznthou/deepseek-code-review/releases)
[![selftest](https://img.shields.io/badge/selftest-49%20passing-brightgreen?style=flat-square)](tools/selftest.py)
[![license](https://img.shields.io/github/license/tznthou/deepseek-code-review?style=flat-square)](LICENSE)

導入只要三步驟、三個檔案，不必複製腳本也不必複製 rubric——
邏輯留在這個 repo，你那邊只放引用（`@v1` 是浮動 tag，這邊修好下次就送到）。
**完整做法見 [`USAGE.md`](USAGE.md)。**

```bash
$ ./review-local.sh origin/main          # 本機先試一次，不碰 GitHub
[info] 呼叫 https://api.deepseek.com / deepseek-v4-pro（diff 43788 字元、thinking=disabled）
[info] 完成於 10.9s ｜ findings=3 ｜ relocated=2 ｜ verdict=comment
```

### 它在什麼標的上有用

命中率**由標的型態決定，不是由模型決定**（完整數據見 §4）：

| 標的 | 實測 | 建議 |
|---|---|---|
| GitHub workflow YAML | 4 筆裡 2 筆成立，都是該修的 bug（§8） | ✅ 目前最好的標的 |
| TypeScript／React（22 檔） | 引用的 code 逐字核對，零捏造 | ✅ |
| Rust（8 檔） | 提到的五個符號全部真實存在 | ✅ |
| Shell（6 檔） | `deepseek-flash` 4 個技術斷言錯 3 個；`v4-pro` 抓到真的參數驗證缺口 | ⚠️ 一定要用 `v4-pro`，且每筆實跑 |
| Markdown／文件（27 檔） | **16 筆只有 1 筆成立**，註解密度 51.7% | ⛔ 不要跑，會空手而回（§4.8） |

> 這張表的樣本是各一到兩次跑，**不是統計結論**。本工具不可重現（§8「已知的不穩定」），
> 方向可以參考，數字不要當指標。

### 這個 kit 對自己做過的兩件事

* **砍掉了自己加的一個功能。** 曾經有一層「第二次呼叫過濾誤報」，用 700 則人工標註
  資料實測後發現它**誤刪 15 筆正確的、只刪對 4 筆**，precision 反而變差 → 整個移除。
  評估工具留在 `tools/eval/`，任何人都能拿自己的 prompt 重跑（§8）。
* **不再相信模型報的行號。** 實測 16 筆 finding 只有 **1 筆**真的指向它自己引用的那段
  code，其餘偏移 +1 到 +24 行。現在行號由程式用程式碼片段文字比對算出（§8）。

⚠️ **兩個預設值不改就不能用**：模型要用 `deepseek-v4-pro`、thinking 要關掉（理由見 §4）。
kit 內都已經設好。

研究報告請看同一目錄的 `github-pr-cicd-code-review-research.md`。

---

## 1. 檔案總覽

```
deepseek-code-review/                        # repo 根目錄——kit 就跑在這裡（dogfood）
├── .github/
│   ├── codeql/codeql-config.yml            # CodeQL 查詢設定（security-and-quality + local threat model）
│   ├── scripts/
│   │   ├── deepseek_review.py              # diff → DeepSeek → review.md + findings.json（純標準庫）
│   │   ├── locate.py                       # 行號由片段文字比對算出，不信模型自報的（見 §8）
│   │   └── post_review.py                  # 驗證行號 → 冪等貼回 PR（摘要 + inline comments）
│   └── workflows/
│       ├── 01-static-review.yml            # ↓ 這五支是本 repo 自己的 caller（dogfood）
│       ├── 02-codeql.yml                   # CodeQL SAST + Trivy → SARIF → code scanning
│       ├── 03-ai-review-collect.yml        # 不受信任段：只產 diff artifact，零 secret
│       ├── 04-ai-review-post.yml           # 受信任段：workflow_run 觸發，呼叫模型並貼留言
│       ├── 05-dsh-agent-review.yml         # ⛔ 評估紀錄，不建議採用（見 §4.6）
│       ├── reusable-static-review.yml      # ↓ 這四支是給別的 repo 引用的實作（USAGE.md）
│       ├── reusable-codeql.yml             #   別人的 caller 用 @v1 指過來，不必複製腳本
│       ├── reusable-ai-review-collect.yml  #
│       ├── reusable-ai-review-post.yml     #
│       └── eval-filter.yml                 # 手動觸發：用 AACR-Bench 評估 prompt（§8）
├── prompts/
│   ├── review-rubric.md                    # 04 用的 review playbook（system prompt）
│   ├── rules/                              # 依 diff 的檔案型態附加的補充規則
│   │   ├── github-workflows.md             #   幾乎每條都是這個 repo 自己踩過的坑
│   │   └── python.md                       #
│   └── dsh-review-task.md                  # 05 用的 agent 任務指令
├── tools/
│   ├── selftest.py                         # 不需網路/API key 的自測（12 組 49 項）
│   ├── check-dsh-version.py                # 檢查內建 DSH 版本 vs npm 最新版
│   └── eval/                               # 用人工標註資料評估 prompt 的效果
│       ├── build_eval_set.py               #   下載 AACR-Bench + 抓 PR diff
│       └── eval_filter.py                  #   算誤刪率／抓錯率（prompt 自備）
├── review-local.sh                         # 本機跑一次 review，不碰 GitHub
├── USAGE.md                                # ⭐ 在別的 repo 導入這套（三步驟，主要路線）
├── CHANGELOG.md                            # 版本變更紀錄（含 v1 浮動 tag 的破壞性變更標記）
├── LICENSE                                 # MIT
├── ACKNOWLEDGMENTS.md                      # 借用了哪些設計想法，以及一則授權更正
├── SETUP-CHECKLIST.md                      # 逐項檢查表與每個坑的來龍去脈
├── README.md
└── github-pr-cicd-code-review-research.md  # 選型研究報告
```

---

## 2. 五分鐘導入

### 先選路線：引用，還是複製？

|  | **引用（建議）** | 複製 |
|---|---|---|
| 你那邊要放什麼 | 三個 caller 檔，每個十幾行 | 整個 `.github/` + `prompts/` + `tools/` |
| 腳本與 rubric | 留在這個 repo，用 `@v1` 指過來 | 你自己一份 |
| 這邊修 bug 之後 | **下次跑就是新版**（浮動 tag 自動送達） | 要自己同步 |
| 適合什麼時候 | 幾乎所有情況 | 你要改腳本本身，或不想依賴外部 repo |

**➡️ 引用路線的完整做法在 [`USAGE.md`](USAGE.md)**——三步驟、三份可直接複製的 caller，
本 repo 自己的 `01`–`04` 就是照那份寫的（dogfood），所以那些範例是實際在跑的東西。

下面是**複製路線**的步驟。步驟 2、4、5、6 兩條路線都適用。

### 步驟 1：複製檔案

從這個 repo 的根目錄複製過去（`<kit>` 是你 clone 本 repo 的位置）：

```bash
cp -r <kit>/.github  <your-repo>/
cp -r <kit>/prompts  <your-repo>/
cp -r <kit>/tools    <your-repo>/
cp    <kit>/review-local.sh <your-repo>/

# .gitignore 用「附加」不要覆蓋——目標 repo 多半已經有自己的規則
cat  <kit>/.gitignore >> <your-repo>/.gitignore
```

⚠️ 複製過去之後，`.github/workflows/` 裡那四支 `reusable-*.yml` 和 `eval-filter.yml`
對你沒用（前者是給別人引用的實作，後者是評估工具），可以刪掉。
MIT 授權要求保留版權聲明，所以 `LICENSE` 的內容請一併帶過去或在你的 NOTICE 裡標明。

⚠️ **最後那行別跳過。** 這個 kit 需要 `DEEPSEEK_API_KEY`，而 2026-09-20 實測：
沒有這幾條規則時，`.env`、`*.key`、`.DS_Store`、`.claude/` 全都會被 `git add -A` 直接收進去。

⚠️ **`.github/` 一定要落在目標 repo 的根目錄。** GitHub Actions 只掃
`<repo-root>/.github/workflows/`，放在子目錄下的 workflow **不會被觸發、也不會報錯**——
它就是安靜地什麼都不做。2026-09-20 本 repo 就是踩到這個才把 kit 從子目錄搬上來的。

### 步驟 2：設定 secret

Repo → Settings → Secrets and variables → Actions：

| Secret | 必要性 | 說明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 04 需要 | https://platform.deepseek.com/api_keys |
| `GITHUB_TOKEN` | 自動提供 | 不需手動設定 |
| `GITLEAKS_LICENSE` | 組織帳號才需要 | 個人 repo 可留空 |

### 步驟 3：改掉這幾個 TODO

| 檔案 | 要改什麼 |
|---|---|
| `01-static-review.yml` | `Run linter` 步驟換成你的 linter（輸出需為 `file:line:col: message`）；可改用 `reviewdog/action-eslint@v1` 等現成 action |
| `02-codeql.yml` | `matrix.language` 換成你的語言；編譯式語言把 `build-mode` 改成 `autobuild` |
| ~~`05-dsh-agent-review.yml`~~ | **不用改 —— 這條路線不建議採用（§4.6）。** 保留它是為了留下「為什麼不走」的評估紀錄 |
| 全部 workflow | 正式環境把 action 版本 pin 到 commit SHA |

### Action 版本對照表（2026-09-17 首驗、2026-09-19 複驗，皆以 GitHub API 實測）

kit 內的版本**已經對照官方最新版並驗證 inputs 存在**，不需再自己查一輪。
複驗結果：下表十項全數仍為最新，無需更動。

| Action | kit 使用 | 官方最新 | 備註 |
|---|---|---|---|
| `actions/checkout` | `@v7` | v7.0.1 | v7 起會拒抓 fork PR 的 head（我們本來就不抓） |
| `actions/setup-node` | `@v7` | v7.0.0 | |
| `actions/cache` | `@v6` | v6.1.0 | |
| `actions/upload-artifact` | `@v7` | v7.0.1 | |
| `actions/download-artifact` | `@v8` | v8.0.1 | 跨 run 下載用的 `run-id` + `github-token` 仍存在 |
| `actions/dependency-review-action` | `@v5` | v5.0.0 | |
| `github/codeql-action` | `@v4` | v4.38.0 | 浮動 `v4` 標籤存在；子動作需分別驗證 inputs |
| `aquasecurity/trivy-action` | `@v0.36.0` | v0.36.0 | ⚠️ **tag 有 `v` 前綴**，寫成 `@0.36.0` 會失敗 |
| `gitleaks/gitleaks-action` | `@v3` | v3.0.0 | |
| `reviewdog/action-setup` | `@v1` | v1.5.0 | |

### 步驟 4：先在本機驗證 review 品質（最省時間的一步）

```bash
export DEEPSEEK_API_KEY=sk-xxxx
./review-local.sh origin/main
```

這會把 `origin/main...HEAD` 的 diff 送給 DeepSeek，印出 review。**先確認 prompt 的品質符合期待，
再開 CI** —— 否則你會在 CI 上反覆燒 token 做 prompt 調校。

### 步驟 5：把專案規範寫進 rubric（影響最大的一步）

實測發現：**改 rubric 的效果大過換模型**。同一份 diff、同一個模型，只在
`prompts/review-rubric.md` 尾端加一段「本專案的禁區」，結果從漏報變成抓到，
而且雜訊還少了一半（4 筆 → 2 筆，信心 0.6–0.8 → 0.85–0.9）。

原因是 diff-only 的 review 有個結構性盲區：**判斷所需的前提如果不在 diff 裡，它就看不到**。
測試用的那個缺陷要看出來，得先知道「這支 script 會被 source 進互動 shell」——
而那句話寫在檔案開頭第 4 行，不在這次的 diff 範圍內。

所以請把散落在 `AGENTS.md`、`CLAUDE.md`、檔案開頭註解裡的規範，挑會被違反的寫成禁區：

```markdown
## 本專案的禁區（優先於一般通則）

1. `scripts/*.sh` 會被 source 進使用者的互動 shell，任何外部命令
   （rm/grep/mv/cp/find…）都必須加 `command` 前綴，否則會被 alias 攔截。
   trap 字串裡的命令同樣適用——觸發時才 eval，屆時仍會展開 alias。
   看到裸的外部命令一律報 major。
2. 失敗必須可見：`2>/dev/null` 吞掉錯誤而呼叫端又不檢查 exit code 的寫法要報。
```

⚠️ 反面風險：rubric 等於告訴模型「這個 repo 常犯 X」，它就會傾向找 X，
而你因為知道自己常犯 X 也會傾向相信。**命中已知模式的 finding 更要驗，不是更可信。**

⚠️ 還有一個方向性的限制：**這招只在「給它 diff 裡看不到的前提」時有效**。
寫成「不要報 X 類問題」這種自我約束規則會無效，而且實測會讓誤報更難識破——見 §4.7。

### 步驟 6：設為 required status check

分支保護 / ruleset 裡把 `reviewdog (diff-only)`、`gitleaks`、`dependency review` 設為 required。
**AI review 先不要設 required**（見 §6）。

---

## 3. 每條路線在做什麼、要花多少錢

| Workflow | 觸發 | 需要 secret | 產出 | 相對成本 |
|---|---|---|---|---|
| 01 static | PR 開啟/更新 | 無 | inline comments、check 紅綠燈 | 極低（純 CI 分鐘） |
| 02 CodeQL | PR + 每週排程 | 無 | code scanning alerts、SARIF | 中（SAST 掃描較久） |
| 03 collect | PR 開啟/更新 | 無 | artifact（diff + metadata） | 極低（幾秒） |
| 04 post | 03 完成後 | `DEEPSEEK_API_KEY` | PR review + inline comments | **模型費用主體** |
| ~~05 dsh~~ | ~~label `review:deep`~~ | — | **⛔ 不建議採用，見 §4.6** | — |

### 模型費用估算

可用模型只有兩個（2026-09-19 實打 `GET /models` 確認）：`deepseek-flash`（即 V4.1-Flash）
與 `deepseek-v4-pro`。**`deepseek-v4.1-flash` 這個名稱不存在，填了回 HTTP 400。**

價格（USD / 1M tokens，離峰價；peak = 週一至週五 01:00–04:00 與 06:00–10:00 UTC，非離峰加倍）：

| 模型 | cache hit 輸入 | cache miss 輸入 | 輸出 |
|---|---|---|---|
| `deepseek-flash` | $0.003 | $0.15 | $0.60 |
| `deepseek-v4-pro`（kit 預設） | $0.022 | $0.66 | $1.98 |

實測單次費用（離峰）：

| PR 規模 | 輸入 tokens | flash | v4-pro |
|---|---|---|---|
| 小（~10 KB diff） | ~4k | ≈ $0.0012 | ≈ $0.0041 |
| 中（~34 KB diff） | ~11k | ≈ $0.0028 | ≈ $0.0094 |
| 大（~54 KB diff） | ~17k | ≈ $0.0035 | ≈ $0.0130 |

> 一個月 200 個 PR、平均中型、用 v4-pro → **約 $1.9/月**。
> 為什麼多付 4 倍仍然划算，見 §4。
> 有趣的對照：**在 private repo 上，GitHub Actions 的分鐘費往往比模型費用還高**
> （Linux 2-core 約 $0.006/分鐘，一個 5 分鐘的 job 就 ≈ $0.03）；
> public repo 的 standard runner 免費，所以這條路線幾乎等於免費。

### 省錢的七個開關（kit 內已預設開啟）

1. `--thinking disabled` — **這條不只是省錢，是不關就不能用**（見 §4）
2. `if: github.event.pull_request.draft == false` — draft PR 不跑
3. `concurrency: cancel-in-progress: true` — 連續 push 只跑最後一次
4. diff 截斷上限 400 KB（`--max-diff-chars`）
5. `--min-confidence 0.7` + `--min-severity minor` — 過濾雜訊
6. `--max-inline 8` — 最多貼 8 則 inline，其餘摺進摘要
7. prompt 前綴穩定（rubric 放檔案、固定順序）→ 吃到 cache hit 價（1/30）

> 第 5 項的門檻是為 `deepseek-v4-pro` 校準的（它自評落在 0.7–0.9）。
> **改用 flash 就要把 `--min-confidence` 降到 0.6**：flash 自評普遍落在 0.55–0.75，
> 實測 5 筆只有 1 筆過得了 0.7 的門檻，被擋掉的其中一筆還是真的安全問題。

---

## 4. 實測結果（2026-09-19 ～ 09-21）

原始的品質評估是 **23 次真實 API 呼叫、7 個真實標的**（09-19／20，$0.43），
之後在真實 PR 上持續累積（未逐次計數）。**模型講的每一句話都另外驗證過**——
符號存在性回頭搜 diff、技術斷言全部實跑。

09-21 另外做了兩組更大的實驗，結論在 §8：

* **定位機制的紅綠對照**（n=16，零額外花費）：拿八組歷史 review artifact 離線重跑，
  比較「信模型報的行號」與「用程式碼片段文字比對算行號」。
* **`filter-findings` 的效果評估**（700 則人工標註 comment、160 次 API 呼叫、$0.48）：
  結論是負面的，該功能已停用。

⚠️ 底下 §4.1–§4.10 保留當時的原始觀察，其中兩處後來有更新：

* **§4.2 表格裡的「行號 5/5」「行號 4/4」是會誤導的指標。** 它量的是「行號落在 diff
  範圍內」＝ GitHub API 不會回 422，**跟「指的對不對」是兩件事**。後來用 16 筆真實
  finding 逐行核對，只有 1 筆真的指向它自己引用的那段 code。見 §8 的「可貼 ≠ 指對」。
* **§4.7／§4.9 記的「加要求自我約束的規則無效」後來拿到了更強的證據**——
  `filter-findings` 整份 prompt 都建立在自我約束上，700 則標註資料實測失敗。見 §8。

### 4.1 `max_tokens` 那個坑（不處理就 100% 失敗）

`deepseek-flash` 與 `deepseek-v4-pro` 都預設開啟 thinking，而 **reasoning tokens 與輸出共用
`max_tokens` 額度**。官方的預設值是「非 thinking 模式 8K、thinking 模式 64K」——
填了 8192 等於只給它八分之一空間，想完就沒額度寫答案了。

| 設定 | 結果 |
|---|---|
| `max_tokens=8192`（早期版本寫死） | reasoning 吃光 8192，`content` 回傳**空字串**，`finish_reason=length`，解析失敗而費用照算 |
| `thinking=high` + `max_tokens=32768` | 124 秒、$0.021、reasoning 用掉 31408，JSON **仍被截斷** |
| `--thinking disabled`（現行預設） | 8.8 秒、$0.003、一次過 |

失敗的樣子是「模型回空字串」，看起來像模型不聽話，實際上是額度用光——這是最誤導的一點。
要保留 reasoning 就得把 `--max-tokens` 拉到 65536 以上，但 code review 這類任務
reasoning 會吐十萬字元，不划算。

### 4.2 為什麼預設用 `deepseek-v4-pro`

同一份 diff、同樣關閉 thinking。

⚠️ 表格裡的「行號 N/N」只代表**行號落在 diff 範圍內**（貼得上去、API 不回 422），
**不代表指對了位置**。後來的實測顯示那兩件事差很多——見 §8。

| 標的 | `deepseek-flash` | `deepseek-v4-pro` |
|---|---|---|
| TypeScript + React | 9.5s／$0.0035／5 筆／行號 5/5 | 10.9s／$0.0130／3 筆／行號 3/3，多抓到一處防護缺口 |
| Shell | 8.8s／$0.0028／5 筆／**4 個技術斷言錯了 3 個** | 11.7s／$0.0094／4 筆／行號 4/4，抓到真的參數驗證缺口 |

pro 報得**少**但精度高、雜訊少，反而更適合 CI。價差 4 倍，但單次仍只要一分錢——
而「語氣篤定卻講錯機制」的代價比多付一分錢高得多。

### 4.3 三種失效形狀（所以不能當結論，只能當篩子）

| 模型 | 失效形狀 | 實例 |
|---|---|---|
| flash | **機制講錯**，語氣篤定 | 斷言某條件式對空字串會報錯、非數字會拋例外——實測都不會。而真正的風險（非數字被判定為真、安靜走錯分支）它反而沒提 |
| v4-pro | **定位對、後果誇大** | 指出某處可注入且屬實，但宣稱能刪整張表——實測連線是唯讀模式，刪除被拒，只有讀取型注入成立 |
| flash | **把自己的解析困難報成程式碼問題** | 巢狀 JSX 看不懂，就報「括號與縮排結構可疑，需確認能編譯」，而且給 `major`——見 §4.8 |

共通點：**位置通常是對的，推論不一定**。每筆 finding 都要實跑驗證再採信。

第四種失效形狀（**報作者已在註解寫明理由的刻意決策**）與它的防法，見 §4.8。

### 4.4 分語言適配性

| 語言 | 行號準確 | 判定 |
|---|---|---|
| TypeScript / React | 5/5 · 3/3 | 強 |
| Rust | 4/4 | 強 |
| Shell | 3/5（flash）· 4/4（pro） | 弱，需靠 §2 步驟 5 的專案禁區補 |

繁體中文輸出無失準，術語保留原文（不會把識別字硬翻）。

### 4.5 假陽性

拿**已經修好的正確 code** 餵給它：0 筆 finding、判定 approve、輸出只花 91 個 token。
它認得出「這段沒問題」，不會為了交差硬擠意見。

### 4.6 為什麼 `05` 評估後不建議採用

`05-dsh-agent-review.yml` 保留在 kit 裡是**評估紀錄**，不是推薦路線。兩個獨立理由，任一個都足以否掉它：

**一、依賴的 CLI 是 developer preview，漂移速度是兩天一版。**
2026-09-17 記錄 `DSH_VERSION=0.1.5-rc.1`，09-19 複查 npm `latest` 已跳到 `0.1.5-rc.2`。
官方明示會有破壞性變更 —— 等於把 CI 的穩定性押在每兩天換一次的地基上。

**二、label 觸發在實務上等於不會跑。**
這不是推測。同一個帳號下另一個 repo 的 `ai-review.yml` 同樣採 label 觸發，
以 GitHub API 查它的全部執行紀錄：

| 總執行數 | skipped | cancelled | 真的跑完 |
|---|---|---|---|
| 22 | 19 | 3 | **0** |

原因單純是那個 label 從來沒有人去加。**一個需要人類記得加 label 才會動的品質關卡，
實際效果是零。** 要用 AI review 就自動觸發，別靠人類的自律。

> 這條教訓不限於 `05`：任何「預設不跑、要手動開啟」的檢查都適用同一個折扣。

想做 AI review 走 `04`（diff → 一次 completion，實測單次約 $0.01）。
想要確定性檢查走 `01`/`02`，那兩條不外送任何內容到第三方。

### 4.7 rubric 的有效邊界：給資訊有效，要求自律無效

§2 步驟 5 說「改 rubric 的效果大過換模型」。這一節補上它**不成立**的那一半——
因為寫錯方向的 rubric 規則不只無效，還會讓誤報變得更難識破。

2026-09-20 的 2×2 實測，標的是另一個 TypeScript + React 專案的 PR
（142K 字元 diff／27 檔），同一份 diff 跑四次：

| | 原版 rubric | 加一條「不得報作者已寫明理由的決策」 |
|---|---|---|
| `deepseek-v4-pro` | 3 筆 → **1 筆成立** | 3 筆 → **0 筆成立** |
| `deepseek-flash` | 6 筆 → **0 筆成立** | 4 筆 → 形狀相同 |

**加了規則之後變差。** 而關鍵不在數字，在模型的反應方式：

- 加規則**前**，它的判斷依據寫「與註解中『……』的意圖不完全一致」
  ——**它讀了註解，而且引用了**，所以一眼看得出是誤報
- 加規則**後**，同一筆 finding 還在、信心一樣 `0.80`，但判斷依據**完全不提註解**，
  改成一個「未來可能改為非同步載入」的假設

**它學會的是把證據從論證裡拿掉，不是停止報告。** 而且那條規則還誤殺了唯一成立的 finding。

所以寫 rubric 規則前先問一句：

| 這條規則在做什麼 | 有效？ |
|---|---|
| 給它 diff 裡**看不到的前提**（專案禁區、呼叫端契約、架構約束） | ✅ 有效，見 §2 步驟 5 |
| 要它**管住自己**（「不要報 X 類」「送出前先檢查 Y」） | ❌ 無效，兩個模型都只是換個說法繞過 |

> **2026-09-21 補上更強的證據。** 這條判準原本的樣本是「一條規則、幾次跑」。
> 後來我們照著另一個專案的做法加了一整層 `filter-findings`——它的 prompt
> 從頭到尾都是自我約束（預設全過、受保護主題否決權、明列不構成理由的情況）。
> 用 **700 則人工標註 comment** 實測的結果是：它誤刪 15 筆正確的、只刪對 4 筆，
> 而且**違反自己寫死的規則 5 次**（prompt 明寫「講可讀性且陳述屬實 → 保留」，
> 它照刪）。該功能已停用，完整數據見 §8。

⚠️ 反過來說，`prompts/rules/` 裡那兩份分型別規則之所以敢用，是因為它們寫的是
**給資訊**（「`.pyi` 檔案的未使用 import 是預期的」「`workflow_run` 跑的是
default branch 的版本」），不是要求模型管住自己。

### 4.8 註解密度越高的專案，誤報率越高

同一次實測的另一個發現，它決定這個工具**值不值得對某個 repo 跑**。

上面那四次跑，16 筆 finding 只有 1 筆成立。而標的的特徵很單純：
**作者幾乎每個設計決策都在註解裡寫了理由。**

主要失效模式是**報作者已經寫明理由的刻意決策**——模型「發現」的機制，
逐字就是作者寫在那幾行正上方的註解。實測到三個這樣的案例，其中兩個的
「建議修法」正是作者在註解裡論證過會出錯的那個做法。

這跟 §2 步驟 5 講的「前提不在 diff 裡」**不是同一件事，而且更難防**：
前提就在 diff 裡，就在它引用的那幾行上面。模型讀到了，但不把
「作者寫了理由」當成「這是已知且刻意的」的證據。

> **實務判準**：跑之前先抽看標的的註解密度。每個決策都寫了理由的 repo，
> 這個工具的訊噪比會崩掉——不是模型不夠好，是失效模式剛好卡在它的盲點上。
>
> 驗 finding 時，**第一步固定成「看它引用的那幾行上下文有沒有註解」**，
> 不要先想技術對不對。那一次 16 筆裡有 3 筆能這樣一眼刷掉。

補一個 `deepseek-flash` 的獨有失效模式（§4.3 之外的第三種）：它六筆裡有
三個 `major` 全長成「巢狀 `map` 的括號與縮排結構可疑，**需確認能編譯**」
——**它解析不了巢狀 JSX，就把自己的困難報成程式碼的問題，而且給 `major`**。
`deepseek-v4-pro` 四次裡一次都沒出現這種。所以用 flash 時它的 `major` 不能當嚴重度看。

#### 對照組：拿這個 kit 審它自己

同一天用 `deepseek-v4-pro` 審本 kit 的 code（11 檔／1,484 新增行，排除文件），
拿到一個乾淨的對照：

| | 前述那個 PR | 本 kit 自己 |
|---|---|---|
| 註解密度（排除文件與測試） | **51.7%** | **9.8%** |
| finding 數 | 16（四次合計） | 9 |
| 逐筆驗證後成立 | 1（6%） | **2（22%）** |
| 成本 | $0.133（四次） | $0.016（一次、22.2 秒） |

密度差 5 倍，成立率差 3.7 倍——方向吻合。**而且那 2 筆是真的 bug，當天就修掉了**：

1. **`post_review.py` 的冪等性檢查是死碼**。`gh(check=False)` 失敗時只 log
   warning、回傳空 stdout、**不拋例外**，所以配在外面的 `except RuntimeError`
   永遠不會觸發。gh 一失敗就回空集合，呼叫端讀成「一則都沒貼過」，於是
   每次 push 重複貼一輪 inline comment——§7 還有一列在教人怎麼善後那個症狀。
2. **`03` 用 `head -c` 截斷 diff**。那是位元組截斷：最後一個 hunk **必然**
   被切成半截，UTF-8 字元有 **2/3 機率**被切斷（3-byte 中文，三種對齊裡兩種壞）。
   而下游 `deepseek_review.py` 的 `truncate()` 本來就是在檔案邊界切的，
   第一層卻先把輸入弄壞了。

第 1 筆特別值得一提：它正是 §2 步驟 5 rubric 範例第 2 條的形狀
（「失敗必須可見：吞掉錯誤而呼叫端又不檢查」），只是載體不是 `2>/dev/null`
而是 `check=False`。**這個工具抓到了我們自己寫進 rubric 的那類問題。**

**但這次出現另一種誤報形狀**，是範本型專案特有的：9 筆裡有 3 筆在報
「README 已經列為 TODO 的刻意留白」（`matrix.language` 要換成你的語言、
action 版本要自己 pin）與「已經有對策的已知風險」（artifact 內容未驗證
——那正是 §5 整節在講的東西）。

所以把 §4.8 的判準再收斂一層，它比「註解密度」更根本：

> **模型會報「已經做了的事」——不管那寫在註解裡、README 裡，還是就在
> code 的上面幾行。** 最乾淨的一例：它建議「在迴圈前初始化 `last_err = None`」，
> 而 `deepseek_review.py` 第 130 行就是那一行。

### 4.9 rubric 的兩個實測限制

**一、「新增分支沒有對應測試」這半條幾乎無效。**

10 次跑（兩標的、兩模型、五種 rubric 變體）裡，只有 2 次出現測試覆蓋相關的 finding：

| rubric 變體（標的：TS PR／本 kit） | 測試 finding |
|---|---|
| 原版 | 0 ／ 0 |
| 把該條**原封不動搬到第 1 位** | **0 ／ 0** |
| 加一條自我約束規則（見 §4.7） | 0 ／ — |
| `deepseek-flash` 兩種變體 | 1 ／ — |
| 加了寫給人看的註記（見下） | **2** ／ 0 |

**搬到第 1 位也不報，所以不是優先序問題。** 合理的推測是它需要跨檔的**語義**比對
（讀 src 的分支，再去 test 檔判斷覆蓋關係），而模型做得到的是跨檔的**文字**比對
（兩處寫的數字不一致這種）——後者實測會自己冒出來，前者排第一也不做。
**這是推測，沒有實證。**

同一條的「**錯誤被吞掉**」那半條**有效**：§4.8 對照組抓到的第一個真 bug 就是它找出來的。
所以這條規則不是整條無效，是三個子項裡有一個無效。

**二、rubric 就是 system prompt，別在裡面寫給人看的註記。**

這個坑是實作上面那張表時踩到的。原本想在第 6 條底下加一段「⚠️ 這半條實測無效」的
說明給後人看——結果那段文字也進了 prompt，`測試` 一詞在 rubric 裡從 3 次變 4 次，
而那一次跑**報了 2 筆測試 finding**（其餘九次共 1 筆）。把註記拿掉重跑，回到 0 筆。

> **判準**：`review-rubric.md` 裡只放要給模型的指令。任何「為什麼這樣寫」「這條試過無效」
> 的元評論都放 README 或 commit message——**你以為在寫文件，其實在調 prompt**。

### 4.10 驗證流程：除了它報了什麼，還要看它沒碰什麼

一個 review 工具的價值不只看 finding 清單，要看**它一筆都沒報的檔案**——而那要自己去數，
它不會告訴你。實例：某次 27 檔的標的它只碰了 6 檔，而作者事前標明「本輪最容易寫錯」的
那個檔完全沒被碰到。

```bash
# 1) diff 涵蓋的全部檔案
grep '^diff --git' pr.diff | sed 's|.*b/||' | sort > /tmp/all.txt

# 2) findings 實際碰過的檔案
python3 -c "
import json; d=json.load(open('findings.json'))
fs=d if isinstance(d,list) else d.get('findings',[])
print('\n'.join(sorted({x['path'] for x in fs})))
" > /tmp/hit.txt

# 3) 差集 = 它一筆都沒報的檔
LC_ALL=C comm -23 /tmp/all.txt /tmp/hit.txt
```

第 3 行的 `LC_ALL=C` 不能省：中文 locale 下 `comm` 會吐 `Illegal byte sequence`，
而那個錯誤看起來像「檔案有問題」不像「locale 有問題」。

> ⚠️ **這一節所有數字都是單次跑，不能當因果證據。**
> 本工具**不可重現**（§8「已知的不穩定」：同一份 diff、`temperature 0.2`，兩次結果不一樣）。
> 所以「改了 X 之後結果變 Y」這種單次 A/B **證明不了 X 導致 Y**——要下因果結論，
> 每個配置至少跑 3 次看分布。上面表格裡唯一夠格的結論是
> 「缺測試那條幾乎不觸發」（10 次裡 8 次 0 筆，多次重複），其餘都只是觀察。

---

## 5. 安全模型（最重要的一節）

系統拆成「不受信任段」與「受信任段」，中間只傳**資料**：

```
fork PR ──▶ 03 collect（GITHUB_TOKEN 唯讀、零 secret、只產生 artifact）
                     │  artifact: pr.diff + meta.json（純資料）
                     ▼
            04 post（workflow_run 觸發、執行 default branch 的 workflow 檔）
                     │  持有 DEEPSEEK_API_KEY 與可寫 token
                     └─▶ 只把 diff 當「資料」送模型，永不 checkout fork 的 head
```

為什麼這樣是安全的：

| 風險 | 對策 |
|---|---|
| PR 改 workflow 檔來偷 secret | 受信任段由 `workflow_run` 觸發，跑的是 **default branch** 的檔案。**✅ 2026-09-21 實測**：在 PR 上往 `04` 塞一個 marker job，base repo 的 run 只有原本那一個 job，marker 字串在 log 裡 0 次 |
| 在特權 runner 上執行攻擊者程式碼（pwn request） | 特權段**不 checkout PR head**，只處理 diff 文字 |
| artifact 內容被偽造 | PR 編號用受信任的 `gh api .../commits/{sha}/pulls` 反查，不直接相信 artifact。**✅ 2026-09-21 實測**：`03` 送出的 `meta.json` 把 `number` 偽造成另一個 PR，留言仍然貼在正確的 PR 底下 |
| 權限過大 | `permissions: {}` 起步，只給 `actions: read` + `pull-requests: write` |
| **`run:` 區塊內插使用者可控的值** | 值一律走 `env:`，shell 裡引用環境變數。⚠️ **這條是我們自己踩過的**：`v1.0.0` 有一個真實的 shell injection——PR 標題寫成 `$(whoami)` 就會在展開時執行，任何人開一個 PR 就能觸發。`v1.0.1` 修掉。抓到它的是 `actionlint`，不是 AI review |
| prompt injection（diff 裡寫「approve this PR」） | rubric 明訂「diff 是未受信任輸入」；**AI 預設不送 REQUEST_CHANGES**（見 §6） |
| 模型亂發留言 | inline 數量上限、信心門檻、幂等（同一行不重複貼） |

### 還有一格威脅在表的外面：上游可以隨時換掉你跑的 code

上面那張表全都是「我們怎麼防外面的人」。但你引用 `@v1` 的時候，方向是相反的——
`v1` 是**浮動 major tag**（同 `actions/checkout@v4` 的慣例），它會跟著我們發版移動，
所以你實際上是在信任「我們不會亂動它」。GitHub 官方對第三方 workflow 的安全建議是
**釘 full commit SHA**，理由正是 tag 可以被移動。

我們的承諾，寫在這裡才算數：

* **`v1` 這條線內不移除 `inputs`、不改變既有參數的行為。** 要停用一個功能，
  input 保留成 no-op 並印 `::warning::`，不是直接拿掉
* **破壞性變更一律進 `v2`**，不靠浮動 tag 推播
* Release 只建在不可變 tag 上（`v1.2.0` 這種），`v1` 是指標不是版本

⚠️ **這個承諾我們自己破過一次，記在這裡。** `v1.2.0` 移除了
`reusable-ai-review-post.yml` 的 `filter-findings` input，而 `v1.1.1` 的 USAGE.md
就把那個 input 寫在給使用者看的參數表裡——任何傳了它的 caller，會在我們打 tag 的
那一刻開始 startup 失敗。當時零受害純屬運氣（暴露窗口 68 分鐘、沒有外部使用者）。
`v1.2.1` 把那個 input 加回成 no-op，並補上這一節。

不想承擔這個信任的話，把 `@v1` 換成 commit SHA 就好，功能完全一樣。

### `05` 為什麼只跑同 repo 的 PR

`if: github.event.pull_request.head.repo.full_name == github.repository`

DeepSeek Harness 的 headless 模式在 CI 中沒有互動審批通道（會 fail-closed），
且 agent 會在 workspace 內活動。與其想辦法在 fork PR 上放寬權限，
不如**讓 fork PR 走 03/04 的資料路線，05 只服務同 repo 分支**。

---

## 6. 四個刻意的設計選擇（請自行確認是否同意）

1. **AI review 不設為 required status check。**
   模型輸出有變異性，把 merge 權交給它會製造偽陽性阻塞。
   kit 裡 `post_review.py` 預設只留 `COMMENT`；
   想開啟 gating 要明示加 `--request-changes-on-blocker`，
   而且即使開啟也建議只讓 `blocker`（不是 `major`）有否決權。

2. **agent 唯讀，寫入交給 shell。**
   `05` 用 `dsh --profile headless "task" > review.md`，
   輸出由 shell 重導向寫檔，agent 不需要 workspace 寫入權限。
   這比把 approval policy 放寬到 `never`（等於 yolo / full-access）安全得多。

3. **不做自動修 code。**
   「發現問題」的錯誤成本低，「自動改壞」的錯誤成本高。
   修復請留在人類手上；要自動修，請走獨立的、
   必須人工 approve 的 PR 流程。

4. **定位是粗篩，不是結論。**
   §4.3 那兩種失效形狀（機制講錯、後果誇大）不會因為換模型消失，
   只會變得更難察覺——因為 pro 的定位更準、語氣更可信。
   合理用法是「對不值得動用重型 review 的中小改動先跑它」，
   或在人工深度審查之前篩一輪。**每筆 finding 都要實跑驗證再採信。**

---

## 7. 疑難排解

| 症狀 | 原因與處理 |
|---|---|
| **模型回傳空字串、exit code 2（「回應中找不到 JSON 物件」）** | reasoning 把 `max_tokens` 吃光了，`finish_reason=length`。確認有帶 `--thinking disabled`（kit 預設），或把 `--max-tokens` 拉到 65536 以上。詳見 §4.1 |
| 模型名稱回 HTTP 400 | 只有 `deepseek-flash` 與 `deepseek-v4-pro` 兩個有效名稱。`deepseek-v4.1-flash` 不存在（`deepseek-flash` 本身就是 V4.1-Flash） |
| review 只報泛泛的通用意見、抓不到你真正在意的問題 | rubric 沒有專案禁區。這是影響最大的一項，見 §2 步驟 5 |
| findings 大部分被 skip、inline 只貼 1 則 | `--min-confidence 0.7` 對 flash 太嚴（它自評落 0.55–0.75）。改用 v4-pro，或把門檻降到 0.6 |
| inline comment 貼不上去（422） | 行號不在 diff hunk 內。`post_review.py` 已做行號驗證並降級進摘要，若仍出現請貼 `--diff` 參數讓它驗證 |
| review 重複貼好幾次 | 摘要用 `gh pr review --comment`，每次 push 會新增一則；要單一留言改用 `gh pr comment --edit-last --create-if-none`（`05` 已這樣做） |
| 04 沒有被觸發 | `03` 必須存在於 **default branch** 且成功完成；`workflow_run` 只認 default branch 上的 workflow 名稱 |
| **每個 step 都 success、`review.md` 完整，但 PR 上一則留言都沒有** | `gh pr` 子命令靠當前目錄的 git remote 推斷 repo，走 reusable 時工作目錄根沒有 git repo。`v1.0.2` 補上 `--repo` 修掉，並改成失敗時印 `::warning::`。若你複製的是舊版腳本，檢查 `gh pr review` 有沒有帶 `--repo` |
| log 出現 `重新定位 A → B` | 正常。行號由程式用程式碼片段比對算出，模型報的當備援——實測它報的行號 16 筆只有 1 筆真的指對。見 §8 |
| **改了 kit 自己的 code，PR 跑完全綠卻看不到效果** | 本 repo 的 `03`／`04` 引用 `@v1`，`.kit` checkout 的是**已發布版本**，PR 裡的改動一行都不會執行。而且 `04` 由 `workflow_run` 觸發、跑的是 default branch 的 workflow，所以連「在 branch 上改 `kit-ref`」都無效。要驗只能走發布流程：合併 → 打 tag → 移動 `v1` → 下一個 PR |
| 05 卡在 approval / 工具被拒 | headless 無互動審批通道，屬預期行為。檢查是否誤讓 agent 需要寫入權限 |
| 05 抓不到 `@deepseek-ai/dsh` | 確認 Node 版本為 `^22.19.0 \|\| >=24.0.0`；首次下載數百 MB，確認 cache 生效 |
| `dsh` 說 sandbox 不可用（`SANDBOX_UNAVAILABLE`） | 容器內缺少 bwrap/Landlock 等後端。唯讀工具通常不受影響；若需要寫入請改用 04 路線 |
| YAML 的 `on:` 被解析成布林 `True` | 用 PyYAML 讀取時的已知行為（YAML 1.1），不影響 GitHub 解析 |

---

## 8. 已驗證與未驗證項目（誠實聲明）

### 已驗證

* **`deepseek_review.py` 對真實 DeepSeek API 端到端跑通**（2026-09-19／20，23 次呼叫、
  7 個真實標的，總花費 $0.43）。其中 10 次是同一組 diff 的 rubric 變體對照
  （2 模型 × 5 種 rubric），1 次是拿本 kit 審自己——**撈出兩個真 bug 並修掉**，
  結論見 §4.7／§4.8／§4.9。這條在 2026-09-17 的版本裡還是「未驗證」——
  當時的 agent session 拿不到 API key，後來補跑了。實測數據見 §4。
* **`post_review.py` 的行號驗證與過濾**已用真實 findings 走過 `--dry-run`：
  5 筆 findings 經門檻與 hunk 檢查後剩 1 筆可貼 inline，其餘正確降級進摘要。
* `python3 tools/selftest.py` **10 組 37 項斷言全通過**。
* ⛔ **試過一層「過濾誤報」，實測讓 precision 變差，已整個移除**（2026-09-21，
  用 [AACR-Bench](https://huggingface.co/datasets/Alibaba-Aone/aacr-bench) 的
  **700 則人工標註 comment**、140 個 PR、10 種語言，成本 $0.40。
  重跑方式：`gh workflow run eval-filter.yml -f limit=0`）。

  | | label=0（錯誤的 comment） | label=1（正確的 comment） |
  |---|---|---|
  | **被 filter 刪掉** | 4（刪對） | **15（誤刪）** |
  | **保留** | 187 | 494 |

  **誤刪 2.95%（15/509）、抓錯 2.09%（4/191），precision 72.71% → 72.54%。**
  誤刪是刪對的 **3.75 倍**，而且 15 筆誤刪裡有 9 筆是 Code Defect——
  括號不匹配、陣列重複項導致某個分支永遠不執行、`curve1`／`curve2` 賦值錯、
  錯誤訊息參數順序顛倒、`mode` 參數被忽略永遠用同一種鎖。**那些被無聲吃掉的代價太高。**

  另外 5 筆誤刪屬於 Maintainability，而 filter 的 prompt 第二步**明寫**
  「講風格、命名、可讀性且陳述屬實 → 保留，停」——**它違反了自己的規則 5 次**。
  這與 §4 記的「rubric 加『給它看不到的前提』有效、加『要求自我約束』無效」是同一件事：
  那份 prompt 的整個機制（預設全過、受保護主題否決權、不構成理由清單）都是自我約束。

  ⚠️ 一個事前的粗估與結果一致，可以拿來當下次的判準：用語言訊號
  （missing／unused／not checked／hardcoded…）分，**錯誤 comment 裡只有 13% 屬於
  「可被 diff 字面反駁」的形狀，正確 comment 裡卻有 18%**——filter 的射程內，
  對的比錯的多三倍（3.6:1），而實測誤刪比是 3.75:1。
  **射程內的組成比模型的判斷力更早決定了上限。**

  它抓對的那 4 筆都是真正的字面矛盾（return 後的死碼、null 檢查後又無條件使用、
  `npos` 未處理、變數名 typo），所以問題不是「Ground B 這個判準錯」，
  是**模型執行不了「只在能指出反證行時才刪」這條約束**。
* **行號改由程式用程式碼片段比對算出，不再相信模型自報的行號**（2026-09-21）。
  用本 repo 八組 `ai-review-input`／`ai-review-output` artifact 離線重跑 16 筆真實
  finding，**零額外 API 花費**：
  * 模型自報的行號，只有 **1/16** 真正指向它自己 evidence 引用的那段 code，
    其餘偏移 +1 到 +24 行。最典型的一筆，evidence 明寫「第 48 行：`BASE='...base.sha'`」，
    而那行實際在 **55**，48 行是 `persist-credentials: false`——**引對內容、數錯行號**。
  * 改用片段文字比對，**13/16** 唯一命中，偏移最大的三筆（+24／+9／+7）逐筆抽驗
    確認指向正確；3 筆誠實拒絕定位，其中 1 筆是「finding 在講被刪掉的區塊」，
    新檔本來就沒有對應行，拒絕才是正確行為。
  * 實作見 `.github/scripts/locate.py`（四層階梯：同檔片段 → 跨檔片段 → 退回模型行號
    → 降級）。第 3 層保留舊行為當安全網，**原本貼得出去的不會因此消失**。
  * ⚠️ **這個實驗繞過了「本工具不可重現」的限制**：它不是比較兩次產出，而是對
    同一批產出用兩種定位方法——確定性、可重複，與模型會不會重現無關。
  * ⚠️ 第一次測量的結果是「16 筆行號 100% 落在合法範圍」，看起來沒問題；
    但那只量到「GitHub API 會不會回 422」，跟「指的對不對」是兩件事。
    **可貼 ≠ 指對**——這個陷阱值得記住。
  * **2026-09-21 真實環境的第一組資料**（v1.1.0 發布後，PR #10）：模型確實填了
    `existing_code` 且內容逐字正確；兩筆 finding 被重新定位（各偏移 +3 行）。
    ⚠️ **但其中一筆是定位層自己改錯的**——模型原本報對了，是我們把它改壞。
    根因：`existing_code` 是整段逐字程式碼，而程式碼的 docstring 裡含有 markdown
    反引號是完全正常的；舊版把它跟散文欄位走同一條路徑，看到反引號就去挖裡面的
    內容當片段，於是命中了 docstring 裡提到那個名字的那一行。
    判斷「這是程式碼還是散文」不能靠內容猜，要靠**它來自哪個欄位**。已修
    （`literal_snippets` 與 `extract_snippets` 分開），並用那兩筆真實 finding
    做過紅綠對照：修正前 1/2 正確，修正後 2/2 正確。
* 所有 action 的版本 tag 與 inputs **2026-09-17 首驗、2026-09-19 複驗**，十項全數仍為最新
  （見 §2 版本對照表）。注意 `trivy-action` 的 tag **有 `v` 前綴**（`v0.36.0`，不是 `0.36.0`）。
  正式環境建議進一步 pin 到 commit SHA。
* `.gitignore` 的攔截範圍以臨時 repo 實測（見 §2 步驟 1 的警告）。
* **`02-codeql.yml` 在真實 GitHub Actions 上跑通**（2026-09-20，本 repo 自己）：
  push 到 main 觸發，`Analyze (python)` 59s、`Trivy (filesystem)` 32s 兩個 job 全綠，
  SARIF 確實進到 code scanning（CodeQL 與 Trivy 各一筆分析紀錄，本 repo 零告警）。
  ⚠️ **2026-09-21 補充：那句「零告警」有前提。** 拿一支刻意寫壞的 Python
  （`sys.argv` 一路流進 `subprocess.run(..., shell=True)`）實測，**預設設定下
  CodeQL 不會報那筆 command injection**——它確實 extract 了檔案、也載入並跑了
  `CWE-078/CommandInjection`、SARIF 也上傳成功，就是不報。原因是**預設的
  threat model 只把「遠端」輸入當汙染源**，命令列參數、環境變數、檔案系統
  屬於 local source。加上 `threat-models: local` 之後，同一份 code 從 4 筆
  變 7 筆，多出來的三筆全都是需要追資料流的（command injection / partial SSRF /
  path injection），而原本那 4 筆全是局部語法分析。本 repo 的 Python 都是 CI
  腳本、吃的就是 argv 與環境變數，所以 `codeql-config.yml` 已經打開這個設定。
  ⚠️ 查結果時注意：**PR 的 alert 在 `refs/pull/<n>/merge`**，查
  `refs/heads/<branch>` 會得到 0 筆，看起來像沒報。
  同時驗掉一個**不會報錯的失敗模式**：這套 kit 原本放在 `code-review-kit/` 子目錄下，
  五個 workflow 的實際觸發次數是**零**——GitHub Actions 只掃 `<repo-root>/.github/workflows/`，
  放錯位置既不觸發也不警告。詳見 §2 步驟 1 的警告。
* **`01`／`03`／`04`／`05` 在真實 PR 上跑通**（2026-09-20，本 repo PR #1）：
  * **`03` → `04` 的 `workflow_run` 觸發鏈成立**——整個 fork-safe 架構就靠這條：
    `03` 完成後 `04` 自動觸發、下載 artifact、拿得到 secret。
  * `04` 呼叫 `deepseek-v4-pro`（prompt 2,497 tokens／cache hit 1,280、completion 586），
    摘要貼成 PR review，**inline comment 實際貼上 `README.md:550`**。
  * `post_review.py` 的降級過濾在真實環境生效：2 筆 finding 只有 1 筆進 inline，
    另一筆**降級進摘要並註明理由**，沒有亂貼。
    ⚠️ **2026-09-21 更正**：這裡原本寫的是「因**行號**不在 diff 內」降級，歸因錯了。
    回頭用八組 artifact 重算 16 筆 finding：**被行號擋 0 筆、被 confidence 擋 4 筆**，
    再用 `gh api` 查 PR #1 實際貼出的 inline comment 交叉確認（兩筆都是 conf 0.70，
    降級的全是 0.65）。行號從頭到尾一筆都沒擋過。錯誤來源是舊版降級訊息把多個原因
    擠成一句「（行號不在 diff 內、或信心/嚴重度未達門檻）」，讀的人記住了第一個——
    同一個錯誤歸因擴散到三份文件。訊息現已改成印出實際命中的原因與值。
  * `01` 的 `reviewdog`／`gitleaks` 兩個 job 綠。`dependency review` 第一次**失敗**，
    根因是 repo 的 **Dependency graph 預設沒開**——啟用後重跑三個 job 全綠
    （紅綠對照：attempt 2 失敗 → 啟用 → attempt 3 成功）。導入時這是必踩的坑，
    而且它跟 required check 有連鎖後果，見 SETUP-CHECKLIST §3 第一條。
  * `05` 如預期 skip（沒有 `review:deep` label）。
* **那次 review 的 2 筆 finding 品質**（單次觀察，不是統計結論）：1 筆成立、1 筆不成立。
  不成立那筆宣稱「workflow 放錯位置是先前已知的陷阱」——事實相反，那是本次才踩出來的。
  **位置對、推論錯、語氣篤定**，與 §4 記錄的模式一致。成立那筆抓到 fork PR 驗證的
  語氣被弱化，已採納修回。附帶觀察：**成立的那筆被降級、沒貼成 inline；
  不成立的那筆反而貼上去了**。
  ⚠️ **2026-09-21 更正機制**：原本寫「因行號不在 diff 內被降級，過濾機制擋的是行號
  不是品質，兩者無關」——**降級的真正原因是 `confidence 0.65 < 0.7`**。
  而 confidence 是模型的自評分數，所以結論要反過來寫：不是「兩者無關」，而是
  **模型對成立 finding 的自評信心反而比較低**。這跟 §4 記的另一個實例同形狀
  （`deepseek-flash` 對一個真 SQL 注入只給 0.6 信心，被預設門檻丟掉）。
  `--min-confidence` 的預設值擋掉的可能正是該看的那幾筆。
* **本 repo 自己的 `03`／`04` 已改用 reusable workflow**（2026-09-21，引用 `@v1`）。
  這不只是整理，它是這套 kit 唯一能驗證「對外部使用者是否可用」的方式——**第一天就抓到
  一個只有 reusable 版才會出現的 bug**：`post_review.py` 的 `gh pr review` 沒帶 `--repo`，
  而 `gh pr` 子命令靠當前目錄的 git remote 推斷 repo。舊版把 caller repo checkout 到
  工作目錄根所以能用，reusable 版只把 kit 放到 `.kit` 子目錄，根目錄沒有 git repo。
  加上 `gh()` 的 `check=False` 吞掉錯誤，症狀是**所有 step success、`review.md` 內容完整、
  PR 上一則留言都沒有**。已於 `v1.0.2` 修正，並把 `gh` 失敗改用 `::warning::` 輸出。
  舊版 `04` 跑了三個 PR 都正常——**不做 dogfood 這個 bug 會留在 `v1` 裡等別人踩**。

* ✅ **`typed-rules`（分型別補充規則）的機制已在真實環境驗過**（2026-09-21）：
  diff 含 `.py` 檔案時 log 出現 `套用補充規則：python.md`，同時含 workflow 與 Python
  時兩份都套用，純 markdown 的 diff 則一份都不附加。
  規則走 **user message 不走 system prompt**，所以不影響 context caching——
  三種 diff 型態下 system prompt 都是同樣的 2,886 字元。
* ✅ **改 rubric 造成的 cache 命中下降是重建過渡，不是結構性損失。**
  實測五次 `prompt_cache_hit_tokens`：

  | rubric | 第 1 次 | 第 2 次 | 第 3 次 |
  |---|---|---|---|
  | v1.0.2（80 行） | 1,280 | 1,280 | — |
  | v1.1.0（89 行） | **640** | **1,024** | **1,408** |

  舊 rubric 的命中數**不隨 diff 大小變動**（`prompt_tokens` 從 1,932 到 10,301 都是 1,280）。
  新 rubric 第三次已超過舊值，符合「rubric 變長、可快取的前綴也變長」的預期。
  DeepSeek 的 cache 是前綴比對，改動之後需要幾次請求重新建立。
* ✅ **rubric 的 `existing_code` 欄位，模型確實填得出來而且填得對**（2026-09-21，
  PR #10）：實際回傳的是
  `'if locate.normalize_ws(line) not in locate.normalize_ws(diff):'`，與 diff 逐字相符。
  同一輪也驗到定位層會修正行號（兩筆各偏移 +3 行）。
  ⚠️ 但那一輪也暴露了定位層自己的一個 bug——見上方「行號改由程式算」那條的說明。

### 未驗證

* **`typed-rules` 有沒有真的提升命中率，還沒有資料。** 已驗的是「規則確實依檔案型態
  被挑中」這件機制層的事（`selftest.py` 測項 `[11]` + 真實環境 log）。
  但「加了 workflow／Python 規則之後，finding 的成立率有沒有變高」需要 A/B，
  而本工具不可重現，單次跑證明不了因果——要做得照 `tools/eval/` 那套，
  用標註資料跑固定分母的對照。
* **換一份 system prompt 就完全失去 cache。** 那層過濾用的是另一份 system prompt，
  實測 `prompt_cache_hit_tokens: 0`。這條留著是因為它本身值得記：
  多一次呼叫的成本，不只是「多一次」，而是多一次**沒有 cache 折扣**的呼叫。
* **§4.7／§4.9 的 rubric 變體比較全部是單次跑，不是統計結論。** 本工具不可重現
  （見下方「已知的不穩定」），所以「改了 X 之後結果變 Y」**證明不了 X 導致 Y**。
  這些表格裡唯一經過多次重複的是「缺測試那條幾乎不觸發」（10 次跑裡 8 次 0 筆）；
  其餘都只是單次觀察。要下因果結論，每個配置至少跑 3 次看分布——**那沒做**。
* **信任邊界驗過兩條，第三條沒驗。** 2026-09-21 用一個同 repo 的 PR 測掉兩件事
  （做法與結果見 §5 的威脅表）：往 `04` 塞一個 marker job，base repo 的 run 不執行它；
  `03` 送出偽造 `number` 的 `meta.json`，留言仍貼在正確的 PR。
  **這兩條不需要 fork**——`pull_request` 那段跑 PR head 的檔案、`workflow_run` 那段跑
  default branch 的檔案，不分 fork 還是同 repo 分支，行為相同。
  **沒驗的是 fork 專屬的部分**：外部貢獻者的核可政策（`all_external_contributors`）
  實際跑起來的樣子。至於「fork 拿不到 secret」——`reusable-ai-review-collect.yml`
  整支**沒有 `secrets:` 區塊**，那條路徑上結構性地不存在 secret 可洩漏，
  所以那不是一個需要測的斷言。
* `05-dsh-agent-review.yml` 的 `dsh` 旗標（`--profile headless`、`--session-id`、`--json`，
  以及「省略位置參數則改讀 stdin」）來自官方 CLI README 與其原始碼，**未在本機執行驗證**。
  DeepSeek Harness 是 developer preview，官方明示會有破壞性變更——
  **2026-09-17 到 09-19 兩天之內 npm `latest` 就從 `0.1.5-rc.1` 跳到 `0.1.5-rc.2`**。
  升級前請重跑 `npx -y @deepseek-ai/dsh@<ver> --profile headless --dump-default-config` 確認 profile 結構。

### 已知的不穩定

* **輸出有變異性**：同一份 diff、同樣 `temperature 0.2`，兩次跑出的 findings 不一樣；
  第二次還冒出第一次沒有的問題。**「跑一次沒報」不等於「沒問題」**，也不要把它當可重現的閘門。
* 模型價格隨官方調整，估算請以 https://api-docs.deepseek.com/quick_start/pricing 為準。

### 每次貼留言會多出一筆「空的」review —— 那是刻意的取捨

PR 的 timeline 上會看到 `github-actions bot reviewed` 出現兩次，其中一次**點進去沒有內容**。
這不是壞掉，是為了冪等性付的代價。

GitHub 貼 PR review comment 有兩條路，而它們是互斥的：

| 做法 | 冪等性 | 副作用 |
|---|---|---|
| `POST /pulls/{n}/reviews` 帶 `comments` 陣列 | **做不到**——一次性提交整個 review，沒有逐筆比對的機會 | 乾淨，一筆 review |
| `POST /pulls/{n}/comments` 逐筆貼 | **做得到**——貼之前先撈現有 comment 的 `(path, line)` 跳過已貼 | GitHub 把每筆包進一個隱含的、`body` 為空的 review |

`post_review.py` 走第二條。**重複貼留言是真 bug**（每次 push 洗版一次，PR 會被淹沒），
而空 review 只是 timeline 上的視覺雜訊——這個取捨很清楚。

2026-09-20 的實測證明冪等性真的在運作：第二輪 DeepSeek **重報了同一個位置**，
而那筆 inline comment 沒有被貼第二次。不是「它沒再報」，是「它再報了但被擋住」。

---

## 9. 隨想：為什麼會有這個 repo

起點是三件事——兩件很實際，一件到現在也說不太清楚。

一是等待。用 CodeRabbit 的時候，相當多的時間花在等 rate limit——送出 PR，
等到能看結果時人已經在做別的事了。code review 的價值有一大半在「當下」，
隔開之後它就只是另一件待辦。

二是成本。直接用 Claude Code 做 review 的品質是夠的，但把一份中型 PR 的 diff 送進去，
token 消耗是實打實的。要變成「每個 PR 都自動跑一次」的流程，那個量級撐不住。

三是一種說不上來的彆扭：**用 Claude Code 去審 Claude Code 自己寫的 code，
總有點監守自盜的味道。** 寫的時候它判斷這樣可以，審的時候還是同一套判斷在跑——
它會不會剛好看不見它自己那一類的盲點？審得再仔細，有些東西可能從一開始就不在視野裡。

這個疑慮我們沒有做過對照實驗（同一份 code，寫的人審 vs 別人審），所以它在這裡
只是動機，不是結論——這份 README 其他地方的斷言都有數字，這一條沒有。

比較直接的解法是換更強的模型來審，或者乾脆多跑幾家再交叉比對。這確實有效，
不同來源會抓到對方沒看到的東西。但那種做法的成本結構屬於「你會盯著看的那幾次」，
而這裡要解的是「每個 PR 都自動跑一次」——同一件事換成這個頻率，可負擔的單價
完全不是同一回事（這裡的費用估算見 §3）。

三件事於是收束成同一個限制條件：**審 code 的最好不要是寫 code 的那一個，
而且要便宜到每個 PR 都跑得起。** 這個 repo 就是在這兩個條件的交集裡找答案。

做到一半才發現，真正的問題不在那裡——**這種工具到底有沒有效？**

這比「怎麼做」難答得多，而且有個很好掉進去的陷阱：**AI review 永遠給得出東西。**
它總是報得出幾筆 finding，語氣還很篤定。難的不是讓它產出，是分辨那是「看懂了」
還是「填空」。而且這件事沒有語言訊號——一筆錯的 finding 和一筆對的，讀起來一樣有道理。

所以這個 repo 的重心後來從「做一個工具」偏向「量這個工具」：

- §4 記的是實測，包含 markdown 標的上 **16 筆只有 1 筆成立**這種難看的數字
- §8 明寫哪些驗過、哪些沒驗、哪些已知不穩定
- `tools/eval/` 是評估框架而不是功能，存在的唯一理由是讓下一個想法先被量過再上線
- 它砍掉過自己加的 review filter——700 則人工標註資料顯示那一層讓 precision 變差

如果這個 repo 有什麼值得看的，大概不是「又一個 AI code review 工具」。這個品類已經很擠，
[alibaba/open-code-review](https://github.com/alibaba/open-code-review) 的功能更完整，
[hustcer/deepseek-review](https://github.com/hustcer/deepseek-review) 也在做同一件事。
值得看的應該是它對自己留下的實測紀錄：這類工具在什麼標的上真的有用、在什麼標的上會空手而回、
以及怎麼分辨這兩者。

這題還沒答完。§8 的「未驗證」那節就是還欠的部分。

— 子超
