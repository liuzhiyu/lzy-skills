# -*- coding: utf-8 -*-
"""抖音搜索 Top N 评论区线索分析（配置驱动引擎）
用法: python3 analyze.py <config_module> <workdir> <关键词> [topN=100]
  config_module: scripts/ 下的 config_xxx.py（如 config_qiaoben / config_base）
输入: <workdir>/list.json（搜索结果列表）
      <workdir>/comments/<videoId>.json（逐条视频评论区）
输出: <workdir>/leads.csv            视频 × 咨询分类统计
      <workdir>/comments_all.csv     全部评论原文 + 分类标签
      <workdir>/report_data.md       数据底稿（结论需人工撰写）
      <workdir>/comments_stats.json  结构化统计（供 report_comments.py 渲染 HTML）
"""
import json, re, os, sys, glob, csv, collections, statistics, importlib

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)
from parse_comments import parse_comment, classify, detect_hook, load_dir, configure

CLS = ["A1", "A2", "A3", "A4", "B", "C", "None"]
NAME = {"A1": "A1 强意向（问价/要联系方式/求服务）", "A2": "A2 求方法求资料", "A3": "A3 钩子留资",
        "A4": "A4 @AI 代写", "B": "B 同行共鸣/求带", "C": "C 泛互动", "None": "无关/无法归类"}


def run_analysis(WORK, KW, TOPN, cfg):
    items = json.load(open(os.path.join(WORK, "list.json"), encoding="utf-8"))[:TOPN]
    com = load_dir(os.path.join(WORK, "comments"))

    rows = []
    for x in items:
        v = com.get(x["id"])
        rec = dict(x)
        rec["cs"] = []
        rec["c_total"] = 0
        rec["hook"] = None
        for k in CLS:
            rec["n" + k] = 0
        rec["tags_hit"] = collections.Counter()
        if v and v.get("ok"):
            cs = [c for c in (parse_comment(l) for l in v.get("comments", [])) if c]
            hook = detect_hook(cs)
            if hook and hook[1] < 3:
                hook = None
            rec["hook"] = hook
            hw = hook[0] if hook else None
            for c in cs:
                cl, tag = classify(c["content"], hw)
                c["cls"], c["tag"] = cl, tag
                rec["n" + (cl if cl else "None")] += 1
                if cl:
                    rec["tags_hit"].update(tag)
            rec["cs"] = cs
            rec["c_total"] = len(cs)
        rows.append(rec)

    done = [r for r in rows if r["c_total"] > 0]
    TOT_C = sum(r["c_total"] for r in rows)
    cnt = {k: sum(r["n" + k] for r in rows) for k in CLS}

    def lead(r):
        return r["nA1"] + r["nA2"] + r["nA3"]

    def rl(rs):
        c = sum(r["c_total"] for r in rs)
        return (sum(lead(r) for r in rs) / c * 100) if c else 0.0

    def rk(rs, k):
        c = sum(r["c_total"] for r in rs)
        return (sum(r["n" + k] for r in rs) / c * 100) if c else 0.0

    def cross(name, pred, note=""):
        g1 = [r for r in done if pred(r)]
        ids = {r["id"] for r in g1}
        g2 = [r for r in done if r["id"] not in ids]
        if not g1 or not g2:
            return None
        return dict(name=name, note=note, n1=len(g1), c1=sum(r["c_total"] for r in g1),
                    n2=len(g2), c2=sum(r["c_total"] for r in g2),
                    ld1=rl(g1), ld2=rl(g2), a11=rk(g1, "A1"), a12=rk(g2, "A1"),
                    a41=rk(g1, "A4"), a42=rk(g2, "A4"), b1=rk(g1, "B"), b2=rk(g2, "B"))

    is_org = getattr(cfg, "is_org", lambda r: False)
    CROSSES_RAW = getattr(cfg, "CROSSES", [])
    CROSSES = []
    for item in CROSSES_RAW:
        name, pred = item[0], item[1]
        note = item[2] if len(item) > 2 else ""
        c = cross(name, pred, note)
        if c:
            CROSSES.append(c)
    quad_bucket = getattr(cfg, "quad_bucket", lambda r: "都没有")
    QUAD_ORDER = getattr(cfg, "QUAD_ORDER", ["都没"])
    quad = {k: [] for k in QUAD_ORDER}
    for r in done:
        quad[quad_bucket(r)].append(r)

    sub = collections.Counter()
    for r in rows:
        for c in r["cs"]:
            if c["cls"] in ("A1", "A2"):
                sub.update(c["tag"])

    hooks = sorted([r for r in rows if r["hook"]], key=lambda r: -r["hook"][1])
    tagc = collections.Counter()
    for x in items:
        tagc.update(x.get("tags", []))

    # ---------- 结构化统计（供报告引擎） ----------
    S = {
        "kw": KW, "n_videos": len(items), "n_done": len(done), "tot_c": TOT_C,
        "cls": cnt, "comp_pct": {k: round(cnt[k] / max(1, TOT_C) * 100, 1) for k in CLS},
        "n_hook_videos": len(hooks),
        "crosses": [{"name": c["name"], "n1": c["n1"], "c1": c["c1"], "ld1": round(c["ld1"], 1),
                     "n2": c["n2"], "c2": c["c2"], "ld2": round(c["ld2"], 1),
                     "mult": round(c["ld1"] / c["ld2"], 2) if c["ld2"] else 0,
                     "a41": round(c["a41"], 1), "a42": round(c["a42"], 1),
                     "a11": round(c["a11"], 1), "a12": round(c["a12"], 1)} for c in CROSSES],
        "quad": [{"key": k, "n": len(quad[k]), "c": sum(x["c_total"] for x in quad[k]),
                  "ld": round(rl(quad[k]), 1), "a1": round(rk(quad[k], "A1"), 1),
                  "a4": round(rk(quad[k], "A4"), 1), "b": round(rk(quad[k], "B"), 1)}
                 for k in QUAD_ORDER if quad[k]],
        "hooks": [{"word": r["hook"][0], "count": r["hook"][1], "c_total": r["c_total"],
                   "likes": r["likes"], "author": r["author"]} for r in hooks],
        "top_tags": [[t, c] for t, c in tagc.most_common(30)],
        "sub_top": [[t, c] for t, c in sub.most_common(10)],
        "leads_top": [{"rank": i, "title": r["title"], "author": r["author"], "likes": r["likes"],
                      "A1": r["nA1"], "A2": r["nA2"], "A3": r["nA3"], "A4": r["nA4"],
                      "B": r["nB"], "C": r["nC"], "lr": round(lead(r) / r["c_total"] * 100, 1) if r["c_total"] else "",
                      "hook": (r["hook"][0] if r["hook"] else ""),
                      "url": "https://www.douyin.com/video/" + r["id"]}
                     for i, r in enumerate(sorted(rows, key=lambda r: (-lead(r), -r["c_total"])), 1)],
        "a1_samples": [{"tag": ",".join(c["tag"]), "likes": c["likes"], "content": c["content"][:120],
                        "author": r["author"]}
                       for r, c in sorted([(r, c) for r in rows for c in r["cs"] if c["cls"] == "A1"],
                                          key=lambda z: -z[1]["likes"])[:40]],
        "a4_samples": [{"likes": c["likes"], "content": c["content"][:120], "author": r["author"]}
                       for r, c in sorted([(r, c) for r in rows for c in r["cs"] if c["cls"] == "A4"],
                                          key=lambda z: -z[1]["likes"])[:20]],
        "is_org_fn": None,
    }
    S["n_org"] = sum(1 for r in done if is_org(r))
    return rows, S


def main():
    CONFIG = sys.argv[1] if len(sys.argv) > 1 else "config_base"
    cfg = importlib.import_module(CONFIG)
    configure(cfg)
    WORK = sys.argv[2]
    KW = sys.argv[3] if len(sys.argv) > 3 else ""
    TOPN = int(sys.argv[4]) if len(sys.argv) > 4 else 100

    rows, S = run_analysis(WORK, KW, TOPN, cfg)
    done = [r for r in rows if r["c_total"] > 0]
    CLS_local = CLS

    def lead(r):
        return r["nA1"] + r["nA2"] + r["nA3"]

    # 打印摘要
    P = print
    P(f"关键词「{KW}」| 视频 {S['n_videos']} 条 | 拿到评论 {S['n_done']} 条 | 评论总数 {S['tot_c']}")
    P("评论构成: " + "  ".join(f"{k}={S['cls'][k]}({S['comp_pct'][k]}%)" for k in CLS_local))
    P(f"设钩子的视频: {S['n_hook_videos']}/{S['n_done']}")
    P("")
    P("交叉分析:")
    for c in S["crosses"]:
        P(f"  {c['name'][:20]:<22} {c['n1']:>3}条 {c['ld1']:>5.1f}%  vs {c['n2']:>3}条 {c['ld2']:>5.1f}%   {c['mult']:>5.2f}x   A4 {c['a41']:.1f}%/{c['a42']:.1f}%")
    P("")
    P("四象限（" + "/".join([q["key"] for q in S["quad"]]) + "）:")
    for q in S["quad"]:
        P(f"  {q['key']:<8} {q['n']:>3}条 线索率{q['ld']:>5.1f}%  A1 {q['a1']:>4.1f}%  A4 {q['a4']:>5.1f}%  同行 {q['b']:>4.1f}%")
    P("")
    P("线索类型 TOP10: " + ", ".join(f"{t}({c})" for t, c in S["sub_top"]))
    P("高频标签 TOP15: " + ", ".join(f"#{t}({c})" for t, c in S["top_tags"][:15]))

    # CSV
    with open(os.path.join(WORK, "leads.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["线索排序", "原排名", "标题", "标签", "点赞", "时长", "作者", "评论总数",
                    "A1强意向", "A2求方法", "A3钩子留资", "A4@AI代写", "B同行共鸣", "C泛互动", "线索率%", "留资暗号", "链接"])
        for r in sorted(rows, key=lambda r: (-lead(r), -r["c_total"])):
            lr = round(lead(r) / r["c_total"] * 100, 1) if r["c_total"] else ""
            w.writerow([0, r["rank"], r["title"], "|".join(r.get("tags", [])), r["likes"], r["dur"], r["author"],
                        r["c_total"] or "", r["nA1"], r["nA2"], r["nA3"], r["nA4"], r["nB"], r["nC"], lr,
                        (r["hook"][0] if r["hook"] else ""), "https://www.douyin.com/video/" + r["id"]])
    # 修正排序号
    with open(os.path.join(WORK, "leads.csv"), "r", encoding="utf-8-sig") as f:
        lines = f.readlines()
    with open(os.path.join(WORK, "leads.csv"), "w", newline="", encoding="utf-8-sig") as f:
        for i, line in enumerate(lines):
            if i == 0:
                f.write(line)
            else:
                f.write(line[:line.find(",") + 1] + str(i) + line[line.find(",") + 1:])

    with open(os.path.join(WORK, "comments_all.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["视频ID", "视频标题", "作者", "评论人", "评论内容", "分类", "标签", "点赞", "回复数", "时间"])
        for r in rows:
            for c in r["cs"]:
                w.writerow([r["id"], r["title"] or "|".join(r.get("tags", [])), r["author"], c["author"],
                            c["content"], c.get("cls", ""), ",".join(c.get("tag", [])), c["likes"], c["replies"], c["time"]])

    # Markdown 数据底稿
    L = []
    A = L.append
    A(f"# 抖音「{KW}」搜索 Top{S['n_videos']} 评论区线索分析（数据底稿）\n")
    A(f"> 视频 {S['n_videos']} 条，拿到评论 {S['n_done']} 条，评论总数 {S['tot_c']}\n")
    A("## 评论构成\n")
    A("| 分类 | 条数 | 占比 |")
    A("|---|---|---|")
    for k in CLS_local:
        A(f"| {NAME[k]} | {S['cls'][k]} | {S['comp_pct'][k]}% |")
    A("\n## 交叉分析\n")
    A("| 内容特征 | 该组 | 线索率 | 对比组 | 线索率 | 倍数 | @AI占比(该组/对比) |")
    A("|---|---|---|---|---|---|---|")
    for c in S["crosses"]:
        A(f"| {c['name']} | {c['n1']}条 | {c['ld1']}% | {c['n2']}条 | {c['ld2']}% | {c['mult']}× | {c['a41']}% / {c['a42']}% |")
    A("\n## 四象限\n")
    A("| 象限 | 视频 | 评论 | 线索率 | A1 | @AI | 同行共鸣 |")
    A("|---|---|---|---|---|---|---|")
    for q in S["quad"]:
        A(f"| {q['key']} | {q['n']} | {q['c']} | {q['ld']}% | {q['a1']}% | {q['a4']}% | {q['b']}% |")
    A("\n## 留资钩子盘点\n")
    A("| 暗号 | 条数 | 该视频评论数 | 占比 | 点赞 | 作者 |")
    A("|---|---|---|---|---|---|")
    for h in S["hooks"]:
        A(f"| {h['word']} | {h['count']} | {h['c_total']} | {h['count']/max(1,h['c_total'])*100:.0f}% | {h['likes']} | @{h['author']} |")
    A("\n## 客户咨询原话（A1）\n")
    for s in S["a1_samples"][:40]:
        A(f"- [{s['tag']}] 赞{s['likes']} · {s['content']} — 视频 @{s['author']}")
    A("\n## @AI 原话（A4）\n")
    for s in S["a4_samples"][:20]:
        A(f"- 赞{s['likes']} · {s['content']} — 视频 @{s['author']}")
    A("\n## 高频标签 TOP30\n")
    A(" ".join(f"#{t}({c})" for t, c in S["top_tags"]))
    A("\n")
    open(os.path.join(WORK, "report_data.md"), "w", encoding="utf-8").write("\n".join(L))

    json.dump(S, open(os.path.join(WORK, "comments_stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    P("")
    P(f"输出: {WORK}/leads.csv, {WORK}/comments_all.csv, {WORK}/report_data.md, {WORK}/comments_stats.json")


if __name__ == "__main__":
    main()
