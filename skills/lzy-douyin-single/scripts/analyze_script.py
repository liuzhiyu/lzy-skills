#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单条抖音口播稿的文本层指标提取（可程序化部分）。

用法:
  python3 analyze_script.py --transcript script.txt --data data.json [--out text_metrics.json]

设计原则:
  - 只做可计数、可复现的部分；语义判断（钩子是不是真钩子、情绪到没到位）留给主 Agent 读全文
  - 钩子窗口 = 前 3 秒（有 [mm:ss] 时间戳时按时间切，没有就按前 25 字估算）
  - 所有命中都给出原句证据，禁止无证据下结论
  - 输出 JSON + 控制台 Markdown 摘要表
"""
import argparse
import json
import os
import re
import sys

# 信号词典：命中即计 1，可 --domain 叠加
SIGNALS = {
    "反常识/否定": ["不要", "别再", "错了", "其实", "真相", "没人告诉", "误区", "以为是", "恰恰相反", "根本不是", "都错了"],
    "人群点名": ["老乡", "老乡们", "同乡", "各位", "朋友们", "姐妹们", "兄弟们", "老板们", "家人们", "宝妈们", "家长们"],
    "身份标签": ["老板", "老板娘", "创业者", "医生", "营养师", "小老板", "实体店", "门店", "诊所", "院长", "宝妈", "打工",
                "副主任医师", "主任医师", "医学博士", "博士", "教授", "律师", "会计"],
    "痛点": ["没效果", "没客户", "做不起来", "亏", "亏钱", "踩坑", "焦虑", "失眠", "疼", "难受", "投不出去", "没人看", "不涨粉", "留不住", "复购低", "被割",
            "冤枉路", "冤枉钱", "被骗", "跑弯路", "花冤枉"],
    "紧迫": ["今天", "现在", "马上", "再不", "最后", "立刻", "趁早", "来不及"],
    "好奇悬念": ["为什么", "凭什么", "秘密", "你不知道", "关键是", "答案", "真相", "到底", "居然", "竟然"],
    "数字/量化": None,  # 走正则
    "结果承诺": ["一定能", "就能", "保证", "必", "让你", "帮你", "从0到", "翻倍", "涨粉", "变现", "客资",
                "帮助到", "尽管找", "最靠谱"],
}

CTA_WORDS = ["关注", "点赞", "收藏", "评论", "私信", "加微信", "微信", "企微", "主页", "咨询", "留言", "扣", "扣1", "告诉我", "来找", "找我", "尽管找"]
ENGAGE_WORDS = ["评论区", "评论里", "打在", "说说", "你说", "你们觉得", "有没有", "对不对", "是不是", "留言"]
DISCLAIM_WORDS = ["仅供参考", "个人观点", "不代表", "请遵医嘱", "不保证", "因人而异", "具体情况", "非医疗建议"]
ORAL_WORDS = ["啊", "呢", "吧", "你看", "其实", "说白了", "所以", "然后", "就是", "这么", "这么着", "对吧", "坦白讲", "实话"]


def split_sentences(text: str):
    """按中文句读切句，保留原文。"""
    parts = re.split(r"(?<=[。！？!?；;])|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


def parse_ts_sentences(text: str):
    """转写稿若带 [mm:ss] 时间戳，返回 [(sec, sent)]；否则返回 None。"""
    pat = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")
    hits = list(pat.finditer(text))
    if len(hits) < 2:
        return None
    out = []
    for i, h in enumerate(hits):
        start = h.end()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        seg = text[start:end].strip()
        if seg:
            sec = int(h.group(1)) * 60 + int(h.group(2))
            out.append((sec, seg))
    return out


def count_hits(text, words):
    hits = []
    low = text
    for w in words:
        n = low.count(w)
        if n:
            hits.append({"词": w, "次数": n})
    return hits


def hook_window(sentences, ts_sents, limit_sec=3):
    """钩子窗口：按时间优先，无时间按前 25 字。"""
    if ts_sents:
        buf = "".join(s for sec, s in ts_sents if sec < limit_sec)
        if buf:
            return buf, f"前 {limit_sec} 秒（按时间戳）"
    buf = ""
    for s in sentences:
        buf += s
        if len(buf) >= 25:
            break
    return buf[:80], "开场合约 25 字（无时间戳，估算）"


def seg_structure(sentences, ts_sents, duration_sec):
    """把稿子按时间或等分切成 4 段，看字数分布（节奏诊断）。"""
    if ts_sents and duration_sec:
        edges = [0, duration_sec * 0.15, duration_sec * 0.5, duration_sec * 0.85, duration_sec + 1]
        buckets = [[] for _ in range(4)]
        for sec, s in ts_sents:
            for i in range(4):
                if edges[i] <= sec < edges[i + 1]:
                    buckets[i].append(s)
                    break
        names = ["开场 0-15%", "展开 15-50%", "论证 50-85%", "收尾 85-100%"]
    else:
        n = len(sentences)
        q = max(n // 4, 1)
        buckets = [sentences[i * q:(i + 1) * q] for i in range(4)]
        if n % 4:
            buckets[3] += sentences[4 * q:]
        names = ["第一段 25%", "第二段 25%", "第三段 25%", "第四段 25%"]
    total = sum(len("".join(b)) for b in buckets) or 1
    return [{"段": names[i], "字数": len("".join(buckets[i])), "占比": round(len("".join(buckets[i])) / total, 3),
             "首句": (buckets[i][0][:40] if buckets[i] else "")} for i in range(4)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True, help="转写 txt 路径")
    ap.add_argument("--data", help="data.json 路径（取时长）")
    ap.add_argument("--out", help="输出 json 路径（默认与转写同目录 text_metrics.json）")
    ap.add_argument("--extra-glossary", help="自定义信号词文件，每行一个词，追加到全部信号类")
    args = ap.parse_args()

    if not os.path.exists(args.transcript):
        print(f"❌ 转写稿不存在: {args.transcript}", file=sys.stderr)
        sys.exit(1)
    text = open(args.transcript, encoding="utf-8").read()
    # 去掉元信息注释行（lzy-video-to-text 归档稿带 # 头）
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#")).strip()

    duration_sec = None
    if args.data and os.path.exists(args.data):
        try:
            d = json.load(open(args.data, encoding="utf-8"))
            if d.get("duration_ms"):
                duration_sec = d["duration_ms"] / 1000.0
        except Exception:
            pass

    sents = split_sentences(body)
    ts_sents = parse_ts_sentences(body)

    extra = []
    if args.extra_glossary and os.path.exists(args.extra_glossary):
        extra = [l.strip() for l in open(args.extra_glossary, encoding="utf-8") if l.strip() and not l.startswith("#")]

    hook, hook_basis = hook_window(sents, ts_sents)

    sig = {}
    for name, words in SIGNALS.items():
        if words is None:
            nums = re.findall(r"\d+(?:\.\d+)?", hook)
            sig[name] = {"命中": len(nums), "证据": nums[:8]}
        else:
            ws = words + (extra if name == "痛点" else [])
            h = count_hits(hook, ws)
            sig[name] = {"命中": sum(x["次数"] for x in h), "证据": [x["词"] for x in h]}

    full = {
        "字数": len(re.sub(r"\s", "", body)),
        "句数": len(sents),
        "平均句长": round(len(re.sub(r"\s", "", body)) / max(len(sents), 1), 1),
        "时长秒": round(duration_sec, 1) if duration_sec else None,
        "语速_字每秒": round(len(re.sub(r"\s", "", body)) / duration_sec, 1) if duration_sec else None,
        "短句占比": round(sum(1 for s in sents if len(s) <= 12) / max(len(sents), 1), 3),
        "口语连接词次数": sum(body.count(w) for w in ORAL_WORDS),
    }

    result = {
        "hook_window": {"文本": hook[:120], "口径": hook_basis, "信号": sig,
                        "信号种类数": sum(1 for v in sig.values() if v["命中"] > 0)},
        "full_text": full,
        "structure": seg_structure(sents, ts_sents, duration_sec),
        "cta": count_hits(body, CTA_WORDS),
        "engage": count_hits(body, ENGAGE_WORDS),
        "disclaimer": count_hits(body, DISCLAIM_WORDS),
        "sentences_head": sents[:5],
        "sentences_tail": sents[-3:],
    }

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.transcript)), "text_metrics.json")
    json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 控制台摘要
    print("\n### 文本层指标")
    print(f"字数 {full['字数']} | 句数 {full['句数']} | 平均句长 {full['平均句长']} 字 | "
          f"时长 {full['时长秒']}s | 语速 {full['语速_字每秒']} 字/s | 短句占比 {full['短句占比']}")
    print(f"\n### 钩子窗口（{hook_basis}）\n> {hook[:100]}")
    print("\n| 信号 | 命中 | 证据 |")
    print("|---|---|---|")
    for k, v in sig.items():
        if v["命中"]:
            print(f"| {k} | {v['命中']} | {', '.join(map(str, v['证据'][:5]))} |")
    print(f"\n钩子信号种类数：**{result['hook_window']['信号种类数']}**（越多越密，≥3 值得注意）")
    print("\n### 结构分布")
    print("| 段 | 字数 | 占比 | 首句 |")
    print("|---|---|---|---|")
    for s in result["structure"]:
        print(f"| {s['段']} | {s['字数']} | {s['占比']} | {s['首句']} |")
    print(f"\nCTA 命中：{result['cta']}\n互动引导：{result['engage']}\n免责话术：{result['disclaimer']}")
    print(f"\n✅ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
