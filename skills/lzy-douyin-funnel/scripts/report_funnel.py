# -*- coding: utf-8 -*-
"""抖音搜索词「完整漏斗」合并报告：landscape（搜索生态）+ 评论区客资 → 单页 HTML
用法: python3 report_funnel.py <config_module> <workdir> <关键词> [topN=100]
输出: <workdir>/funnel_report.html
"""
import os, sys, re, importlib, subprocess

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)
PY = sys.executable

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "config_base"
WORK = sys.argv[2]
KW = sys.argv[3] if len(sys.argv) > 3 else ""
TOPN = int(sys.argv[4]) if len(sys.argv) > 4 else 100

cfg = importlib.import_module(CONFIG)

# 1) landscape 报告
subprocess.run([PY, os.path.join(SKILL_DIR, "landscape.py"), CONFIG,
                os.path.join(WORK, "list.json"), WORK], check=False)
land_path = os.path.join(WORK, "landscape_report.html")
land_body = ""
if os.path.exists(land_path):
    land = open(land_path, encoding="utf-8").read()
    m = re.search(r"<body[^>]*>(.*)</body>", land, re.S)
    land_body = m.group(1) if m else ""

# 2) 评论区客资报告
from analyze import run_analysis
from report_comments import render_html
_, S = run_analysis(WORK, KW, TOPN, cfg)
comments_html = render_html(S, cfg)
m = re.search(r"<body[^>]*>(.*)</body>", comments_html, re.S)
comments_body = m.group(1) if m else comments_html

color = getattr(cfg, "ACCENT", "#7a5aa8")
title = getattr(cfg, "COMMENT_TITLE", "抖音搜索词完整漏斗分析")

HTML = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}（完整漏斗）</title>
<style>
body{{margin:0;background:#f7f8fa;color:#1f2329;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",Arial,sans-serif;line-height:1.7;font-size:14px}}
.wrap{{max-width:1040px;margin:0 auto;padding:30px 24px 80px}}
h1{{font-size:26px;margin:0 0 4px;padding-left:0}}
.sub{{color:#5f6672;font-size:13px;margin-bottom:24px}}
.stage{{background:{color};color:#fff;border-radius:10px;padding:10px 18px;font-size:15px;font-weight:700;margin:36px 0 14px;display:inline-block}}
footer{{color:#9aa0aa;font-size:12px;margin-top:40px;text-align:center}}
</style></head><body><div class="wrap">
<h1>{title}（完整漏斗）</h1>
<div class="sub">搜索词「{KW}」· 视频 {S['n_videos']} 条 · 评论总数 {S['tot_c']} · 由 douyin-comment-lead-analysis skill 生成</div>

<div class="stage">阶段一 · 搜索生态 landscape</div>
{land_body}

<div class="stage">阶段二 · 评论区客资 leads</div>
{comments_body}

<footer>完整漏斗报告：landscape（搜索生态）+ 评论区客资（leads）。结论需结合两阶段人工撰写。</footer>
</div></body></html>"""

out = os.path.join(WORK, "funnel_report.html")
open(out, "w", encoding="utf-8").write(HTML)
print("funnel ok", len(HTML), "->", out)
