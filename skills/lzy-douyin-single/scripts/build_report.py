#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data.json + 转写稿 拼成单条视频拆解报告骨架（Markdown）。

用法:
  python3 build_report.py --workdir <工作目录> [--transcript script.txt] [--type 口播类] [--out 报告.md]

产物：三章精简报告骨架（数据快照 / 自带文案 / 全文+逐句标注）。
关键：**先判类型，再选分析主线**——门诊类走故事线，口播类走文案线，不同类型标注词表不同。

理由：数据和计数可以程序化，归因是判断——判断不外包（lzy 工具箱设计原则）。
      v2.2 起：程序化指标（text_metrics.json）**不再进报告**，只作判类型与写标注时的后台参考
      （用户 2026-09-30 拍板：指标堆砌是废话，报告只留素材 + 文案 + 逐句亮点）。
"""
import argparse
import json
import os
import sys

# 类型 → 分析主线 + 标注词表
TYPE_GUIDE = {
    "口播类": {
        "主线": "文案驱动。逐句看「这句话在干什么」：怎么点名、怎么立人设、怎么戳痛点、怎么收口。",
        "词表": ["圈人群", "认亲/降维", "人设专业背书", "情感钩", "戳痛点",
                 "给承诺·希望种草", "二次点名·划定范围", "CTA·人设定型", "留人/防划走"],
        "提示": "本类也cover「无口播的字幕型」——文本在屏幕上时，按字幕逐句标。",
    },
    "门诊类": {
        "主线": "故事驱动。看人物、冲突、转折、结局：谁来了、他卡在哪、医生做了什么、结果怎样、留了什么尾巴。",
        "词表": ["人物出场", "处境/冲突", "误判或踩坑", "医生的判断动作", "转折",
                 "结局与结果", "留白/追问", "信任落点", "给患者/观众的行动指引"],
        "提示": "门诊类的钩子往往在「这个病人有多典型」，不在文案本身——别套口播类那套词表。",
    },
    "科普类": {
        "主线": "结构驱动。看信息怎么组织：用什么问题钩住、先破哪个误区、怎么讲原理、给不给方案。",
        "词表": ["钩子问题", "误区破除", "原理拆解", "案例佐证", "方案/清单", "收口与复述"],
        "提示": "科普类最容易做成说明书——标注时重点看它有没有「先破后立」和对观众说的话。",
    },
    "人设类": {
        "主线": "身份驱动。看它怎么立人：亮什么身份、表什么态、用什么处境换共鸣。",
        "词表": ["身份标签", "价值观表态", "处境共鸣", "反差/反转", "自我暴露", "行动号召"],
        "提示": "人设类没有知识点，别去找「讲了个什么道理」，去看他把自己摆在了什么位置。",
    },
}

TYPE_SIGNALS = """判类型的信号（目视 + 转写后综合判断，拿不准就选最接近的）：
- 转写 < 50 字、内容像歌词 → **无口播字幕型**，按口播类走
- 画面出现第二个真人 + 诊室/病房/白大褂 + 有对话 → **门诊类**
- 医生独自讲、术语密度高、有板书或图 → **科普类**
- 不讲知识、讲态度/生活/出诊日常 → **人设类**"""


def fmt(n):
    return "—" if n is None else f"{n:,}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--transcript", help="转写 txt 路径，默认工作目录下 script_*.txt")
    ap.add_argument("--type", default="", help="视频类型：口播类/门诊类/科普类/人设类")
    ap.add_argument("--out", help="输出 md 路径")
    args = ap.parse_args()

    wd = os.path.abspath(args.workdir)
    data = {}
    dp = os.path.join(wd, "data.json")
    if os.path.exists(dp):
        data = json.load(open(dp, encoding="utf-8"))

    transcript = args.transcript
    if not transcript:
        cands = [f for f in os.listdir(wd)
                 if (f.startswith("script_") or f.startswith("captions_")) and f.endswith(".txt")]
        transcript = os.path.join(wd, sorted(cands)[-1]) if cands else None
    tbody = ""
    if transcript and os.path.exists(transcript):
        tbody = "\n".join(l for l in open(transcript, encoding="utf-8").read().splitlines()
                          if not l.strip().startswith("#")).strip()

    mt = data.get("metrics", {}) or {}
    vid = data.get("video_id", "unknown")
    out = args.out or os.path.join(wd, f"单条拆解_{vid}.md")

    vtype = args.type.strip()
    guide = TYPE_GUIDE.get(vtype)

    L = []
    nick = (data.get("author", {}).get("nickname") or "未知作者").split("\n")[0].strip()[:15]
    L.append(f"# {nick} · "
             f"{(data.get('content') or '').split('#')[0].strip()[:24] or '未命名'} · {vid}")
    L.append("")
    if os.path.exists(os.path.join(wd, f"preview_{vid}.gif")):
        L.append(f"![原片动图预览（GIF 压缩，无声）](preview_{vid}.gif)")
        L.append("")
    L.append(f"> 来源：{data.get('url')}  ")
    L.append(f"> **数据抓取时刻：{data.get('captured_at_human', '—')}**  ")
    L.append(f"> 发布：{data.get('publish_time') or '—'}　存续 {data.get('age_days', '—')} 天　"
             f"时长 {(data.get('duration_ms') or 0) / 1000:.1f}s  ")
    L.append("")

    L.append("## 一、数据快照")
    L.append("")
    L.append("| 指标 | 数值 |")
    L.append("|---|---|")
    raw = data.get("metrics_raw", {}) or {}
    for zh, k in [("点赞", "likes"), ("评论", "comments"), ("收藏", "collects"), ("转发", "shares")]:
        L.append(f"| {zh} | {raw.get(k) or fmt(mt.get(k))} |")
    L.append("")
    L.append("> 抖音数字是活的，引用必须带上方的抓取时刻。")
    L.append("")

    L.append("## 二、视频自带文案（标题 + 正文 + 话题）")
    L.append("")
    L.append("```")
    L.append(data.get("content") or "（未抓到，可能登录态失效）")
    L.append("```")
    L.append("")

    L.append("## 三、口播转写全文")
    L.append("")
    if tbody:
        L.append(tbody)
    else:
        L.append("（未转写/无口播——若为字幕型，逐帧目视拼成 captions_<id>.txt 后重跑本步）")
    L.append("")

    L.append("### 逐句亮点标注（每句话在干什么）")
    L.append("")
    if guide:
        L.append(f"> **类型：{vtype}**　分析主线：{guide['主线']}")
        L.append(f"> 标注词表：{' / '.join(guide['词表'])}")
        L.append(f"> {guide['提示']}")
    else:
        L.append("> ⚠️ 未判类型。**先判类型再写标注**——门诊类走故事角度，口播类走文案角度，套错词表等于白拆。")
        L.append(">")
        for line in TYPE_SIGNALS.splitlines():
            L.append(f"> {line}")
    L.append("")
    L.append("**（原句）**")
    L.append("【标注】")
    L.append("")

    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"✅ {out}" + (f"（类型：{vtype}）" if vtype else "（未判类型）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
