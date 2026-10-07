#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data.json + 转写稿 拼成单条视频拆解报告骨架（Markdown）。

用法:
  python3 build_report.py --workdir <工作目录> [--transcript script.txt] [--type 口播类] [--out 报告.md]

产物：四章报告骨架（数据快照 / 自带文案 / 全文+逐句标注 / 七维拆解）。
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


# 互动结构比率经验线（经验假设，只作线索不作结论）
RATIO_LINE = {"comment_per_like": 0.08, "collect_per_like": 0.15, "share_per_like": 0.05}
RATIO_ZH = {"comment_per_like": "评赞比", "collect_per_like": "藏赞比", "share_per_like": "转赞比"}


def fmt(n):
    return "—" if n is None else f"{n:,}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--transcript", help="转写 txt 路径，默认工作目录下 script_*.txt")
    ap.add_argument("--type", default="", help="视频类型：口播类/门诊类/科普类/人设类")
    ap.add_argument("--fit", default="", help="适合科室（如「全部科室」「骨科/康复科」）")
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
    # 类型 + 适合科室：这条能不能被别人抄，先看这两栏
    if vtype or args.fit:
        L.append(f"> **类型：{vtype or '（待判）'}**"
                 + (f"　|　**适合科室：{args.fit}**" if args.fit else "　|　**适合科室：（待补）**"))
        if not args.fit:
            L.append("> 待补口径：这条的爆点**依赖专科知识吗**？依赖 → 写具体科室；不依赖（靠身份/喊话/结构）→ "
                     "写「全部科室」，并说明那个可替换的锚点是什么。")
        L.append(">")
    L.append(f"> 来源：{data.get('url')}  ")
    L.append(f"> **数据抓取时刻：{data.get('captured_at_human', '—')}**  ")
    L.append(f"> 发布：{data.get('publish_time') or '—'}　存续 {data.get('age_days', '—')} 天　"
             f"时长 {(data.get('duration_ms') or 0) / 1000:.1f}s  ")
    L.append("")

    L.append("## 一、数据快照")
    L.append("")
    L.append("| 指标 | 数值 | 偏离 |")
    L.append("|---|---|---|")
    raw = data.get("metrics_raw", {}) or {}
    likes = mt.get("likes") or 0
    rows = [("点赞", "likes", None),
            ("评论", "comments", "comment_per_like"),
            ("收藏", "collects", "collect_per_like"),
            ("转发", "shares", "share_per_like")]
    for zh, k, dk in rows:
        ratio = (mt.get(k) / likes) if (dk and likes) else None
        if ratio is None:
            note = "基准"
            if zh == "点赞":
                note = "基准" + ("（页面只到万级，为估算值）"
                                 if "万" in str(raw.get(k) or "") else "")
        else:
            line = RATIO_LINE[dk]
            pct = f"{ratio * 100:.1f}%"
            # 只分两档：超线 = 🔴 偏高，不足 0.6 倍 = 偏低。别再细分「很高」——
            # 实测阈值会把 1.29 倍和 1.30 倍分成两档，那是自欺。
            if ratio >= line:
                flag, word = "🔴", "偏高"
            elif ratio >= line * 0.6:
                flag, word = "", "正常"
            else:
                flag, word = "", "偏低"
            note = f"{RATIO_ZH[dk]} **{pct}** {flag} {word}（经验线 {line * 100:.0f}%）"
        rv = raw.get(k) or fmt(mt.get(k))
        if rv.isdigit():                      # 纯数字统一加千分位，带「万」的原样保留
            rv = fmt(int(rv))
        L.append(f"| {zh} | {rv} | {note} |")
    L.append("")
    L.append("> 抖音数字是活的，引用必须带上方的抓取时刻。"
             "比率只标偏离，正常项不展开。")
    L.append("")
    L.append("**互动结构**（一句话：上面几个比率合起来说明这条的观众在干什么）：")
    L.append("（待补：高藏+高评+低转 → 观众当「人脉」存起来、在评论区认亲，但不转给外人。"
             "结合内容改成自己的话，一行，不要展开）")
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

    # 第四章：七维拆解（2026-10-04 用户定的维度，全部占位由主 Agent 填）
    L.append("## 四、七维拆解")
    L.append("")
    L.append("> 顺序就是优先级：选题和角度定这条是不是好料，钩子结构定它能不能被看见，")
    L.append("> 后四维是工艺。每维都要落到**具体的秒/句/帧**，不许写「节奏很好」「画面干净」这种话。")
    L.append("")
    L.append("### 1. 选题")
    L.append("（这条选的是什么人群、什么母题？检验标准：它选的人跟同类视频选的不是同一群，才算有选题）")
    L.append("")
    L.append("### 2. 角度")
    L.append("（同一选题下它站的切入位：别人都从 A 进，它从哪进？）")
    L.append("")
    L.append("### 3. 钩子结构（三钩分开看，2026-10-04 用户定义）")
    L.append("- **视觉钩**（刚开始的画面）：")
    L.append("- **口播钩**（开头那几句口述文案）：")
    L.append("- **文字钩**（印在屏幕上的文字，**不是字幕**）：")
    L.append("- 三钩怎么叠加（哪钩缺位、哪钩补位）：")
    L.append("")
    L.append("### 4. 故事结构")
    L.append("（有人物/冲突/转折就写；没有就写清楚它实际是什么结构——公开信/清单/问答/自我介绍，别硬套故事）")
    L.append("")
    L.append("### 5. 视觉版式")
    L.append("（字幕板样式/颜色策略/字幕节奏[累积还是换屏]/机位与运镜）")
    L.append("")
    L.append("### 6. 关键画面")
    L.append("（按时间列画面切换，每个场景干一件事；格式：[秒] 画面 → 它在建立什么）")
    L.append("")
    L.append("### 7. 音频")
    L.append("（BGM 选曲逻辑：歌词与叙事是否同构；口播/同期声有无，为什么）")
    L.append("")

    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"✅ {out}" + (f"（类型：{vtype}）" if vtype else "（未判类型）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
