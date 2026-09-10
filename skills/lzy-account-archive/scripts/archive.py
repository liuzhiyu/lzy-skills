#!/usr/bin/env python3
"""lzy-account-archive 账号存量仓库管理器

数据仓库默认在 ~/WorkBuddy/lzy-data/accounts/<platform>/<account>/（可用 LZY_ARCHIVE_ROOT 覆盖）。
技能目录本身不放数据（技能会发布到 GitHub）。

用法：
  archive.py init   <platform> <account>                    创建仓库目录
  archive.py known  <platform> <account>                    输出已知 post_id（每行一个，供增量过滤）
  archive.py pending <platform> <account> <items.json>      从列表里过滤出还没归档的 id（stdout 每行一个）
  archive.py merge  <platform> <account> <items.json>       合并抓取结果（去重 / 跳过当天 / 记录指标历史）
  archive.py stats  <platform> <account>                    覆盖情况统计
  archive.py report <platform> <account>                    生成/刷新 STATUS.md 摘要

items.json 格式：数组，或 {"items": [...]}。字段宽容映射（抖音/小红书原始字段均可）：
  id(必填) url title content publish_date metrics{likes comments shares collects}
  兼容抖音: desc/create_time/statistics{digg_count,...}；兼容小红书: time/interactInfo{likedCount,...}
"""
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))  # 统一用北京时间
ROOT = os.environ.get("LZY_ARCHIVE_ROOT") or os.path.join(
    os.path.expanduser("~"), "WorkBuddy", "lzy-data", "accounts")

VALID_PLATFORMS = {"douyin", "xiaohongshu"}


def die(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def slugify(s):
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", s.strip()).strip("-")
    return s or "unknown"


def store_dir(platform, account):
    if platform not in VALID_PLATFORMS:
        die(f"platform 必须是 {sorted(VALID_PLATFORMS)} 之一，收到: {platform}")
    return os.path.join(ROOT, platform, slugify(account))


def posts_file(platform, account):
    return os.path.join(store_dir(platform, account), "posts.jsonl")


def today_cn():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        die(f"无法读取 JSON: {path} ({e})")
    if isinstance(data, dict) and "items" in data:
        data = data["items"]
    if not isinstance(data, list):
        die(f"items.json 应为数组: {path}")
    return data


def parse_publish_date(raw):
    """宽容解析发布日期 → YYYY-MM-DD 或 None"""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        if v > 1e12:  # 毫秒时间戳
            v /= 1000.0
        if v > 1e9:
            return datetime.fromtimestamp(v, TZ).strftime("%Y-%m-%d")
        return None
    s = str(raw).strip()
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def norm_metrics(raw):
    """宽容映射各类计数来源 → 标准五键"""
    m = {"likes": 0, "comments": 0, "shares": 0, "collects": 0}
    if not isinstance(raw, dict):
        return m
    alias = {
        "likes": ["likes", "digg_count", "likedCount", "liked", "digg"],
        "comments": ["comments", "comment_count", "commentCount", "comment"],
        "shares": ["shares", "share_count", "shareCount", "share"],
        "collects": ["collects", "collect_count", "collectedCount", "collect", "collectCount"],
    }
    def to_int(v):
        if v is None:
            return 0
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).replace(",", "").strip()
        mult = 1
        if s.endswith("万"):
            mult, s = 10000, s[:-1]
        elif s.endswith("w"):
            mult, s = 10000, s[:-1]
        try:
            return int(float(s) * mult)
        except ValueError:
            return 0
    for std, keys in alias.items():
        for k in keys:
            if k in raw and raw[k] not in (None, ""):
                m[std] = to_int(raw[k])
                break
    return m


def norm_item(raw, platform):
    """把一条原始抓取记录规范成标准 schema；返回 (item, problems[])"""
    problems = []
    if not isinstance(raw, dict):
        return None, ["不是对象"]
    pid = raw.get("id") or raw.get("note_id") or raw.get("video_id") or raw.get("aweme_id")
    if not pid:
        return None, ["缺 id"]
    pid = str(pid)

    title = (raw.get("title") or "").strip()
    content = (raw.get("content") or raw.get("desc") or raw.get("note") or "").strip()
    if not title and content:
        title = content.splitlines()[0][:60]
    if not content:
        problems.append("缺 content")

    pd = parse_publish_date(raw.get("publish_date") or raw.get("publish_time")
                            or raw.get("create_time") or raw.get("time") or raw.get("date"))
    if not pd:
        problems.append("缺 publish_date")

    metrics_raw = raw.get("metrics") or raw.get("statistics") or raw.get("stats") \
        or raw.get("interactInfo")
    flat_keys = ("likes", "comments", "shares", "collects", "digg_count",
                 "comment_count", "share_count", "collect_count",
                 "likedCount", "commentCount", "shareCount", "collectedCount")
    if not isinstance(metrics_raw, dict) or not metrics_raw:
        flat = {k: raw[k] for k in flat_keys if raw.get(k) not in (None, "")}
        metrics_raw = flat if flat else (metrics_raw if isinstance(metrics_raw, dict) else {})
    metrics = norm_metrics(metrics_raw)

    item = {
        "id": pid,
        "platform": platform,
        "url": raw.get("url") or "",
        "title": title,
        "content": content,
        "publish_date": pd,
        "metrics": metrics,
    }
    return item, problems


def load_posts(path):
    posts = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    p = json.loads(line)
                    posts[p["id"]] = p
                except Exception:
                    continue
    return posts


def save_posts_atomic(path, posts):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for p in sorted(posts.values(), key=lambda x: x.get("publish_date") or "0000"):
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def cmd_init(platform, account):
    d = store_dir(platform, account)
    os.makedirs(os.path.join(d, "raw"), exist_ok=True)
    if not os.path.exists(posts_file(platform, account)):
        save_posts_atomic(posts_file(platform, account), {})
    print(json.dumps({"ok": True, "store": d}, ensure_ascii=False))


def cmd_known(platform, account):
    for pid in load_posts(posts_file(platform, account)):
        print(pid)


def cmd_pending(platform, account, items_path):
    known = load_posts(posts_file(platform, account))
    items = load_json(items_path)
    pend = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or raw.get("note_id") or raw.get("video_id") or "")
        if pid and pid not in known:
            pend.append(pid)
    print(json.dumps({"pending": len(pend), "listed": len(items), "known": len(known)},
                     ensure_ascii=False), file=sys.stderr)
    for pid in pend:
        print(pid)


def cmd_merge(platform, account, items_path):
    path = posts_file(platform, account)
    posts = load_posts(path)
    items = load_json(items_path)
    today = today_cn()
    new_n = upd_n = skip_today = skip_nodate = 0
    problems_all = []
    for raw in items:
        item, problems = norm_item(raw, platform)
        if item is None:
            problems_all.append({"raw": raw, "problems": problems})
            continue
        if problems:
            problems_all.append({"id": item["id"], "problems": problems})
        old = posts.get(item["id"])
        # 缺发布日期：新条目宁缺毋滥不入库；已入库条目允许做指标/字段补全更新
        if not item["publish_date"]:
            if old is None:
                skip_nodate += 1
                continue
        # 用户规则：不需要当天的（数据未定型），跳过不入库
        elif item["publish_date"] == today or item["publish_date"] > today:
            skip_today += 1
            continue
        if old is None:
            item["first_seen"] = item["last_seen"] = today
            item["history"] = [{"date": today, "metrics": item["metrics"]}]
            posts[item["id"]] = item
            new_n += 1
        else:
            changed = False
            for f in ("title", "content", "url", "publish_date"):
                if not old.get(f) and item.get(f):
                    old[f] = item[f]
                    changed = True
            if old.get("metrics") != item["metrics"]:
                old["metrics"] = item["metrics"]
                changed = True
                hist = old.setdefault("history", [])
                if not hist or hist[-1].get("date") != today or hist[-1].get("metrics") != item["metrics"]:
                    if hist and hist[-1].get("date") == today:
                        hist[-1]["metrics"] = item["metrics"]
                    else:
                        hist.append({"date": today, "metrics": item["metrics"]})
            old["last_seen"] = today
            if changed:
                upd_n += 1
    save_posts_atomic(path, posts)
    print(json.dumps({
        "store": store_dir(platform, account),
        "total": len(posts),
        "new": new_n,
        "updated": upd_n,
        "skipped_today": skip_today,
        "skipped_nodate": skip_nodate,
        "problems": len(problems_all),
    }, ensure_ascii=False))
    if problems_all:
        pf = os.path.join(store_dir(platform, account), "raw",
                          f"merge_problems_{today}.json")
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(problems_all, f, ensure_ascii=False, indent=1)
        print(f"问题清单 → {pf}", file=sys.stderr)


def cmd_stats(platform, account):
    posts = load_posts(posts_file(platform, account))
    if not posts:
        print(json.dumps({"total": 0, "store": store_dir(platform, account)}, ensure_ascii=False))
        return
    dates = sorted(p["publish_date"] for p in posts.values() if p.get("publish_date"))
    missing_content = sum(1 for p in posts.values() if not p.get("content"))
    missing_metrics = sum(1 for p in posts.values()
                          if not any(p.get("metrics", {}).values()))
    print(json.dumps({
        "store": store_dir(platform, account),
        "total": len(posts),
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "missing_content": missing_content,
        "missing_metrics": missing_metrics,
    }, ensure_ascii=False))


def cmd_report(platform, account):
    path = posts_file(platform, account)
    posts = load_posts(path)
    d = store_dir(platform, account)
    lines = [f"# 账号归档：{account}（{platform}）", "",
             f"- 仓库：`{d}`",
             f"- 已归档：**{len(posts)} 条**（截至 {today_cn()}）"]
    if posts:
        dates = sorted(p["publish_date"] for p in posts.values() if p.get("publish_date"))
        if dates:
            lines.append(f"- 发布日期范围：{dates[0]} ~ {dates[-1]}")
        top = sorted(posts.values(),
                     key=lambda p: p.get("metrics", {}).get("likes", 0), reverse=True)[:5]
        lines += ["", "## 点赞 Top 5", "",
                  "| 日期 | 标题 | 赞 | 评 | 转 | 藏 |", "|---|---|---|---|---|---|"]
        for p in top:
            m = p.get("metrics", {})
            t = (p.get("title") or "（无标题）").replace("|", "/")[:40]
            lines.append(f"| {p.get('publish_date') or '?'} | {t} "
                         f"| {m.get('likes',0)} | {m.get('comments',0)} "
                         f"| {m.get('shares',0)} | {m.get('collects',0)} |")
        miss = [p for p in posts.values() if not p.get("content")]
        if miss:
            lines += ["", f"⚠️ 有 {len(miss)} 条缺正文全文，可跑增量抓取补齐。"]
    else:
        lines.append("- 仓库还是空的，先抓一次存量。")
    lines.append("")
    out = os.path.join(d, "STATUS.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"STATUS → {out}")


def main():
    args = sys.argv[1:]
    if not args:
        die(__doc__)
    cmd = args[0]
    try:
        if cmd == "init" and len(args) == 3:
            cmd_init(args[1], args[2])
        elif cmd == "known" and len(args) == 3:
            cmd_known(args[1], args[2])
        elif cmd == "pending" and len(args) == 4:
            cmd_pending(args[1], args[2], args[3])
        elif cmd == "merge" and len(args) == 4:
            cmd_merge(args[1], args[2], args[3])
        elif cmd == "stats" and len(args) == 3:
            cmd_stats(args[1], args[2])
        elif cmd == "report" and len(args) == 3:
            cmd_report(args[1], args[2])
        else:
            die(f"参数不对。命令与参数见 --help（直接运行不带参数看文档）")
    except SystemExit:
        raise
    except Exception as e:
        die(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
