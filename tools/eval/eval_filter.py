#!/usr/bin/env python3
"""用 AACR-Bench 的人工標註，評估一份「過濾 finding」的 prompt 到底刪對還是刪錯。

資料集怎麼來、為什麼只取那個子集，見 `build_eval_set.py` 的說明。

## 指標的分母刻意不用「filter 刪了幾筆」

那個數字是 filter 自己決定的——拿它當分母，「少刪一點」會看起來像「變準了」。
兩個主要指標的分母都固定，由資料集給定：

    誤刪率 = 誤刪數 / 全部 label=1 的數量     ← 最貴的錯誤
    抓錯率 = 刪對數 / 全部 label=0 的數量

誤刪比漏抓貴得多：留下一筆錯的 finding，讀的人自己會判斷；刪掉一筆對的，
他連看都看不到。所以 filter 的設計目標是「誤刪率趨近 0」，不是「抓錯率最大化」。

⚠️ 這支**不內建任何 filter prompt**，要自己用 `--filter-prompt` 指一份進來。

本 kit 曾經內建過一份（參考另一個專案的設計寫的），2026-09-21 用這套工具實測的
結果是：它誤刪 15 筆正確的、只刪對 4 筆，precision 從 72.71% 掉到 72.54% ——
誤刪是刪對的 3.75 倍。那份 prompt 已經移除，完整數據見 README §8。

留下這支腳本是因為**評估方法本身可重用**：任何「自動刪掉某類 finding」的想法，
都可以先用它在固定分母上量一次誤刪率，再決定要不要上線。

用法：
    DEEPSEEK_API_KEY=... python3 tools/eval/eval_filter.py \
        --filter-prompt path/to/your-filter.md [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))
import locate  # noqa: E402

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def chat(payload, api_key, timeout=300, retries=3):
    body = json.dumps(payload).encode("utf-8")
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            BASE_URL.rstrip("/") + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}",
                     "Accept": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            last = f"HTTP {e.code}: {detail}"
            if e.code not in (429, 500, 502, 503, 504):
                return None, last
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        if attempt < retries:
            time.sleep(min(2 ** attempt * 2, 30))
    return None, last


def extract_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e > s:
        return json.loads(text[s:e + 1])
    raise ValueError("回應裡找不到 JSON")


def run_one_pr(item, filter_prompt, api_key, model, thinking):
    """回傳 (被刪的 index 集合, usage, error)。"""
    cs = item["comments"]
    listing = []
    for i, c in enumerate(cs):
        # 欄位形狀要與正式流程一致。資料集沒有 existing_code（那是我們 rubric 才
        # 有的欄位），所以留空——這也是這次評估與線上行為的一個已知差異。
        listing.append(
            f"### finding {i}\n"
            f"- path: {c['path']}:{c['from_line']}\n"
            f"- severity: minor\n"
            f"- title: {c['note'][:120]}\n"
            f"- body: {c['note']}\n"
            f"- existing_code:\n```\n\n```"
        )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": filter_prompt},
            {"role": "user", "content":
                f"## Diff\n\n```diff\n{item['diff']}\n```\n\n"
                f"## Findings（共 {len(cs)} 筆）\n\n" + "\n\n".join(listing)},
        ],
        "temperature": 0.0,
        "max_tokens": 2048,
        "thinking": {"type": thinking},
    }
    resp, err = chat(payload, api_key)
    if err:
        return set(), {}, err
    try:
        verdict = extract_json(resp["choices"][0]["message"]["content"])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        return set(), resp.get("usage") or {}, f"解析失敗: {e}"

    norm_diff = locate.normalize_ws(item["diff"])
    removed = set()
    for it in verdict.get("remove") or []:
        if not isinstance(it, dict):
            continue
        try:
            idx = int(it.get("index"))
        except (TypeError, ValueError):
            continue
        line = str(it.get("contradicting_line") or "").strip()
        if not (0 <= idx < len(cs)) or not line:
            continue
        # 與正式流程同一條幻覺防線：模型宣稱的反證行必須真的在 diff 裡
        if locate.normalize_ws(line) not in norm_diff:
            continue
        removed.add(idx)
    return removed, resp.get("usage") or {}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", default=os.path.join(HERE, "eval_set.json"))
    ap.add_argument("--filter-prompt", required=True,
                    help="要評估的 filter prompt 檔案路徑（本 kit 不內建，需自備）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 個 PR")
    ap.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    ap.add_argument("--thinking", default="disabled", choices=["disabled", "low", "high", "max"])
    ap.add_argument("--out", default=os.path.join(HERE, "eval_result.json"))
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        log("[error] 缺少 DEEPSEEK_API_KEY")
        return 1

    with open(args.filter_prompt, encoding="utf-8") as fh:
        filter_prompt = fh.read()
    with open(args.eval_set, encoding="utf-8") as fh:
        items = json.load(fh)
    if args.limit:
        items = items[:args.limit]

    tp = fp = fn = tn = 0
    errors, killed_records = [], []
    tok_in = tok_out = 0

    for i, item in enumerate(items, 1):
        removed, usage, err = run_one_pr(item, filter_prompt, api_key, args.model, args.thinking)
        tok_in += usage.get("prompt_tokens", 0)
        tok_out += usage.get("completion_tokens", 0)
        if err:
            errors.append((item["url"], err))
        for j, c in enumerate(item["comments"]):
            killed = j in removed
            if killed and c["label"] == 0:
                tp += 1
            elif killed and c["label"] == 1:
                fp += 1
            elif not killed and c["label"] == 0:
                fn += 1
            else:
                tn += 1
            if killed:
                killed_records.append({
                    "url": item["url"], "path": c["path"], "label": c["label"],
                    "category": c["category"], "note": c["note"][:300],
                })
        log(f"[{i}/{len(items)}] {item['repo']}#{item['number']} "
            f"刪 {len(removed)}/{len(item['comments'])}" + (f"  ⚠️ {err}" if err else ""))

    total = tp + fp + fn + tn
    n_ok, n_bad = fp + tn, tp + fn
    base = n_ok / total if total else 0
    kept = total - tp - fp
    after = (n_ok - fp) / kept if kept else 0

    lines = [
        "## AACR-Bench 評估結果",
        "",
        f"- 評估集：**{len(items)} 個 PR、{total} 則 comment**（正確 {n_ok} / 錯誤 {n_bad}）",
        f"- 模型：`{args.model}`、thinking `{args.thinking}`",
        "",
        "| | label=0（錯誤） | label=1（正確） |",
        "|---|---|---|",
        f"| **被刪** | {tp}（刪對） | **{fp}（誤刪）** |",
        f"| **保留** | {fn}（漏抓） | {tn} |",
        "",
        f"- **誤刪率 {fp}/{n_ok} = {fp / n_ok * 100:.2f}%**　← 最貴的錯誤",
        f"- 抓錯率 {tp}/{n_bad} = {tp / n_bad * 100:.2f}%",
        f"- precision {base * 100:.2f}% → {after * 100:.2f}% "
        f"（{'+' if after >= base else ''}{(after - base) * 100:.2f} 個百分點）",
        "",
        f"- tokens：輸入 {tok_in:,}／輸出 {tok_out:,}"
        f"　估計 ${tok_in / 1e6 * 0.66 + tok_out / 1e6 * 1.98:.3f}",
    ]
    if errors:
        lines.append(f"- ⚠️ {len(errors)} 個 PR 呼叫失敗，那些 comment 一律計為「未刪」")
    if fp:
        lines += ["", "<details><summary>誤刪的那幾筆</summary>", ""]
        for r in [r for r in killed_records if r["label"] == 1][:20]:
            lines.append(f"- `{r['path']}` [{r['category']}] {r['note'][:150]}")
        lines += ["", "</details>"]

    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                   "model": args.model, "prs": len(items), "comments": total,
                   "tokens_in": tok_in, "tokens_out": tok_out,
                   "killed": killed_records, "errors": errors},
                  fh, ensure_ascii=False, indent=1)
    log(f"\n[info] 明細 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
