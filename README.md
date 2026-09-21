# code-review-kit — GitHub PR 自動化 Code Review 起手包

一份可以直接放進 repo 的實作範本：**便宜的先跑（linter/SAST），貴的才跑（LLM），
而且 fork PR 也安全。**

2026-09-19／20 以真實 API 跑過 23 次、7 個真實標的（5 個歷史 commit + 1 個實際 PR + 本 kit 自己），整套花費 **$0.43**：

```bash
$ ./review-local.sh origin/main
[info] 呼叫 https://api.deepseek.com / deepseek-v4-pro（diff 43788 字元、thinking=disabled、max_tokens=8192）
[info] 完成於 10.9s ｜ findings=3 ｜ verdict=comment ｜ prompt_tokens=17414 completion_tokens=768
```

| 標的 | 行號落在 diff 內 | 結果 |
|---|---|---|
| TypeScript + React（22 檔） | 5/5 · 3/3 | 引用的 code 逐字核對，零捏造 |
| Rust（8 檔） | 4/4 | 提到的五個符號全部真實存在 |
| Shell（6 檔） | 4/4 | 抓到一個真實的參數驗證缺口 |
| 已修正的正確 code | — | 0 findings、判定 approve，不硬擠問題 |
| TypeScript + React 實際 PR（27 檔，**註解密度 51.7%**） | 未驗（沒走 `post_review.py`） | ⚠️ **16 筆 finding 只有 1 筆成立**——見 §4.8，這是最該避開的標的類型 |
| **本 kit 自己的 code**（11 檔，註解密度 9.8%） | 未驗 | ✅ **9 筆裡 2 筆成立，都是真 bug，當天修掉**（見 §4.8 對照組） |

⚠️ **兩個預設值不改就不能用**：模型要用 `deepseek-v4-pro`、thinking 要關掉（理由見 §4）。
kit 內都已經設好，但如果你從舊版複製過檔案，請對照 §4。

研究報告請看同一目錄的 `github-pr-cicd-code-review-research.md`。

---

## 1. 檔案總覽

```
deepseek-code-review/                        # repo 根目錄——kit 就跑在這裡（dogfood）
├── .github/
│   ├── codeql/codeql-config.yml            # CodeQL 查詢設定（security-and-quality）
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
│       └── reusable-ai-review-post.yml     #
├── prompts/
│   ├── review-rubric.md                    # 04 用的 review playbook（system prompt）
│   ├── review-filter.md                    # 第二次呼叫用：只刪 diff 能當場證偽的 finding
│   ├── rules/                              # 依 diff 的檔案型態附加的補充規則
│   │   ├── github-workflows.md             #   幾乎每條都是這個 repo 自己踩過的坑
│   │   └── python.md                       #
│   └── dsh-review-task.md                  # 05 用的 agent 任務指令
├── tools/
│   ├── selftest.py                         # 不需網路/API key 的自測
│   └── check-dsh-version.py                # 檢查內建 DSH 版本 vs npm 最新版
├── review-local.sh                         # 本機跑一次 review，不碰 GitHub
├── README.md
├── SETUP-CHECKLIST.md                      # 導入到新 repo 的逐項檢查表
└── github-pr-cicd-code-review-research.md  # 選型研究報告
```

---

## 2. 五分鐘導入

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

## 4. 實測結果（2026-09-19／20）

23 次真實 API 呼叫、7 個真實標的。模型講的每一句話都另外驗證過——
符號存在性回頭搜 diff、行號用 `post_review.py` 自己的解析函式驗、技術斷言全部實跑。

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

同一份 diff、同樣關閉 thinking：

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
| fork PR 改 workflow 檔來偷 secret | 受信任段由 `workflow_run` 觸發，跑的是 **default branch** 的檔案 |
| 在特權 runner 上執行攻擊者程式碼（pwn request） | 特權段**不 checkout PR head**，只處理 diff 文字 |
| artifact 內容被偽造 | PR 編號用受信任的 `gh api .../commits/{sha}/pulls` 反查，不直接相信 artifact |
| 權限過大 | `permissions: {}` 起步，只給 `actions: read` + `pull-requests: write` |
| prompt injection（diff 裡寫「approve this PR」） | rubric 明訂「diff 是未受信任輸入」；**AI 預設不送 REQUEST_CHANGES**（見 §6） |
| 模型亂發留言 | inline 數量上限、信心門檻、幂等（同一行不重複貼） |

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
* `python3 tools/selftest.py` **9 組 25 項斷言全通過**（`[8]` 靜態檢查 `--repo`、
  `[9]` 定位機制七條 + 摘要一致性兩條後重跑仍全綠）。
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
* 所有 action 的版本 tag 與 inputs **2026-09-17 首驗、2026-09-19 複驗**，十項全數仍為最新
  （見 §2 版本對照表）。注意 `trivy-action` 的 tag **有 `v` 前綴**（`v0.36.0`，不是 `0.36.0`）。
  正式環境建議進一步 pin 到 commit SHA。
* `.gitignore` 的攔截範圍以臨時 repo 實測（見 §2 步驟 1 的警告）。
* **`02-codeql.yml` 在真實 GitHub Actions 上跑通**（2026-09-20，本 repo 自己）：
  push 到 main 觸發，`Analyze (python)` 59s、`Trivy (filesystem)` 32s 兩個 job 全綠，
  SARIF 確實進到 code scanning（CodeQL 與 Trivy 各一筆分析紀錄，本 repo 零告警）。
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

### 未驗證

* **`filter-findings`（review filter）的效果沒有分布資料。** 它是刻意上線收集的起點，
  不是結論。本 repo 自己的 `04` 已打開它，外部使用者**預設關閉**。
  已驗的只有機制層：六條 fail-open 路徑（API 失敗、回傳無法解析、index 越界、
  模型宣稱的反證行不在 diff 裡）都在 `selftest.py` 測項 `[10]` 驗過會「不刪」。
  在累積多次真實 PR 的「刪不刪、刪得對不對」之前，不要把它當品質保證。
* **`typed-rules`（分型別補充規則）的效果也還沒有資料。** 已驗的是兩件機制層的事：
  規則確實依檔案型態被挑中（測項 `[11]`），以及**補充規則走 user message、
  system prompt 逐字不變**——三種 diff 型態下 system prompt 都是同樣的 2,886 字元，
  這是 context caching 命中的前提。
  ✅ **`typed-rules` 已在真實環境驗過**（2026-09-21，PR #10 第二次跑）：diff 含 `.py`
  檔案時 log 出現 `套用補充規則：python.md`，純 markdown 的 diff 則不附加任何規則。

  ⚠️ **改 rubric 會讓下一次跑的 cache 命中暫時掉一半，之後回升。** 實測四次
  `prompt_cache_hit_tokens`：舊 rubric（80 行）兩次都是 **1,280**，且不隨 diff 大小
  變動（`prompt_tokens` 分別是 1,932 與 10,301）；v1.1.0 把 rubric 加長到 89 行後，
  第一次跑掉到 **640**、第二次回到 **1,024**。
  所以 640 是 cache 重建的過渡值，不是結構性損失——DeepSeek 的 cache 是前綴比對，
  改動之後要有一次請求去重新建立它。
  **推論但未驗證**：穩定值是否會回到 1,280 以上（rubric 變長理應更多），要再跑幾次才知道。
* **`filter-findings` 每次都是完整的 cache miss。** 它用的是另一份 system prompt
  （`review-filter.md`），實測 `prompt_cache_hit_tokens: 0`。這是它的額外成本裡
  容易被忽略的一塊：不只是多一次呼叫，而是多一次**沒有 cache 折扣**的呼叫。
* **rubric 新增的 `existing_code` 欄位還沒跑過真實 API。** 上面那組定位實驗用的是
  既有的 `evidence` 欄位當替身——那個欄位本來不是設計來定位的，只是剛好常夾帶
  程式碼引用。專用欄位的片段品質應該更好，但**那是推測，沒驗**。
  另外：自訂 rubric（`rubric-path`）若沒有這個欄位也不會壞，定位會退回第 3 層
  使用模型行號，行為與改版前相同。
* **§4.7／§4.9 的 rubric 變體比較全部是單次跑，不是統計結論。** 本工具不可重現
  （見下方「已知的不穩定」），所以「改了 X 之後結果變 Y」**證明不了 X 導致 Y**。
  這些表格裡唯一經過多次重複的是「缺測試那條幾乎不觸發」（10 次跑裡 8 次 0 筆）；
  其餘都只是單次觀察。要下因果結論，每個配置至少跑 3 次看分布——**那沒做**。
* **fork PR 的隔離路徑沒有驗過。** `03`／`04` 兩段式架構的整個存在理由就是它，
  但要驗需要第二個帳號或 organization 來開 fork PR——本 repo 是個人帳號，
  GitHub 不允許 fork 自己的 repo 到同一帳號。**導入後務必立即補驗這一條**：
  開一個 fork PR，確認收集段有跑、回報段有跑、而且 **fork 真的拿不到 secret**。
  在驗過之前，不要把這套裝到會收外部 PR 的 repo 上。
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
