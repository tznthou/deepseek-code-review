# Changelog

本專案所有值得注意的變更都記錄在這個檔案。

格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號依循 [語意化版本](https://semver.org/lang/zh-TW/)。

> **關於 `v1` 這個浮動 tag**：`@v1` 會跟著 v1.x.x 移動（同 `actions/checkout@v4` 的慣例），
> 引用它的 repo 不必改任何東西就會拿到修正版。代價是破壞性變更也會自動推播——
> 所以 v1 這條線上的相容性承諾見 README §5，本檔的 `BREAKING` 標記請特別留意。

## [Unreleased]

### Docs

- 新增 `experiments/`：實測紀錄的公開索引。實驗的原始資料一直放在不進 repo 的私有目錄，
  README §9 說這個 repo 值得看的是實測紀錄，但 09-25 起方法最硬的兩組只有我們自己看得到。
  索引列了 13 組實驗：已經寫在 README／CHANGELOG 的只寫結論、連過去，數字不重抄；另外寫了
  兩頁新的——修改型 PR 的 recall 基準線（Qodo PR-Review-Bench），以及把 repo 規範放進 prompt 的得失。
- README 開頭「這個 kit 對自己做過的兩件事」改成「實測紀錄」，補上上面那兩組，數字都帶分母與條件；
  §1 檔案總覽加上 `experiments/`。
- README §2 步驟 5 補一條：整份規範檔放進同一次呼叫，功能缺陷的 recall 會掉（盲標量過），
  只挑幾條的代價沒量過。
- USAGE「第 2 步」與 README §7 的「強制 action 釘 SHA 的 repo 目前不能用」改寫成 `v1.4.1` 起可以用。
  2026-09-26 在測試 repo 開著這個政策實測：collect、code-review、post 都跑到最後；同一個設定下，
  還停在 `v1.4.0` 的 caller 照樣被擋。沒實測到的也寫明了：測試 repo 沒有依賴清單，dependency review
  那個 job 是跳過的，而跳過的 job 不會被這個政策檢查。AI agent 安裝程序的前提檢查同步放寬
  （`sha_pinning_required` 是 `true` 也可以）。
- README 開頭「它在什麼標的上有用」的 ⛔ 那列標錯了標的。「Markdown／文件（27 檔）」底下的
  「16 筆只有 1 筆成立、註解密度 51.7%」出自一個 TypeScript／React PR（27 檔裡 14 個 TS/TSX、
  9 個文件），§4.7 寫的也是「TypeScript + React 專案的 PR」，51.7% 是排除文件後算的。
  這列改掛回「TypeScript／React，註解密度高」；markdown 那列換成真正的純文件 PR（§8 的 PR #1、
  §4.8 的 #24）。§9 那句「markdown 標的上 16 筆只有 1 筆成立」同步改。
- 同一段開頭那句「命中率由標的型態決定，不是由模型決定」改成「模型用 `deepseek-v4-pro` 的前提下，
  命中率主要看標的：型態，以及作者有沒有把決策理由寫在 code 旁邊」。改標之後表上有兩列
  TS/React、結論相反，原句跟表格對不上；而且那 16 筆裡有 10 筆是 flash 報的（0 筆成立），
  同一列本身就混了兩個模型。
- 標題下那句「便宜的先跑，貴的才跑」改寫：`01` 與 `03` 都在 PR 開啟／更新時直接觸發、同時跑，
  `04` 只看 `03` 的結果，AI review 不會等 linter，也不看它過沒過。實際的分工是 linter/SAST
  當合併關卡（§2 步驟 6），AI review 只給意見（§6）。

## [1.4.1] - 2026-09-26

> **patch**：kit 內部的 action 改釘 commit SHA，外加兩個 reusable 小修。reusable workflow 的介面沒動，
> caller 不用改任何東西，引用 `@v1` 的 repo 會自動拿到新版。
> 唯一要留意的是 Actions 政策設成 `selected` 的 repo：允許清單照 USAGE 寫 `@*` 的不受影響（`@*` 也配得到
> SHA 引用，2026-09-24 實測過）；如果寫死了 tag（例如 `reviewdog/action-setup@v1`），這一版起 kit 內部
> 改用 SHA 引用，會對不上而被擋，要改成 `@*`。

### Changed

- **workflow 裡的外部 action 全部改釘 commit SHA**（37 處：reusable workflow 內部 19 處、本 repo 自己的
  `01`／`02`／`05`／`eval-filter` 18 處）。開了「強制 action 釘 SHA」（Settings → Actions → General，
  API 欄位 `sha_pinning_required`）的 repo，之後就能用引用路線：2026-09-24 實測，這個政策擋的是
  kit 裡面的 tag 引用，caller 自己怎麼釘 kit 都沒用。複製路線的範本（`01`、`02`）也一起釘了。
  - 釘的是原本那個 tag 當下指向的 commit，action 本身的 code 一行都沒變。action 執行時才下載的東西
    （`reviewdog_version: latest` 的 binary、trivy 的漏洞資料庫、CodeQL bundle）本來就不受 SHA 控制，
    這點跟以前一樣。
  - 註解寫完整版本號並放在行尾（`# v7.0.1`）。Dependabot 換 SHA 時，是在註解裡找舊的完整版本字串換掉：
    只寫 `# v7`、或版本號後面還接著別的字，註解都不會跟著更新。
  - 新增 `.github/dependabot.yml`：github-actions 每週檢查一次，所有更新併成一個 PR。
  - 代價：以前 `@v7` 會自動拿到 action 的修正版，現在要走 Dependabot PR → merge → kit 發版，
    引用 `@v1` 的 repo 才拿得到。
- `tools/selftest.py` 從 17 組 96 項增加到 **18 組 100 項**。新增的那一組確認 workflow 裡的外部 action
  全部釘了 SHA、註解是完整版本號，而且 `run:` 裡沒有直接內插 input。釘 SHA 這件事被改壞時，本 repo
  的 CI 照樣全綠（本 repo 沒開那個政策，`03`／`04` 又跑已發布的 `@v1`），只有這裡擋得到。

### Fixed

- `reusable-ai-review-post.yml` 的 concurrency group 連 head repo 一起放。原本只用 branch 名，
  來自不同 repo（fork）的同名 branch（`main`、`patch-1` 這類）會落在同一個 group，後到的 run 會取消
  先到的，先到的那個 PR 就拿不到 review。這是看 code 發現的，沒有實際遇到。
- caller 傳進來的 6 個 input 改走 `env:`，不再直接內插進 `run:`：`reusable-ai-review-post.yml` 的
  `min-severity`、`min-confidence`、`max-inline`，以及 `reusable-static-review.yml` 的
  `lint-errorformat`、`lint-name`、`fail-level`。`'${{ … }}'` 是先展開才交給 shell，值裡有單引號就會
  提前結束引號。這些值由 caller 自己的 workflow 檔決定，不是外部 PR 作者控制的，所以這是一致性修正、
  不是注入漏洞；同一支檔案的其他 input 本來就走 env。

### Docs

- 釘版本的說明補上 `kit-ref`。`reusable-ai-review-post.yml` 與 `reusable-codeql.yml` 會用 `kit-ref`
  （預設 `v1`）另外 checkout kit 的腳本、內建 rubric 與 CodeQL 設定，所以只把 `uses:` 改成
  `@vX.Y.Z` 或 SHA，同一個 run 會兩層跑不同版本——README §8 早就記過這個實例，但給使用者看的
  釘版本說明一直只講改 `uses:`。
  - 補上的地方：`USAGE.md` 釘版本那一段（附範例）與兩張參數表（原本都沒列 `kit-ref`）、
    README §5「上游可以隨時換掉你跑的 code」、1.4.0 的升級說明（本檔與 Release）。
  - `v1.4.0` 的 tag 訊息同樣只寫了改 `uses:`，但不重打：tag 是不可變的（README §5 的承諾），
    以本檔為準。
- `SETUP-CHECKLIST.md` 的「（可選）建立 environment `ai-review`」改成整項跳過。它叫人把 `04` 的
  `# environment: ai-review` 取消註解，但那一行在 1.0.2 把 `04` 改成呼叫 reusable workflow 時就刪了，
  而呼叫 reusable 的 job 不能設 `environment:`（actionlint 會報 `"environment" is not available`）。
  `04` 開頭的註解一直寫著這件事，checklist 沒跟上。
- `SETUP-CHECKLIST.md` 標位置的方式從行號改成那一行的內容。原本 6 處行號有 4 處指錯：`04:19`
  兩處（實際在第 29 行）、`01-static-review.yml:48`（實際在第 50 行），以及上一條的 `04:31`
  （那一行已經不存在）。這份文件的行號在 1.0.0 之前就修過一次，改標內容之後，workflow 加減幾行
  也不會跑掉。
- `tools/eval/build_eval_set.py` 的註解更正：只取 AACR-Bench 的 Diff Level，理由從「只有這 47.4%
  在能力範圍內」改成「減少干擾變因」。`context` 欄位標的是寫那則 comment 需要多少上下文，不是只看
  diff 的能力上限：論文 Table 4 裡，DeepSeek-V3.2 不給上下文時，File／Repo Level 的問題仍各找得到
  三成多。
- `.github/scripts/post_review.py` 開頭 docstring 的「冪等」那條，把摘要的貼法寫錯了：寫的是
  `gh pr comment --edit-last --create-if-none`（每次編輯同一則留言），實際呼叫的是
  `gh pr review --comment`，每次執行都新建一則 review。冪等只做在 inline comment：同一個
  `(path, line)` 已經有帶 `<!-- deepseek-review -->` 標記的留言就不重貼。

## [1.4.0] - 2026-09-24

> **minor**：內建 rubric 的行為變更（見下面的 Changed），介面沒動，caller 不用改任何東西。
> 引用 `@v1` 的 repo 會自動拿到新版。想先觀察再升級，要**兩處一起**釘在 `v1.3.1`：
> `uses:` 改成 `@v1.3.1`，而且 `reusable-ai-review-post.yml`（以及 `reusable-codeql.yml`）
> 要傳 `kit-ref: v1.3.1`。只改 `uses:` 的話，rubric 會照樣從 `kit-ref` 的預設值 `v1`
> checkout，拿到的還是新版。（這段發版時只寫了改 `uses:`，2026-09-24 更正，見 `[1.4.1]`。）

### Changed

- **`prompts/review-rubric.md`：confidence 從「過濾門檻」改成「排序訊號」**（行為變更）。
  - 拿掉「低於 0.6 的 finding 請直接省略」和「不要用『可能』『或許』模糊帶過」。改成告訴模型
    這個數字拿來做什麼：0.7 以上貼成行內留言，低於 0.7 只列在摘要表；不確定的也照樣列出來，
    給低分就好。最高原則第 2 條的標題也從「不確定就不要報」改成「不要把推測寫成實測結論」，
    條文內容不變。
  - 依據：2026-09-24 做了一輪固定預算的迭代實驗，每輪決定保留或丟棄，而且只改 rubric。
    - 評估標的是三個合成標的：兩個埋了缺陷的標的，加上一個專門誘發「報已經做了的事」的探針。
    - 用 `deepseek-v4-pro`，每種寫法合計跑 30 次（三個標的各 10 次）。每一筆 finding
      都在看不到信心值的情況下標對錯。
    - 用信心值區分成立與不成立的 AUC，從 0.825 升到 0.876。
    - 在 0.7 門檻下，不成立的 finding 被貼成行內留言的比例從 83% 降到 71%；成立的從 97% 變成 95%。
  - ⚠️ 勝幅剛好壓在事先寫死的門檻（+0.05）上。把「部分成立」算成不成立時是 +0.052，
    算成成立時是 +0.040。評估標的全是合成的，還沒在真實 PR 上量過。接下來每個 PR 的 finding
    都會逐筆記錄信心值和對錯，看不到改善就改回來。
  - 同一輪還試了另一種改法，結果比原版更差，所以沒採用：替 confidence 定錨，依「實際確認過什麼」
    分成三級，AUC 掉到 0.773（只跑了 15 次）。中間那一級變成安全區，成立的和不成立的都擠進去。
    這又是一次「要求模型照規則自評」比原版還差的例子，跟 README §4.7 的結論方向一致。
  - 摘要表會變長：原本不到 0.6 就被省略的 finding，現在會以低分列進摘要表。
    同一批標的上，finding 總數多了 13%。
  - 如果你改了 `min-confidence`，內建 rubric 裡寫的 0.7 不會跟著變。
- `tools/selftest.py` 從 16 組 93 項增加到 **17 組 96 項**。新增的那一組確認 rubric 告訴模型的門檻，
  跟 reusable workflow 和 `post_review.py` 的 `min-confidence` 預設值一致。同一個數字寫在三個地方，
  改一處漏一處的話，rubric 會對模型講錯而沒有人發現。

### Docs

- README §8：CodeQL 其餘 27 筆（`py/path-injection` 25、`py/full-ssrf` 2）分流完畢，
  **0 筆成立、全部以 won't fix dismiss**。source 全是 argv 或環境變數，每個執行情境裡
  設值的都是本來就有同等權限的一方；不受信任的資料（artifact、模型輸出）只被讀，
  不拿來組路徑或 URL。原本那句「27 筆的汙染源是 workflow 寫死的 argv」說過頭了——
  驗過的只有 `04` 側 13 筆，`tools/` 的 14 筆根本不是由寫死的 workflow 呼叫的，已改寫。
- README §4.8 的 09-22 dogfood 紀錄更正：原寫「四次、4 筆 finding」，實為**三個 PR、
  五次 run、7 筆 finding**——#21 的第二、三次 run 被當成了同一次，兩次各 3 筆、內容
  完全不同。漏記的 3 筆補驗後同樣不成立，「0 筆成立」不變。1.3.1 那條把這段的位置
  寫成 README §8，實際在 §4.8。
- 那段原本插在 §4.8「對照組」的敘事中間，害後面那句「第 1 筆特別值得一提」看起來
  在講 09-22 那批；移到 §4.8 尾端。段內「見上面『行號由程式算』那節」改指 §8 的那條。
- 補上 `v1.3.0` 到 `v1.3.1`（#23–#28）的 dogfood：七次 run、2 筆 finding、1 筆成立。
  成立的是編輯時被吃掉的一個空格（`ROOT =pathlib`），原本預期是誤報。
- `SETUP-CHECKLIST.md` §9 的 selftest 那一行：括號列的是測項涵蓋範圍，但 #20 之後的
  三次更新（#22、#21、#27）都只改了組數與項數，#21 的禁用詞掃描、#27 的『』 片段挖取
  沒補進去；#20 寫的括號本身也沒明確涵蓋另外四組。補齊六組後，16 組在括號裡都有對應。
- workflow 數量有兩處還停在初版的 5 個：`SETUP-CHECKLIST.md` §9 的已驗證清單，以及
  `github-pr-cicd-code-review-research.md` 頭部的配套實作說明（同一句的腳本數也還是
  當時的 2 支）。改成現況：10 個 workflow、`.github/scripts/` 下 3 支腳本；§9 那條的
  驗證方式也從「可被解析」改成本機實際在跑的 `actionlint`。
- `USAGE.md` 開頭加上「給 AI agent 的安裝程序」：使用者可以把這份文件交給自己 repo 裡的
  coding agent，讓它照著裝。內容包括前提檢查、要裝哪幾支、每一步怎麼驗證、哪幾步要停下來
  交給人（API key 不經過 agent，也不貼進對話），以及裝好之後的樣子。踩坑的部分直接引用原本的
  「四個最容易踩的坑」，不另寫一份。開頭要求 agent 用 `curl` 讀原文，因為 WebFetch 這類
  工具回傳的是摘要，YAML 會被改寫。
- `USAGE.md` 補上三件原本沒寫的事：
  - 只有開 PR 才會觸發。
  - `code-review.yml` 裡的 dependency review 與 CodeQL，在 private repo 上只有「組織帳號、
    而且開了 GitHub Code Security」才能用，個人帳號的 private repo 不能用（附上 GitHub 文件連結）。
  - bot 開的 PR 一樣會觸發，大 PR 也只審前 400 KB。
- `USAGE.md` 的 `code-review.yml` 範例註解寫的是「三個最容易踩的坑」的第 4 點，但那一節從
  USAGE 第一版（`d3dcaec`）開始就是四個。
- `USAGE.md` 的「第 2 步」補上 Actions 政策（Settings → Actions → General）：2026-09-24 在測試 repo
  切換四組設定實測。這是 tautin 驗收時 AI 提出、之前一直沒測的坑。
  - 「只允許自己帳號的 action」：kit 裡面用到的 `actions/checkout` 等會被擋，每一支都 `startup_failure`，
    連 collect 也是，post 根本不會被觸發。
  - `selected` 模式要允許的清單已列出。其中 `aquasecurity/setup-trivy` 是 `trivy-action` 內部引用的，
    照 workflow 裡的 `uses:` 抄一定會漏；「把 kit 本身加進清單」那條我們測不到，文件裡寫明了。
  - **強制 action 釘 SHA 的 repo 目前不能用引用路線**：kit 內部的 action 是用 tag 引用的，caller 把 `@v1`
    換成 SHA 也沒用。
  - AI agent 的安裝程序多了一項前提檢查（`gh api 'repos/{owner}/{repo}/actions/permissions'`）。
- `USAGE.md`「四個最容易踩的坑」第 4 點原本說這種失敗「特別難查」，但網頁上那個 run 頁面的
  Annotations 一直都寫著原因（回頭抓了三個歷史 run 都有）。已改成指向 Annotations，並補上怎麼跟
  Actions 政策區分：CLI 上的訊息一模一樣。README §7 疑難排解同步加了兩列。
- `USAGE.md` 釘版本的範例更新到 `@v1.4.0`。

## [1.3.1] - 2026-09-23

### Security

- `locate.py` 從 evidence／body 挖『』引號內容的 regex（`『(.+?)』`，`re.S`）遇到沒有收尾的
  『 會退化成**平方時間**：每個 『 都各自往後掃到字串尾。輸入是模型輸出，PR 的 diff
  可以透過 prompt injection 左右它，而它跑在 `04`（帶 secret 的那一側）。
  實測 64K 字元 5.4 秒、128K 字元 21.7 秒。
  - **實際風險低**：模型輸出上限是 8192 token（reusable 沒有開放調整）。以本機實測外推
    （runner 抓慢 3 倍、兩支 script 各跑一次），要撞到 job 的 20 分鐘 timeout 得塞進
    約 39 萬字元。不會外洩任何東西，最壞是拖慢那一個 PR 的 review。
  - 改成 `str.find` 手寫迴圈，結果與原 regex 逐筆相同（隨機 30 萬筆加 13 個邊界比對），
    時間變線性（128K 字元：21.7 秒 → 0.04 毫秒）。
  - 這筆是 CodeQL `py/polynomial-redos` 報的。同一批另外三筆（`deepseek_review.py:145`、
    `locate.py:57`、`post_review.py:68`）實測線性，已標為 false positive——保護來自
    `re.M` 與 `splitlines()`，同一個 regex 拿掉這層就是平方。

### Changed

- `tools/selftest.py` 從 15 組 86 項增加到 **16 組 93 項**：新增一組釘住上面那筆修正。
  前五項驗結果沒變（巢狀、緊接的 』、跨行、沒有收尾），**修改前後都必須通過**；
  後兩項是 64K 字元的時間探針，修改前各跑 5.4 秒而 FAIL。第二種形狀（唯一的 』 在
  最前面）擋的是「先查字串裡有沒有 』 再跑 regex」這種不完整的修法。

### Docs

- README §8 補上「零告警」的現況：#19 打開 local threat model 之後，本 repo 自己從
  0 筆變 31 筆，PR 上的 CodeQL check 照樣是綠的，一天半沒有人發現。記下 4 筆 ReDoS
  的分流結果，以及其餘 27 筆尚未逐筆處理。
- README §7 新增一列：**caller 新傳一個 secret、merge 進 default branch 之後 `04`
  變成 `startup_failure`**。原因是 caller 引用 `@v1`，而那個 secret 是還沒發版的
  reusable 才認識的。這個失敗在 PR 上驗不到——`04` 由 `workflow_run` 觸發、跑的是
  **default branch** 的 caller，merge 前那還是舊的，所以它只在「merge 後、發版前」
  這段窗口炸。本 repo 自己在 `v1.3.0` 發版前踩過，窗口大約兩分鐘。
  正確順序是**先發版、再讓 caller 傳新 secret**。
- README §8 補上 2026-09-22 的四次 dogfood：**4 筆 finding、0 筆成立**，
  三筆的失效模式各不相同（假設的輸入情境不存在、報「已經做了的事」、
  技術斷言與當天的實測直接矛盾）。已註明這批數字不推翻也不強化既有結論——
  標的以文件與測試為主、`n=4` 太小，放進來是因為失效模式比成立率有資訊量。
- `USAGE.md` 釘版本的範例更新到 `@v1.3.1`。

## [1.3.0] - 2026-09-22

### Added

- **送出前的禁用詞掃描**（`REVIEW_BLOCKED_TERMS`，選填 secret）。這套工具每次跑都會把
  diff、PR 標題、rubric 送到 DeepSeek 的 API，而 DeepSeek 的隱私政策明寫會用使用者輸入
  訓練模型。設了這個 secret 之後，送出前會做一次大小寫不敏感的子字串比對，
  **命中就拒送、不呼叫 API**（新增離開碼 `3`）。
  - 判準不是「repo 是 public 還是 private」，是「**這個字串終將公開，還是永遠不該公開**」。
    前者送出去只是提前，後者的損失不隨時間衰減。
  - 清單走 secret 不走設定檔——把要保護的字串 commit 進 repo 是自相矛盾的。
    命中時的錯誤訊息**只給條號不給內容**，因為 CI log 是公開的。
  - 空行與 `#` 註解會略過；**少於 3 個字元的詞會被忽略並印 warning**。
    這兩條不是便利功能：空字串是 `in` 任何字串都成立的，沒濾掉會讓整條 pipeline
    變成永遠拒送，而那個故障看起來像「掃描很嚴格」。過短的詞還有第二個問題——
    **Actions 會把 secret 的值在 log 裡遮成 `***`，包括它出現在別的字當中的時候**；
    2026-09-22 實測放一條兩字元的 `ab`，整份 log 的 `reusable` 都變成 `reus***le`。
  - ⚠️ 邊界：確定性字串比對，攔不住換句話說的同一件事，也攔不住沒列進清單的東西。
    未設這個 secret 時完全不掃，行為與加這個功能之前一致。
  - `reusable-ai-review-post.yml` 新增同名的選填 secret；本 repo 自己的 `04` caller
    也接上去（沒設值＝空字串＝不掃）——教別人用的路徑自己不跑，正是靜默分岔的來源。

### Fixed

- **`extract_json` 不再把 finding 內容裡的 code fence 當成整份回應的外包裝。**
  2026-09-22 真實事故：模型在 finding 的 `body` 裡寫 markdown code fence 給修正建議
  （下面這段用四個反引號包住，因為它自己就含有三個反引號的 fence）：

  ````
  "body": "建議修正為：\n```yaml\nFOO: ${{ secrets.FOO }}\n```"
  ````

  而舊的順序是「**先剝 fence 再 `json.loads`**」，剝的方式又是 `re.search` 一個
  非貪婪 pattern——它會抓到整份回應裡**任何一段** fence，包括上面那一段。於是
  一份**完整且合法**的 JSON 被換成那段 YAML，`find("{")`／`rfind("}")` 再從裡面
  切出 `{{ secrets.FOO }}`，最後報 `Expecting property name ... line 1 column 2`。
  症狀指向「模型吐了畸形 JSON」，真因是我們自己把它剝壞了。
  - 改成先試整份（本來就有 `response_format: json_object`，這條該最先中），
    失敗才剝 fence，而且 fence 必須包住**整個** text（`^...$` 錨定）才剝。
  - ⚠️ **AI review 給修正建議時本來就會寫 code fence**，所以這不是罕見輸入。
    `v1.0.0` 起就存在，那天是第一次真的踩到——整個 review 解析失敗、exit 2、
    PR 上一則留言都沒有。
  - 這條也擋住了上一版修正的生效：`incomplete_json_error` 在它後面，內容被剝壞
    之後根本走不到。修掉 fence 之後，同一份真實回應才正確報出「JSON 在字串中途結束」。
- **`extract_json` 不再讓「內容不完整」偽裝成「格式錯誤」。** 第二層 fallback 用
  `text.rfind("}")` 找結尾，內容被切斷時它抓到的是**中途某一筆的收尾 `}`**，
  切出來的片段必然語法錯誤，於是 `JSONDecodeError` 指向片段裡的奇怪位置
  （實例：`Expecting ',' delimiter: line 1 column 92`）——讀起來像模型吐了畸形
  JSON，真因卻是少了尾巴。現在先掃一遍括號與字串狀態，講明「JSON 在中途結束
  （還有 N 層括號沒有收尾）」或「JSON 在字串中途結束」。有 `{` 卻連一個 `}`
  都沒有的情況，原本報「回應中找不到 JSON 物件」，也一併改成報不完整。
  ⚠️ 與 `v1.2.2` 修的截斷偵測是**不同路徑**：那條看 `finish_reason == "length"`，
  是 API 自己說了它截斷；這條處理的是 finish_reason 正常、content 卻真的不完整。
  括號平衡但語法錯（`{"a": }`）與收尾多過開頭（`{"a": 1}}`）仍然報格式錯誤，
  不會被講成不完整——兩者都有測項釘著。
- **解析失敗時印的原始輸出改成頭尾都印、並標明總長度**（原本只印 `content[:2000]`）。
  內容不完整時斷點在尾巴，印開頭正好把唯一有診斷價值的地方切掉，而且看不出總長度
  ——「被切斷」和「模型從頭就亂吐」在 log 上長得一模一樣。

### Changed

- `tools/selftest.py` 從 12 組 49 項增加到 **15 組 86 項**：
  - 新增兩組，涵蓋不完整偵測與診斷輸出（含「括號平衡但語法錯」「收尾多過開頭」
    兩個誤報探針，以及字串內含括號、跳脫引號這些不可誤判的護欄）。
  - `[13]` 組再補 7 項，涵蓋 code fence 那條修正：兩項驗「`body` 含 fence 的合法
    JSON 解析得出來且內容沒被剝壞」，四項是 never-break 護欄（純 JSON、整份被
    fence 包住、前後綴雜訊、雜訊加 fence）——這四項**在修改前後都必須通過**，
    否則只證明了新行為出現，沒證明舊能力還在。
  - 新增一組涵蓋禁用詞掃描（含「清單只有空行」「詞太短」兩個防止靜默擋一切的探針，
    以及一條專門釘住「回傳值不可以帶出禁用詞本身」的斷言）。
  - README badge 與 `SETUP-CHECKLIST.md` §9 一併更新——後兩處先前分別停在 `49`
    與 `9 項`，是發版時漏掃的。
- `review-local.sh` 檔頭不再教 `export DEEPSEEK_API_KEY=sk-xxxx`：那會把金鑰明文留在
  shell history 裡，而 history 不會過期也沒有人在看守。改為提示 `read -rs` 或 macOS
  Keychain 的取法，並說明這支腳本只從環境變數讀、不吃命令列參數（後者會出現在 `ps`）。

- `codeql-config.yml` 加上 `threat-models: local`。**預設的 threat model 只把「遠端」
  輸入當汙染源**，命令列參數、環境變數、檔案系統屬於 local source——所以
  `sys.argv` 流進 `subprocess.run(..., shell=True)` 這種本機工具的 command injection，
  預設設定下**不會被報出來**。實測（刻意寫壞的 104 行 Python）：預設 4 筆告警，
  加上這個設定變 7 筆，多出來的三筆全是需要追資料流的
  （`py/command-line-injection`、`py/partial-ssrf`、`py/path-injection`）。
  複製這份設定的 repo 若掃的是 CLI 工具或 CI 腳本，這個設定通常才是你要的。

### Docs

- `USAGE.md` 釘版本的範例更新到 `@v1.3.0`。⚠️ 這個位置漏掃過一次——`v1.2.2` 發版時
  它還停在 `@v1.2.1`，是事後盤點才撈到的。版本號散落處見 README §5。
- README §8 補上「本 repo 零告警」那句的前提，以及查 PR alert 要用
  `refs/pull/<n>/merge` 而不是 `refs/heads/<branch>`。

## [1.2.2] - 2026-09-21

### Fixed

- `review-local.sh` 沒有傳 `--rules-dir`，本機跑**永遠不會套用** `prompts/rules/*.md`。
  CI 走 reusable workflow 時 `typed-rules` 預設開啟，所以同一份 diff 在本機與 CI
  會得到不一樣的結果，而兩邊都不會提示。
- 模型輸出被 `max_tokens` 砍斷時，錯誤訊息是「回應中找不到 JSON 物件」——
  JSON 格式其實完全正確，只是少了尾巴。症狀指向格式、真因是長度，而 token 費用照算。
  現在會直接說明是截斷，並區分兩種成因（額度不足 vs thinking 吃光額度）。
- 截斷提示的分流條件從「`content` 空不空」改成「thinking 開著沒」。
  thinking 開著時就算已經有部分輸出，首要嫌疑仍然是 reasoning 吃掉額度
  （2026-09-19 實測：`--max-tokens` 給到 32768 仍被截斷，reasoning 自己用掉 31408），
  舊的分流會在這種情況下叫使用者去調一個沒用的參數。
  **這筆是 kit 自己的 review 在 PR #17 報出來的**（3 筆裡唯一完全成立的一筆）。
- `truncation_error` 接受 `content` 為 `None`——OpenAI 相容回應的 `content` 可能是 null，
  偵測本身不應該先崩掉。
- `deepseek_review.py` 檔頭 docstring 寫著 `DEEPSEEK_MODEL` 預設 `deepseek-flash`，
  實際預設是 `deepseek-v4-pro`。

### Added

- `review-local.sh` 支援 `MAX_TOKENS` 環境變數。截斷訊息會要求使用者調高額度，
  本機入口就必須真的調得動。
- README §9「為什麼會有這個 repo」。
- `tools/selftest.py` 新增兩組測試（37 → 49 項）：截斷偵測的四種情境，
  以及本機入口與 CI 的參數對齊檢查。

## [1.2.1] - 2026-09-21

### Fixed

- 把 `reusable-ai-review-post.yml` 的 `filter-findings` input 加回成 no-op。
  v1.2.0 移除它是**掛在 minor 版號上的破壞性變更**，而 `v1` 是浮動 tag ——
  打 tag 的那一刻就自動推播給所有引用 `@v1` 的 caller，傳了那個參數的人會直接
  `startup_failure`。零受害純屬運氣（0 star / 0 fork，暴露窗口 68 分鐘）。

### Deprecated

- `filter-findings` 標記為 deprecated，傳入時印 `::warning::`。v2 才會真的移除。

### Added

- README §5 補上「上游可以隨時換掉你跑的 code」這一格威脅，含 `v1` 浮動 tag 的
  三條相容性承諾，以及自己破過一次的紀錄。

## [1.2.0] - 2026-09-21

### Removed

- **BREAKING:** 移除 `reusable-ai-review-post.yml` 的 `filter-findings` input。
  ⚠️ 這是個錯誤——破壞性變更不該掛在 minor 版號上，v1.2.1 已修正為 no-op。
- 移除 review filter 那一層。用 700 則人工標註資料實測：**誤刪 15 筆正確的、
  只刪對 4 筆**，precision 反而變差。評估工具保留在 `tools/eval/`，
  任何人都能拿自己的 prompt 重跑。
- 移除一個構成衍生作品的檔案。

### Added

- MIT LICENSE。先前沒有 LICENSE 等於保留所有權利，而文件卻在教人複製檔案。
- `tools/eval/` 評估框架（AACR-Bench、`workflow_dispatch` 觸發、API key 不離開 GitHub）。

### Changed

- README 分段對齊現狀。

## [1.1.1] - 2026-09-21

### Fixed

- 兩個**靜默失效**：不報錯、step 全 success、log 看起來正常。
  - review filter 因為兩邊比對邏輯分岔（一邊用原始子字串、一邊壓縮空白），
    永遠不會刪掉任何 finding。
  - 定位層把模型**報對的**行號改成錯的——`existing_code` 裡的反引號被當成散文
    挖取片段，導致比對到錯誤位置。

## [1.1.0] - 2026-09-21

### Added

- 定位機制 `locate.py`：行號改由程式用程式碼片段文字比對算出，不採信模型自報的值。
  實測 16 筆 finding 只有 **1 筆**真的指向它自己引用的那段 code，其餘偏移 +1 到 +24 行。
- 依 diff 涵蓋的檔案型態附加補充規則（`prompts/rules/github-workflows.md`、`python.md`）。
  規則走 user message 不走 system prompt，不影響 context caching 命中。
- review filter（v1.2.0 實測後移除）。

## [1.0.2] - 2026-09-21

### Fixed

- `gh pr review` 少了 `--repo`：走 reusable workflow 時 kit 被 checkout 到 `.kit`
  子目錄，工作目錄根沒有 git repo，導致摘要貼不出去——而 job 仍然回報 success，
  症狀是「全綠但零留言」。
- USAGE.md 的錯誤建議：DeepSeek 平台沒有消費上限設定，計費是預付制。

### Changed

- kit 自己的 `03`／`04` 改用 reusable workflow（dogfood）。上線第一天就抓到
  只有 reusable 版才會出現的 bug（即上述 `--repo`）。

### Added

- USAGE.md 補上 fork PR 核可政策的設定指令。

## [1.0.1] - 2026-09-21

### Security

- 修掉 shell injection：不帶引號的 heredoc（`<<EOF`）內插使用者可控的值時，
  `toJSON()` 只做 JSON 跳脫、擋不住命令替換——PR 標題寫 `$(whoami)` 就會執行。
  改為「值走 `env:`、heredoc 帶引號」。這筆是 `actionlint` 抓到的，AI review 沒報。

### Fixed

- 修掉 AI review 報的兩個 finding。

## [1.0.0] - 2026-09-21

### Added

- 四支可重用 workflow（`reusable-static-review`、`reusable-codeql`、
  `reusable-ai-review-collect`、`reusable-ai-review-post`），其他 repo 可以用引用的
  方式導入，不必複製腳本也不必複製 rubric。
- `USAGE.md`：三步驟導入說明與可直接複製的 caller 範本。

[Unreleased]: https://github.com/tznthou/deepseek-code-review/compare/v1.4.1...HEAD
[1.4.1]: https://github.com/tznthou/deepseek-code-review/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/tznthou/deepseek-code-review/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/tznthou/deepseek-code-review/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/tznthou/deepseek-code-review/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/tznthou/deepseek-code-review/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/tznthou/deepseek-code-review/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/tznthou/deepseek-code-review/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/tznthou/deepseek-code-review/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/tznthou/deepseek-code-review/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/tznthou/deepseek-code-review/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/tznthou/deepseek-code-review/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/tznthou/deepseek-code-review/releases/tag/v1.0.0
