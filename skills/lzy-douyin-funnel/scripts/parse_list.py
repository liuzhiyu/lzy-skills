# -*- coding: utf-8 -*-
"""稳健解析抖音搜索结果卡片 -> 结构化 JSON
用法: python3 parse_list.py raw.json list.json
注意：卡片 innerText 行数不固定（带「合集」角标的是 6 行），必须按规则解析，不能用固定下标。
"""
import json, re, sys

DUR = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
NUM = re.compile(r"^[\d.]+\s*[万wW]?$")
TIME = re.compile(r"(刚刚|分钟前|小时前|天前|昨天|前天|\d+\s*(秒|分钟|小时|天|周|个月|月|年)前|^\d+-\d+$|^\d+/\d+$)")


def to_int(s):
    s = (s or "").strip()
    m = re.match(r"^([\d.]+)\s*(万|w|W)?$", s)
    if not m:
        return 0
    v = float(m.group(1))
    if m.group(2):
        v *= 10000
    return int(v)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rows = json.load(open(src, encoding="utf-8"))
    items = []
    for i, r in enumerate(rows, 1):
        lines = r["lines"]
        dur = likes = author = pub = badge = ""
        desc_parts = []
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if not dur and DUR.match(s):
                dur = s
                continue
            if not likes and NUM.match(s) and not DUR.match(s):
                likes = s
                continue
            if not author and s.startswith("@"):
                author = s[1:].strip()
                continue
            if not pub and TIME.search(s) and not s.startswith("@"):
                pub = s
                continue
            desc_parts.append(s)
        if not dur and not likes:
            desc_parts = lines
        rest = []
        for p in desc_parts:
            if len(p) <= 4 and not re.search(r"[\u4e00-\u9fa5]{3,}", p):
                badge = p
            else:
                rest.append(p)
        desc = " ".join(rest).strip()
        tags = [t.strip() for t in re.findall(r"#([^#\s]+)", desc) if t.strip()]
        clean = re.sub(r"#[^#\s]+", "", desc)
        clean = re.sub(r"\s+", " ", clean).strip(" ，,。!！?？:：、")
        items.append(dict(rank=i, id=r["id"], dur=dur, likes=likes, likes_n=to_int(likes),
                          badge=badge, title=clean, tags=tags, author=author, pub=pub, raw=desc))
    bad = [x for x in items if not x["title"] or not x["author"] or not x["likes"]]
    print(f"总条数 {len(items)}  解析缺字段 {len(bad)}（多为纯标签无标题卡片）")
    json.dump(items, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"saved -> {dst}")


if __name__ == "__main__":
    main()
