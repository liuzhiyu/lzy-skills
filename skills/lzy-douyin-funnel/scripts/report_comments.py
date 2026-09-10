# -*- coding: utf-8 -*-
"""抖音搜索词「评论区客资」HTML 报告渲染器（配置驱动）
用法: python3 report_comments.py <config_module> <workdir> <关键词> [topN=100]
读取 <workdir>/list.json + comments/，复用 analyze.run_analysis 计算，渲染可视化 HTML。
输出: <workdir>/comments_report.html
"""
import os, sys, json, importlib

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)
from analyze import run_analysis

CLS_NAME = {"A1": "A1 强意向", "A2": "A2 求方法", "A3": "A3 钩子留资", "A4": "A4 @AI代写",
            "B": "B 同行共鸣", "C": "C 泛互动", "None": "无关/未归类"}


def render_html(S, cfg):
    color = getattr(cfg, "ACCENT", "#7a5aa8")
    title = getattr(cfg, "COMMENT_TITLE", "抖音搜索评论区线索分析")
    a1p = S["comp_pct"]["A1"]
    hooks = S["hooks"]
    hook_rate = f"{S['n_hook_videos']}/{S['n_done']}"

    # 评论构成条
    comp_rows = "".join(
        f'<div class="bar-row"><div class="bar-label">{CLS_NAME[k]}</div>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{S["comp_pct"][k]/max(1,max(S["comp_pct"].values()))*420:.1f}px;background:{color}"></div>'
        f'<span class="bar-val">{S["cls"][k]}（{S["comp_pct"][k]}%）</span></div></div>'
        for k in ["A1", "A2", "A3", "A4", "B", "C", "None"])

    cross_rows = "".join(
        f'<tr><td>{c["name"]}</td><td>{c["n1"]}</td><td><b>{c["ld1"]}%</b></td>'
        f'<td>{c["n2"]}</td><td>{c["ld2"]}%</td><td><b>{c["mult"]}×</b></td>'
        f'<td>{c["a41"]}% / {c["a42"]}%</td></tr>' for c in S["crosses"])

    quad_rows = "".join(
        f'<tr><td>{q["key"]}</td><td>{q["n"]}</td><td>{q["c"]}</td><td><b>{q["ld"]}%</b></td>'
        f'<td>{q["a1"]}%</td><td>{q["a4"]}%</td><td>{q["b"]}%</td></tr>' for q in S["quad"])

    hook_rows = "".join(
        f'<tr><td><b>{h["word"]}</b></td><td>{h["count"]}</td><td>{h["c_total"]}</td>'
        f'<td>{h["count"]/max(1,h["c_total"])*100:.0f}%</td><td>{h["likes"]}</td><td>@{h["author"]}</td></tr>'
        for h in S["hooks"]
        ) or '<tr><td colspan="6" class="muted">无视频设置留资钩子</td></tr>'

    a1_rows = "".join(
        f'<div class="quote"><span class="badge">[{s["tag"]}]</span> 赞{s["likes"]} · {s["content"]}'
        f'<span class="muted"> — 视频 @{s["author"]}</span></div>' for s in S["a1_samples"][:20]) or '<div class="muted">无 A1 强意向评论</div>'

    a4_rows = "".join(
        f'<div class="quote">赞{s["likes"]} · {s["content"]}<span class="muted"> — 视频 @{s["author"]}</span></div>'
        for s in S["a4_samples"][:12]) or '<div class="muted">无 @AI 代写评论</div>'

    tag_rows = " ".join(f'<span class="tg">#{t}({c})</span>' for t, c in S["top_tags"][:30])

    leads_rows = "".join(
        f'<tr><td>{r["rank"]}</td><td class="tt">{r["title"][:40] or "—"}</td><td>@{r["author"]}</td>'
        f'<td class="num">{r["likes"]}</td><td class="num">{r["A1"]}/{r["A2"]}/{r["A3"]}</td>'
        f'<td class="num">{r["lr"]}</td><td>{"🔔"+r["hook"] if r["hook"] else "—"}</td></tr>'
        for r in S["leads_top"][:25] if r["lr"] != "")

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
:root{{--bg:#f7f8fa;--card:#fff;--line:#e6e8eb;--tx:#1f2329;--tx2:#5f6672;--accent:{color};}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);
 font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",Arial,sans-serif;line-height:1.7;font-size:14px}}
.wrap{{max-width:1000px;margin:0 auto;padding:40px 24px 80px}}h1{{font-size:24px;margin:0 0 6px}}
.sub{{color:var(--tx2);font-size:13px;margin-bottom:24px}}
h2{{font-size:19px;margin:36px 0 14px;padding-left:11px;border-left:4px solid var(--accent)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:16px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:8px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
.kpi .v{{font-size:22px;font-weight:700;color:var(--accent)}}.kpi .l{{font-size:12px;color:var(--tx2);margin-top:2px}}
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:7px;font-size:13px}}
.bar-label{{flex:0 0 150px}}.bar-track{{flex:1;display:flex;align-items:center;gap:8px}}
.bar-fill{{height:15px;border-radius:4px;min-width:3px}}
.bar-val{{font-size:12px;color:var(--tx2);white-space:nowrap}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{background:#f2f4f7;color:var(--tx2);font-weight:600}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.muted{{color:var(--tx2);font-size:12px}}.tg{{display:inline-block;background:#f0f2f5;color:#6b7280;border-radius:4px;padding:1px 6px;font-size:11px;margin:2px 4px 0 0}}
.quote{{font-size:13px;padding:6px 0;border-bottom:1px dashed var(--line)}}
.badge{{display:inline-block;background:var(--accent);color:#fff;border-radius:4px;padding:0 6px;font-size:11px;margin-right:6px}}
.note{{background:#fffaf0;border:1px solid #f3e2c0;border-radius:10px;padding:14px 18px;font-size:13px;color:#7a5c1e}}
footer{{color:#9aa0aa;font-size:12px;margin-top:40px;text-align:center}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<div class="sub">搜索词「{S['kw']}」· 视频 {S['n_videos']} 条 · 拿到评论 {S['n_done']} 条 · 评论总数 {S['tot_c']}</div>
<div class="kpis">
<div class="kpi"><div class="v">{S['n_videos']}</div><div class="l">搜索视频数</div></div>
<div class="kpi"><div class="v">{S['n_done']}</div><div class="l">取到评论视频</div></div>
<div class="kpi"><div class="v">{S['tot_c']}</div><div class="l">评论总数</div></div>
<div class="kpi"><div class="v">{a1p}%</div><div class="l">A1 强意向占比</div></div>
<div class="kpi"><div class="v">{hook_rate}</div><div class="l">设留资钩子视频</div></div>
</div>
<h2>一、评论构成</h2><div class="card">{comp_rows}</div>
<h2>二、交叉分析（控制变量）</h2>
<div class="card"><table><thead><tr><th>内容特征</th><th>该组</th><th>线索率</th><th>对比组</th><th>线索率</th><th>倍数</th><th>@AI占比(该/对)</th></tr></thead>
<tbody>{cross_rows}</tbody></table></div>
<h2>三、四象限（{ " / ".join(q["key"] for q in S["quad"]) }）</h2>
<div class="card"><table><thead><tr><th>象限</th><th>视频</th><th>评论</th><th>线索率</th><th>A1</th><th>@AI</th><th>同行共鸣</th></tr></thead>
<tbody>{quad_rows}</tbody></table>
<div class="note">务必对比「钩子+案例」与「只有案例」「都没有」的线索率差——单变量高很可能只是假相关，真正起作用的是留资钩子。</div></div>
<h2>四、留资钩子盘点</h2>
<div class="card"><table><thead><tr><th>暗号</th><th>条数</th><th>该视频评论数</th><th>占比</th><th>点赞</th><th>作者</th></tr></thead>
<tbody>{hook_rows}</tbody></table></div>
<h2>五、客户咨询原话（A1，按点赞）</h2><div class="card">{a1_rows}</div>
<h2>六、@AI 代写原话（A4，按点赞）</h2><div class="card">{a4_rows}</div>
<h2>七、高频标签</h2><div class="card">{tag_rows}</div>
<h2>八、线索视频 TOP（线索率降序）</h2>
<div class="card"><table><thead><tr><th>#</th><th>标题</th><th>作者</th><th>点赞</th><th>A1/A2/A3</th><th>线索率%</th><th>钩子</th></tr></thead>
<tbody>{leads_rows}</tbody></table></div>
<footer>报告由 douyin-comment-lead-analysis skill 自动生成 · 数据口径见 analyze.py</footer>
</div></body></html>"""


def main():
    CONFIG = sys.argv[1] if len(sys.argv) > 1 else "config_base"
    cfg = importlib.import_module(CONFIG)
    WORK = sys.argv[2]
    KW = sys.argv[3] if len(sys.argv) > 3 else ""
    TOPN = int(sys.argv[4]) if len(sys.argv) > 4 else 100
    _, S = run_analysis(WORK, KW, TOPN, cfg)
    html = render_html(S, cfg)
    out = os.path.join(WORK, "comments_report.html")
    open(out, "w", encoding="utf-8").write(html)
    print("report ok", len(html), "->", out)


if __name__ == "__main__":
    main()
