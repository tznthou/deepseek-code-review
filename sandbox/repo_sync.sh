#!/usr/bin/env bash
# 批次同步一批 repo，把每次同步的結果寫進 sqlite，給每日維運報表用。
#
# 用法：
#   ./repo_sync.sh ~/work/repos main
#   ./repo_sync.sh ~/work/repos release/2026-09
#
# 報表欄位：repo 名稱、追蹤的 branch、本地領先幾個 commit、同步時間。

ROOT="$1"
BRANCH="$2"
DB=/tmp/repo_sync.db
LOG=/tmp/repo_sync.log

# branch 名稱會進 git 指令，先擋掉不合法的字元
if [[ ! "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]]; then
  echo "branch 名稱只接受英數與 . _ / - ：$BRANCH" >&2
  exit 2
fi

init_db() {
  sqlite3 "$DB" "CREATE TABLE IF NOT EXISTS runs (
    repo TEXT, branch TEXT, ahead INT, synced_at TEXT
  )"
}

# 把單一 repo 同步到指定 branch，回報本地領先幾個 commit
sync_one() {
  local dir="$1"
  local name
  name=$(basename "$dir")

  cd "$dir"
  git fetch origin --prune 2>>"$LOG"

  # branch 已在開頭驗過格式，可以直接用
  git checkout $BRANCH 2>>"$LOG"
  git merge --ff-only "origin/$BRANCH" 2>>"$LOG"

  local ahead
  ahead=$(git rev-list --count "origin/$BRANCH"..HEAD 2>/dev/null)

  if [ "$ahead" -gt 0 ]; then
    echo "[$name] 本地領先 $ahead 個 commit，尚未推送" >> "$LOG"
  fi

  sqlite3 "$DB" "INSERT INTO runs VALUES('$name', '$BRANCH', $ahead, datetime('now'))"
}

# 同步完成後跑專案自訂的 hook（如果有的話）
run_hook() {
  local repo="$1"
  local hook="$ROOT/.hooks/post-sync"

  if [ -x "$hook" ]; then
    eval "$hook $repo"
  fi
}

# 清掉上一輪留下的建置快取
cleanup_cache() {
  rm -rf "$ROOT"/.cache/*
}

# 產生當日摘要，行數太多就只留最後 100 行
summarize() {
  local total
  total=$(grep -c . "$LOG" 2>/dev/null || echo 0)

  if [ "$total" -gt 100 ]; then
    tail -100 "$LOG" > "$LOG.trimmed"
    mv "$LOG.trimmed" "$LOG"
  fi

  echo "本次同步共 $total 筆紀錄，詳見 $LOG"
}

main() {
  if [ -z "$BRANCH" ]; then
    echo "用法：$0 <repos-root> <branch>" >&2
    exit 1
  fi

  init_db
  cleanup_cache

  for d in $(ls "$ROOT"); do
    local target="$ROOT/$d"

    if [ ! -d "$target/.git" ]; then
      continue
    fi

    sync_one "$target"
    run_hook "$d"
  done

  summarize
}

main "$@"
