#!/usr/bin/env python3
"""
选样：从 all_videos.json 按点赞排序，选出爆款组 N 条 + 非爆款(对照组) N 条
=================================================
用法：
  python3 select_samples.py all_videos.json --viral 10 --control 10 [--out 选样.txt]
  python3 select_samples.py all_videos.json --viral 10 --control 10 --min-control 50 --max-control 2000

选样策略：
  - 爆款组：点赞 Top N
  - 对照组：点赞末 N（可加 min/max 区间约束，避开 0 赞或异常值）
"""
import argparse
import json
import sys


def parse_n(n):
    if not n or n == "?":
        return 0
    n = str(n).strip()
    if "万" in n:
        return float(n.replace("万", "")) * 10000
    try:
        return float(n)
    except Exception:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json", help="all_videos.json 路径")
    ap.add_argument("--viral", type=int, default=10, help="爆款组取几条")
    ap.add_argument("--control", type=int, default=10, help="对照组取几条")
    ap.add_argument("--min-control", type=float, default=0, help="对照组最低赞（避开0赞）")
    ap.add_argument("--max-control", type=float, default=10 ** 9, help="对照组最高赞（避开异常值）")
    ap.add_argument("--out", default=None, help="选样清单输出路径")
    args = ap.parse_args()

    with open(args.json) as f:
        data = json.loads(f.read().strip())

    # 去重（同一 id 只留一次）
    seen = {}
    for d in data:
        i = d.get("id", "?")
        if i not in seen:
            seen[i] = d
    data = list(seen.values())

    for d in data:
        d["_n"] = parse_n(d.get("n"))

    data.sort(key=lambda x: -x["_n"])

    viral = [d for d in data if d["_n"] > 0][: args.viral]
    control_pool = [
        d for d in data
        if args.min_control <= d["_n"] <= args.max_control and d["_n"] > 0
    ]
    control = control_pool[-args.control:] if control_pool else []

    print("=" * 60)
    print(f"总作品 {len(data)} 条，选出爆款 {len(viral)} 条 + 对照 {len(control)} 条")
    print("=" * 60)
    print("\n【爆款组】")
    for d in viral:
        print(f"  {d['_n']:>9.0f}  {d['id']}  {d.get('alt','')[:24]}")
    print("\n【对照组】")
    for d in control:
        print(f"  {d['_n']:>9.0f}  {d['id']}  {d.get('alt','')[:24]}")

    viral_ids = [d["id"] for d in viral]
    control_ids = [d["id"] for d in control]

    out = args.out or "选样.txt"
    with open(out, "w") as f:
        f.write(f"# 爆款组 {len(viral_ids)} 条\n")
        f.write(" ".join(viral_ids) + "\n")
        f.write(f"# 对照组 {len(control_ids)} 条\n")
        f.write(" ".join(control_ids) + "\n")
    print(f"\n选样清单已写 → {out}")


if __name__ == "__main__":
    main()
