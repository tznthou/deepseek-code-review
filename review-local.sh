#!/usr/bin/env bash
# 在本機跑一次 DeepSeek review，不碰 GitHub、不貼留言。
#
# 用法：
#   export DEEPSEEK_API_KEY=sk-xxxx
#   ./review-local.sh                 # 預設比對 origin/main
#   ./review-local.sh origin/develop  # 指定 base ref
#   ./review-local.sh HEAD~3          # 也可以只比最近三個 commit
#
# 環境變數：
#   DEEPSEEK_MODEL  模型（預設 deepseek-v4-pro）
#   MAX_TOKENS      輸出上限（預設 8192）。缺陷密度高的 diff 會吐超過這個額度，
#                   被截斷時腳本會直接告訴你要調高，不會偽裝成解析失敗。
#
# 產出：/tmp/deepseek-review.md（人看）與 /tmp/deepseek-findings.json（機器看）

set -euo pipefail

BASE_REF="${1:-origin/main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIFF_FILE="${TMPDIR:-/tmp}/deepseek-pr.diff"
OUT_MD="${TMPDIR:-/tmp}/deepseek-review.md"
OUT_JSON="${TMPDIR:-/tmp}/deepseek-findings.json"

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "請先設定 DEEPSEEK_API_KEY" >&2
  exit 1
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "請在 git repository 內執行" >&2
  exit 1
fi

echo "==> 產生 diff：${BASE_REF}...HEAD"
git diff --unified=3 "${BASE_REF}...HEAD" > "$DIFF_FILE"
echo "    $(wc -c < "$DIFF_FILE") bytes / $(grep -c '^diff --git' "$DIFF_FILE" || true) 個檔案"

if [[ ! -s "$DIFF_FILE" ]]; then
  echo "沒有任何變更，結束"
  exit 0
fi

{
  echo '{'
  echo "  \"base_ref\": \"${BASE_REF}\","
  echo "  \"head_sha\": \"$(git rev-parse HEAD)\","
  echo "  \"branch\": \"$(git rev-parse --abbrev-ref HEAD)\""
  echo '}'
} > "${TMPDIR:-/tmp}/deepseek-meta.json"

# --rules-dir 必須傳：CI 走 reusable workflow 時 typed-rules 預設開啟，
# 本機少了這個參數就不會套 prompts/rules/*.md，同一份 diff 在本機與 CI 會得到
# 不一樣的結果，而且兩邊都不會提示。2026-09-21 實測踩過一次。
python3 "$SCRIPT_DIR/.github/scripts/deepseek_review.py" \
  --diff "$DIFF_FILE" \
  --meta "${TMPDIR:-/tmp}/deepseek-meta.json" \
  --rubric "$SCRIPT_DIR/prompts/review-rubric.md" \
  --rules-dir "$SCRIPT_DIR/prompts/rules" \
  --max-tokens "${MAX_TOKENS:-8192}" \
  --out "$OUT_MD" \
  --findings-out "$OUT_JSON"

echo
echo "==> review 已寫入 $OUT_MD"
echo "==> findings 已寫入 $OUT_JSON"
echo
cat "$OUT_MD"
