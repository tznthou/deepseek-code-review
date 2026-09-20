#!/usr/bin/env python3
"""檢查 DSH 版本：Cherry Studio 內建的 runtime 版本 vs npm 上的最新版。

用途：回答「我現在用的 DSH 是最新版嗎？」
分三層看 —— app 本體、app 內建的 DSH 元件、你要在 CI 用的 CLI。

用法：
    python3 tools/check-dsh-version.py
    python3 tools/check-dsh-version.py --app "/Applications/Cherry Studio.app"

只用 Python 標準函式庫。沒有網路時仍會印出本機版本，只是跳過 npm 比較。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import plistlib
import struct
import sys
import urllib.error
import urllib.request

DEFAULT_APP = "/Applications/Cherry Studio.app"
REGISTRY = "https://registry.npmjs.org"
PACKAGES = ["@deepseek-ai/dsh", "@deepseek-ai/dsh-agent"]
# npm 的「精簡版」文件，比完整文件小很多，且含 dist-tags
ABBREVIATED = "application/vnd.npm.install-v1+json"


def read_app_version(app: str) -> str:
    plist = os.path.join(app, "Contents", "Info.plist")
    try:
        with open(plist, "rb") as fh:
            return plistlib.load(fh).get("CFBundleShortVersionString", "?")
    except Exception:
        return "?"


def read_asar_versions(app: str) -> dict[str, str]:
    """從 app.asar 取出所有 @deepseek-ai/dsh* 套件的版本。"""
    asar = os.path.join(app, "Contents", "Resources", "app.asar")
    unpacked = os.path.join(app, "Contents", "Resources", "app.asar.unpacked")

    with open(asar, "rb") as fh:
        struct.unpack("<I", fh.read(4))  # pickle payload size (=4)
        header_size = struct.unpack("<I", fh.read(4))[0]
        header = fh.read(header_size)

    # asar header = Pickle[ payloadSize ][ stringLen ][ json ][ padding ]
    string_len = struct.unpack("<I", header[4:8])[0]
    tree = json.loads(header[8 : 8 + string_len].decode("utf-8"))
    base = 8 + header_size

    targets: dict[str, dict] = {}

    def walk(node: dict, prefix: str = "") -> None:
        for name, entry in (node.get("files") or {}).items():
            path = f"{prefix}/{name}" if prefix else name
            if entry.get("files") is not None:
                walk(entry, path)
            elif name == "package.json" and "node_modules/@deepseek-ai/dsh" in path:
                targets[path] = entry

    walk(tree)

    versions: dict[str, str] = {}
    for path, entry in targets.items():
        try:
            if entry.get("unpacked"):
                with open(os.path.join(unpacked, path), "rb") as fh:
                    data = fh.read(entry["size"])
            else:
                with open(asar, "rb") as fh:
                    fh.seek(base + int(entry["offset"]))
                    data = fh.read(entry["size"])
            meta = json.loads(data.decode("utf-8"))
            name = path.split("node_modules/")[-1].rsplit("/package.json", 1)[0]
            versions[name] = meta.get("version", "?")
        except Exception:
            continue
    return versions


def npm_dist_tags(package: str, timeout: int = 15) -> dict[str, str]:
    req = urllib.request.Request(
        f"{REGISTRY}/{package.replace('/', '%2f')}",
        headers={"Accept": ABBREVIATED, "User-Agent": "check-dsh-version"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return (json.loads(resp.read().decode("utf-8")) or {}).get("dist-tags", {})


def main() -> int:
    parser = argparse.ArgumentParser(description="檢查 DSH 版本")
    parser.add_argument("--app", default=DEFAULT_APP, help=f"Cherry Studio.app 路徑（預設 {DEFAULT_APP}）")
    parser.add_argument("--no-network", action="store_true", help="跳過 npm 查詢")
    args = parser.parse_args()

    if not os.path.exists(args.app):
        print(f"[error] 找不到 app：{args.app}", file=sys.stderr)
        return 1

    app_version = read_app_version(args.app)
    try:
        versions = read_asar_versions(args.app)
    except Exception as err:
        print(f"[error] 無法解析 app.asar：{err}", file=sys.stderr)
        return 1

    grouped = collections.Counter(versions.values())

    print(f"== 第 1 層：Cherry Studio app 本體 ==\n  {app_version}\n")
    print(f"== 第 2 層：app 內建的 DSH 元件（共 {len(versions)} 個套件）==")
    for ver, count in grouped.most_common():
        print(f"  {ver:16s} ← {count} 個套件")
    mismatched = [n for n, v in versions.items() if v != grouped.most_common(1)[0][0]]
    if mismatched:
        print(f"  ⚠️ 版本不一致的套件：{mismatched[:5]}")

    if args.no_network:
        print("\n（已跳過 npm 查詢）")
        return 0

    print("\n== 第 3 層：npm 上的 dist-tags ==")
    tags_by_pkg: dict[str, dict[str, str]] = {}
    for pkg in PACKAGES:
        try:
            tags = npm_dist_tags(pkg)
            tags_by_pkg[pkg] = tags
            print(f"  {pkg}")
            for tag in ("latest", "next", "alpha"):
                if tag in tags:
                    print(f"    {tag:6s} {tags[tag]}")
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            print(f"  {pkg}: 查詢失敗（{type(err).__name__}）")

    # 判斷：內建版本是否等於任何一個 dist-tag？
    if tags_by_pkg:
        print("\n== 結論 ==")
        newest = sorted(
            {v for tags in tags_by_pkg.values() for v in tags.values()},
            reverse=True,
        )
        local = grouped.most_common(1)[0][0]
        hit = [f"{pkg.split('/')[-1]}:{tag}" for pkg, tags in tags_by_pkg.items() for tag, v in tags.items() if v == local]
        if hit:
            print(f"  內建 {local} 對應到 npm 標籤 {', '.join(hit)}")
        else:
            print(f"  內建 {local} 不等於任何 dist-tag → 不是最新版")
        print(f"  npm 上最新的標籤版本：{', '.join(newest[:4])}")
        print("  提醒：monorepo 各套件的 latest 標籤可能不一致，")
        print("        只看一個數字會誤判；請以你實際要 pin 的 CLI 套件為準。")
        print("  CI 要 pin 的是第 3 層的 CLI 版本，與本機 runtime（第 2 層）無關。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
