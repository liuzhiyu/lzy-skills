#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data.json + text_metrics.json + 转写稿 拼成单条视频拆解报告骨架（Markdown）。

用法:
  python3 build_report.py --workdir <工作目录> [--transcript script.txt] [--out 报告.md]

产物：报告 md，含「已测数据」全部自动填充，「归因判断」留占位由主 Agent 逐帧+读稿后填写。
理由：数据和计数可以程序化，归因是判断——判断不外包（lzy 工具箱设计原则）。
"""
import argparse
import json
import os
import sys

DIMENSIONS = [
    ("选题与人群", "这条在替谁说话？痛点强度够不够？是大众母题还是窄众黑话？", "🟡"),
    ("钩子（前 3 秒）", "开场塞了几个信号？是反常识、身份点名、还是结果承诺？为什么能拦住人？", "🔴"),
    ("结构节奏", "四段字数分布说明了什么？信息密度压在哪一段？有没有废段？", "🔴"),
    ("表达与语感", "口语还是书面？短句比例、语速、有没有口语连接词撑住「人味」？", "🔴"),
    ("信任与身份", "凭什么信他？身份标签、案例、信任反转、免责话术怎么配比？", "🟡"),
    ("互动设计", "评论区是怎么被设计出来的？预判滑走、提问、三连击？", "🟡"),
    ("CTA / 留资", "有没有钩子把人带走？带走的路径是几步？", "🔴"),
    ("制作层", "场景 / POV / 字幕 / BGM / 剪辑节奏（逐帧目视后填）", "🟡"),
]


def fmt(n):
    return "—" if n is None else f"{n:,}"


def ratio_line(der, mt):
    rows = []
    mapping = [("评赞比", "comment_per_like", 0.08, "高评=争议型/提问型，评论本身是内容"),
               ("藏赞比", "collect_per_like", 0.15, "高藏=工具型，观众觉得「以后用得上」"),
               ("转赞比", "share_per_like", 0.05, "高转=社交货币型，观众愿意替你背书")]
    for label, key, thr, mean in mapping:
        v = der.get(key)
        if v is None:
            rows.append(f"| {label} | — | — |")
        else:
            flag = "偏高" if v >= thr else "偏低"
            rows.append(f"| {label} | {v} | {flag}（阈值 {thr}）→ {mean} |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--transcript", help="转写 txt 路径，默认工作目录下 script_*.txt")
    ap.add_argument("--out", help="输出 md 路径")
    args = ap.parse_args()

    wd = os.path.abspath(args.workdir)
    data = {}
    dp = os.path.join(wd, "data.json")
    if os.path.exists(dp):
        data = json.load(open(dp, encoding="utf-8"))
    tm = {}
    tp = os.path.join(wd, "text_metrics.json")
    if os.path.exists(tp):
        tm = json.load(open(tp, encoding="utf-8"))

    transcript = args.transcript
    if not transcript:
        cands = [f for f in os.listdir(wd) if f.startswith("script_") and f.endswith(".txt")]
        transcript = os.path.join(wd, sorted(cands)[-1]) if cands else None
    if transcript and os.path.exists(transcript):
        # 去掉转写稿的元信息注释行（lzy-video-to-text 带 # 头），否则进 md 会变成一级标题
        tbody = "\n".join(l for l in open(transcript, encoding="utf-8").read().splitlines()
                          if not l.strip().startswith("#")).strip()

    mt = data.get("metrics", {}) or {}
    der = data.get("derived", {}) or {}
    vid = data.get("video_id", "unknown")
    out = args.out or os.path.join(wd, f"单条拆解_{vid}.md")

    L = []
    L.append(f"# 单条拆解 · {data.get('author', {}).get('nickname') or '未知作者'} · {vid}")
    L.append("")
    L.append(f"> 来源：{data.get('url')}  ")
    L.append(f"> **数据抓取时刻：{data.get('captured_at_human', '—')}**（抖音指标是活的，脱离抓取时间的数字无意义）  ")
    L.append(f"> 发布：{data.get('publish_time') or '—'}　存续 {data.get('age_days', '—')} 天　"
             f"时长 {(data.get('duration_ms') or 0) / 1000:.1f}s  ")
    L.append("> 口径：**单条拆解，无对照组**——所有归因是相关性判断，不是因果证明。")
    L.append("")

    L.append("## 一、数据快照")
    L.append("")
    L.append("| 指标 | 数值 | 原始显示 |")
    L.append("|---|---|---|")
    raw = data.get("metrics_raw", {}) or {}
    for zh, k in [("点赞", "likes"), ("评论", "comments"), ("收藏", "collects"), ("转发", "shares")]:
        L.append(f"| {zh} | {fmt(mt.get(k))} | {raw.get(k) or '—'} |")
    if der.get("engagement_total") is not None:
        L.append(f"| 互动总量 | {fmt(der.get('engagement_total'))} | — |")
    if der.get("likes_per_day") is not None:
        L.append(f"| 日均赞 | {fmt(der.get('likes_per_day'))} | 赞 ÷ 存续天数 |")
    L.append("")
    L.append("**互动结构（经验阈值，⚠️ 非验证结论，只作线索）**")
    L.append("")
    L.append("| 比率 | 值 | 提示 |")
    L.append("|---|---|---|")
    L.append(ratio_line(der, mt))
    L.append("")

    L.append("## 二、视频自带文案（标题 + 正文 + 话题）")
    L.append("")
    L.append("```")
    L.append(data.get("content") or "（未抓到，可能登录态失效）")
    L.append("```")
    L.append("")

    if tbody:
        L.append("## 三、口播转写全文")
        L.append("")
        L.append(tbody)
        L.append("")

    if tm:
        f = tm.get("full_text", {})
        hk = tm.get("hook_window", {})
        L.append("## 四、文本层指标（程序化提取）")
        L.append("")
        L.append(f"- 字数 {f.get('字数')} / 句数 {f.get('句数')} / 平均句长 {f.get('平均句长')} 字")
        L.append(f"- 时长 {f.get('时长秒')}s / 语速 {f.get('语速_字每秒')} 字每秒 / 短句(≤12字)占比 {f.get('短句占比')}")
        L.append(f"- 口语连接词 {f.get('口语连接词次数')} 次")
        L.append("")
        L.append(f"**钩子窗口**（{hk.get('口径')}）：{hk.get('文本')}")
        L.append("")
        L.append("| 信号 | 命中 | 证据 |")
        L.append("|---|---|---|")
        for k, v in (hk.get("信号") or {}).items():
            if v.get("命中"):
                L.append(f"| {k} | {v['命中']} | {', '.join(map(str, v['证据'][:5]))} |")
        L.append(f"\n钩子信号种类数：**{hk.get('信号种类数')}**")
        L.append("")
        L.append("| 段落 | 字数 | 占比 | 首句 |")
        L.append("|---|---|---|---|")
        for s in tm.get("structure", []):
            L.append(f"| {s['段']} | {s['字数']} | {s['占比']} | {s['首句']} |")
        L.append("")
        for name, key in [("CTA 命中", "cta"), ("互动引导", "engage"), ("免责话术", "disclaimer")]:
            items = tm.get(key) or []
            s = "、".join(f"{i['词']}×{i['次数']}" for i in items) or "无"
            L.append(f"- {name}：{s}")
        L.append("")

    if data.get("top_comments"):
        L.append("## 五、前排评论（爆款的第二个证据源）")
        L.append("")
        for i, c in enumerate(data["top_comments"][:15], 1):
            L.append(f"{i}. {c}")
        L.append("")

    files = data.get("files", {}) or {}
    if files.get("frames_dir"):
        L.append("## 六、素材索引")
        L.append("")
        L.append(f"- 视频：`{files.get('video') or '未下载'}`")
        L.append(f"- 帧图目录：`{files['frames_dir']}`")
        L.append("")

    L.append("## 七、爆款归因（八维，主 Agent 填）")
    L.append("")
    L.append("> 每维必须写三件事：**证据（第几秒/第几句）→ 判读 → 验证程度🔴🟡⚠️**。")
    L.append("> 🔴 已量化验证（有计数或帧佐证）｜🟡 推断（读稿判断）｜⚠️ 待验证（无对照组，说不清因果）")
    L.append("")
    for name, hint, lvl in DIMENSIONS:
        L.append(f"### {name}　`{lvl}`")
        L.append("")
        L.append(f"*判读要点：{hint}*")
        L.append("")
        L.append("**证据：**")
        L.append("")
        L.append("**判读：**")
        L.append("")
    L.append("## 八、可迁移清单（这条里我们能抄的）")
    L.append("")
    L.append("| 可迁移点 | 怎么用到自己的号 | 风险/前提 |")
    L.append("|---|---|---|")
    L.append("|  |  |  |")
    L.append("")
    L.append("## 九、边界与免责")
    L.append("")
    L.append("- 单条拆解无对照组，「爆款原因」只能是**强相关因素**，不是因果。")
    L.append(f"- 数据抓取于 {data.get('captured_at_human', '—')}，之后指标会继续变化，引用请带时间。")
    L.append("- 转写为 Whisper 本地识别，专有名词可能有错字，引用前对照原视频。")
    L.append("")

    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"✅ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
