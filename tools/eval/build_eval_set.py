#!/usr/bin/env python3
"""從 AACR-Bench 建出可以用來評估 review filter 的資料集。

AACR-Bench（`Alibaba-Aone/aacr-bench`，Apache-2.0）逐則標註了 2,145 個 code review
comment 的對錯。它沒有附 diff，只給 PR 網址與 commit SHA，所以這支要自己去抓。

## 為什麼只取一個子集

`context` 欄位把每則 comment 標成判斷它需要多少上下文：

    Diff Level  1,017 (47.4%)   錯誤率 25.9%
    File Level    744 (34.7%)   錯誤率 30.4%
    Repo Level    384 (17.9%)   錯誤率 39.3%

本 kit 是單次 API 呼叫、只看得到 diff、沒有讀檔工具。File Level 與 Repo Level
的 comment 要判對錯，需要 diff 以外的資訊；混進來的話，「filter 判斷失準」和
「缺資訊」會攪在一起分不開。所以只取 Diff Level，為的是減少干擾變因。

這不是說另外兩層只看 diff 就做不到：`context` 標的是寫這則 comment 需要多少
上下文，不是能力上限。AACR-Bench 論文（arXiv 2601.19494）Table 4 裡，
DeepSeek-V3.2 在不給上下文的設定下，File Level 與 Repo Level 的問題仍各找得到
三成多。

再加上 `is_ai_comment=True`（filter 要處理的正是 AI 產的 comment），子集是 760 則。

## 兩個抓資料的坑

1. **不要用 compare API。** `compare/{pr_target_commit}...{pr_source_commit}` 抓到的
   不是該 PR 的變更——實測 FreeCAD#18688 交集是 0，連 basename 都對不上，因為
   target commit 是 base branch 後來的狀態，兩點之間夾著別人的 commit。
   要用 `repos/{repo}/pulls/{number}` 帶 diff media type，實測交集 100%。

2. **要排除「檔案已不在 PR diff 裡」的 comment。** 標註是在某個時間點做的，
   有些 PR 之後被 force push 或追加 commit，現在抓到的 diff 跟標註當時不同
   （例如 gemini-cli#5819 現在動的是完全不同的檔案）。這類 comment 留著會讓
   filter 因為「找不到對應的 code」而刪掉它們，**高估抓錯能力**。
   實測 760 則裡有 60 則屬於這種，排除後剩 700 則。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

DATASET_URL = "https://huggingface.co/datasets/Alibaba-Aone/aacr-bench/resolve/main/dataset.json"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_dataset(cache_path):
    if os.path.exists(cache_path):
        log(f"[info] 用既有的 {cache_path}")
        with open(cache_path, encoding="utf-8") as fh:
            return json.load(fh)
    log(f"[info] 下載 {DATASET_URL}")
    with urllib.request.urlopen(DATASET_URL, timeout=120) as resp:
        raw = resp.read()
    with open(cache_path, "wb") as fh:
        fh.write(raw)
    return json.loads(raw.decode("utf-8"))


def fetch_pr_diff(repo, num, retries=3):
    """用 PR 編號抓 diff。回傳 (diff, error)。"""
    for attempt in range(retries + 1):
        r = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{num}",
             "-H", "Accept: application/vnd.github.v3.diff"],
            capture_output=True, text=False,
        )
        if r.returncode == 0:
            # diff 可能含非 UTF-8 位元組，不能用 text=True
            return r.stdout.decode("utf-8", "replace"), None
        err = r.stderr.decode("utf-8", "replace").strip()
        if "rate limit" in err.lower() and attempt < retries:
            time.sleep(30)
            continue
        if attempt < retries:
            time.sleep(2 ** attempt)
            continue
        return None, err[:120]
    return None, "retries exhausted"


def slice_to_files(diff, wanted):
    """只留 wanted 這些檔案的 diff 區塊。"""
    out, keep = [], False
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            m = re.search(r" b/(.+?)\s*$", line)
            keep = bool(m and m.group(1).strip() in wanted)
        if keep:
            out.append(line)
    return "".join(out)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.environ.get("EVAL_SET_OUT", os.path.join(here, "eval_set.json"))
    cache = os.environ.get("AACR_CACHE", os.path.join(here, "dataset.json"))
    limit = int(os.environ.get("EVAL_LIMIT", "0"))

    rows = load_dataset(cache)
    sub = [r for r in rows if r["is_ai_comment"] and r["context"] == "Diff Level"]
    by_pr = {}
    for r in sub:
        by_pr.setdefault(r["pr_url"], []).append(r)
    log(f"[info] 子集：{len(sub)} 則 comment、{len(by_pr)} 個 PR")

    urls = list(by_pr)[:limit] if limit else list(by_pr)
    items, failed, dropped = [], [], {"label0": 0, "label1": 0}

    for i, url in enumerate(urls, 1):
        cs = by_pr[url]
        repo = "/".join(url.split("/")[3:5])
        num = url.rstrip("/").split("/")[-1]
        diff, err = fetch_pr_diff(repo, num)
        if err:
            failed.append((url, err))
            log(f"[{i}/{len(urls)}] ❌ {repo}#{num} {err}")
            continue

        wanted = {c["path"] for c in cs}
        sliced = slice_to_files(diff, wanted)
        present = set(re.findall(r"^diff --git a/.+ b/(.+)$", sliced, re.M))

        keep = []
        for c in cs:
            if c["path"] in present:
                keep.append(c)
            else:
                dropped["label0" if c["label"] == 0 else "label1"] += 1
        if not keep:
            log(f"[{i}/{len(urls)}] ⏭️  {repo}#{num} 全部 comment 的檔案都不在現在的 diff 裡")
            continue

        items.append({
            "url": url, "repo": repo, "number": num, "diff": sliced,
            "comments": [{
                "note": c["note"], "path": c["path"],
                "from_line": c["from_line"], "to_line": c["to_line"],
                "category": c["category"], "label": c["label"],
                "source_model": c["source_model"],
            } for c in keep],
        })
        log(f"[{i}/{len(urls)}] ✅ {repo}#{num}  {len(sliced)//1024} KB  {len(keep)}/{len(cs)} 則")

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False)
    n = sum(len(x["comments"]) for x in items)
    n1 = sum(1 for x in items for c in x["comments"] if c["label"] == 1)
    log("")
    log(f"[info] 有效評估集：{len(items)} 個 PR、{n} 則 comment"
        f"（正確 {n1} / 錯誤 {n - n1}）→ {out_path}")
    log(f"[info] 排除 {dropped['label0'] + dropped['label1']} 則"
        f"（檔案已不在現在的 PR diff 裡：錯誤 {dropped['label0']} / 正確 {dropped['label1']}）")
    if failed:
        log(f"[warn] {len(failed)} 個 PR 抓不到 diff")
        for u, e in failed[:5]:
            log(f"       {u} — {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
