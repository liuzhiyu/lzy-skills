#!/usr/bin/env python3
"""
18 元素提取 + 爆款/对照组对比统计
=================================================
对已抓取的视频（转写 script_<ID>.txt + 视频 v_<ID>.mp4）做可程序化的元素检测，
输出每条视频的元素 JSON + 爆款 vs 对照组的命中率对比。

用法：
  python3 analyze_elements.py --workdir <目录> \
      --viral 763940... 766721... \
      --control 762070... 763146...

说明：本脚本做「可程序化检测」的维度（文本层 + 时长）。
      画面层（场景/镜头/POV/字幕等）与 BGM 需主 Agent 逐帧目视 / classify_bgm.py 补充。
"""
import argparse
import json
import os
import re
import subprocess


def read_script(path):
    """读转写，去掉时间戳，返回纯文本。"""
    if not os.path.exists(path):
        return ""
    lines = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        ln = re.sub(r"^\[\d{1,2}:\d{2}([:.]\d+)?\]\s*", "", ln)  # 去 [MM:SS]
        if ln:
            lines.append(ln)
    return "\n".join(lines)


def video_duration(video_path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True,
        )
        return round(float(r.stdout.strip()), 1)
    except Exception:
        return None


# ---- 各元素检测规则（正则，基于 20 条样本验证出的真变量） ----
RULES = {
    # 钩子句式
    "返场钩子": r"再(说|讲|发|强调)(一次|一遍)|最后(说|讲|一遍)|第二次(说|讲)|(因为|这是)?有用.{0,4}再说",
    "缘分钩子": r"有缘人|缘分|刷到我|只教给|只交给|只(分|交)给",
    "秘密钩子": r"9[05]%|(都|却)不知道|不愿公开|别人不说|医生不(说|常开|公开)",
    "紧迫钩子": r"千万|赶紧|马上|别划走|别着急|抓紧|记住|一定要",
    # 数字配伍（克数×动作）
    "精确克数": r"\d+\s*(克|g|毫升|ml|斤|两|片|粒)",
    "配伍动作": r"煮水|泡水|煮(开|熟)?|泡(一)?(杯)?|喝|敷|贴|按摩|按揉|熏蒸|熬",
    # 体感 vs 医学
    "体感词": r"疼|痛|痒|胀|抽|麻|酸|烧|堵|憋|喘|冒汗|睡不着|睡不着觉|拉不出|便秘|尿|抽筋",
    "医学词": r"气血|淤|瘀|辨证|齿痕|舌(苔|尖|边)|脉象|脏腑|湿(气|热|寒)|寒(湿|气)|虚(火|寒)|肝气|脾(虚|胃)|经络",
    # 互动话术
    "互动话术": r"小红花|加号|点(赞|关注|个)|收藏|关注|谢谢|福报|支持",
    # 信任反转
    "信任反转": r"不收费|免费|爱上哪买|上哪买|不(卖|收)钱|一分钱不",
    # 免责（反向信号）
    "免责话术": r"辨证|遵医嘱|具体情况|因人而异|医生指导|请勿|不建议自行|仅作参考",
}


def detect(text):
    d = {}
    for k, pat in RULES.items():
        d[k] = bool(re.search(pat, text))
    # 数字计数
    d["数字出现次数"] = len(re.findall(r"\d+", text))
    d["克数出现次数"] = len(re.findall(r"\d+\s*克", text))
    d["字数"] = len(text)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--viral", nargs="+", default=[])
    ap.add_argument("--control", nargs="+", default=[])
    ap.add_argument("--out", default="elements.json")
    args = ap.parse_args()

    all_ids = args.viral + args.control
    results = {}
    for vid in all_ids:
        txt = read_script(os.path.join(args.workdir, f"script_{vid}.txt"))
        dur = video_duration(os.path.join(args.workdir, f"v_{vid}.mp4"))
        elem = detect(txt)
        elem["时长"] = dur
        elem["id"] = vid
        results[vid] = elem

    # 写入 json
    out_path = os.path.join(args.workdir, args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 汇总对比
    def rate(ids, key):
        if not ids:
            return None
        return sum(1 for i in ids if results.get(i, {}).get(key)) / len(ids)

    print("=" * 72)
    print(f"元素对比统计（爆款 {len(args.viral)} vs 对照 {len(args.control)}）")
    print("=" * 72)
    print(f"{'维度':<12} {'爆款':>8} {'对照':>8} {'差值':>8}")
    print("-" * 72)
    for key in RULES:
        rv = rate(args.viral, key)
        rc = rate(args.control, key)
        if rv is None or rc is None:
            continue
        diff = rv - rc
        flag = "  ← 显著" if abs(diff) >= 0.3 else ""
        print(f"{key:<12} {rv*100:>6.0f}% {rc*100:>6.0f}% {diff*100:>+6.0f}%{flag}")

    print("-" * 72)
    # 数值维度均值
    for key in ("字数", "数字出现次数", "克数出现次数", "时长"):
        vals_v = [results[i][key] for i in args.viral if results.get(i, {}).get(key) is not None]
        vals_c = [results[i][key] for i in args.control if results.get(i, {}).get(key) is not None]
        if vals_v and vals_c:
            mv = sum(vals_v) / len(vals_v)
            mc = sum(vals_c) / len(vals_c)
            print(f"{key:<12} {mv:>8.1f} {mc:>8.1f} {mv-mc:>+8.1f}")

    print(f"\n元素明细已写 → {out_path}")
    # 打印每条一句话摘要
    print("\n【逐条摘要】")
    for vid in all_ids:
        e = results[vid]
        grp = "爆款" if vid in args.viral else "对照"
        hits = [k for k in RULES if e.get(k)]
        print(f"  [{grp}] {vid} 时长{e.get('时长')}s 命中: {', '.join(hits) if hits else '无'}")


if __name__ == "__main__":
    main()
