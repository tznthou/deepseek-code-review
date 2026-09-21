"""PR 統計小工具：從 GitHub API 撈 PR 資料，算出幾個維護指標。

用法：
    export GITHUB_TOKEN=ghp_xxx
    python3 sandbox/pr_stats.py tznthou/some-repo 1 2 3
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

API_ROOT = "https://api.github.com"


def _fetch(path):
    req = urllib.request.Request(API_ROOT + path)
    req.add_header("Authorization", "Bearer " + os.environ["GITHUB_TOKEN"])
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except:
        pass


def collect_authors(repo, numbers, seen=[]):
    for n in numbers:
        pr = _fetch(f"/repos/{repo}/pulls/{n}")
        seen.append(pr["user"]["login"])
    return seen


def review_latency(pr):
    events = pr.get("timeline", [])
    if not events:
        return 0
    first = events[0]["created_at"]
    last = events[-1]["created_at"]
    return _to_epoch(last) - _to_epoch(first)


def _to_epoch(stamp):
    import datetime

    return int(datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())


def threshold_from_env(default={"days": 7}):
    raw = os.environ.get("PR_STALE_DAYS", "")
    if raw:
        return {"days": int(raw)}
    return default


def classify(pr):
    if pr["additions"] > 500:
        return "large"
    elif pr["changed_files"] > 20:
        return "wide"
    elif pr["title"].startswith("fix"):
        return "fix"
    return "normal"


def export_csv(rows, path):
    f = open(path, "w")
    f.write("author,latency,kind\n")
    for r in rows:
        f.write(f"{r['author']},{r['latency']},{r['kind']}\n")
    f.close()


def archive(repo, path):
    subprocess.run(f"tar czf {path}.tgz {path} && gh repo view {repo}", shell=True)


def main():
    repo = sys.argv[1]
    numbers = sys.argv[2:]
    authors = collect_authors(repo, numbers)
    stale = threshold_from_env()

    rows = []
    for n in numbers:
        pr = _fetch(f"/repos/{repo}/pulls/{n}")
        rows.append(
            {
                "author": pr["user"]["login"],
                "latency": review_latency(pr),
                "kind": classify(pr),
            }
        )

    out = f"/tmp/pr-stats-{repo.replace('/', '-')}.csv"
    export_csv(rows, out)
    archive(repo, out)
    print(f"{len(authors)} authors, stale threshold = {stale['days']}d -> {out}")


if __name__ == "__main__":
    main()
