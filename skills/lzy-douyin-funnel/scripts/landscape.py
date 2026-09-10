# -*- coding: utf-8 -*-
"""抖音搜索词「landscape」引擎：标题/标签词频 · 分类 · 话题簇 · 母题 · 身份桶
用法: python3 landscape.py <config_module> <list.json> <outdir>
  config_module: scripts/ 下的 config_xxx.py（如 config_qiaoben / config_base）
  list.json: 来自 fetch_list.sh -> parse_list.py 的搜索结果（需含 title/tags/likes_n/author/rank/id/dur）
输出: <outdir>/landscape_tables.md   数据底稿
      <outdir>/landscape_report.html 可视化报告
领域适配全部在 config 里；本脚本是通用引擎，CATS/TOPICS/MOTHER 为空时自动跳过对应段落。
"""
import json, re, os, sys, collections, statistics, importlib

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

CFG = sys.argv[1] if len(sys.argv) > 1 else "config_base"
cfg = importlib.import_module(CFG)
LIST = sys.argv[2]
OUT = sys.argv[3] if len(sys.argv) > 3 else "."

import jieba
for w in (cfg.DOMAIN or "").split():
    jieba.add_word(w)

items = json.load(open(LIST, encoding="utf-8"))
ALL = [x for x in items if x.get("title")]
TOP = ALL[:100] if len(ALL) >= 100 else ALL
N = len(TOP)

# ---------------- 标签频率 ----------------
tag_df = collections.Counter()
tag_likes = collections.Counter()
for x in TOP:
    for t in set(x.get("tags", [])):
        tag_df[t] += 1
        tag_likes[t] += x["likes_n"]

# ---------------- 标题热词 ----------------
STOP = cfg.STOP
word_cnt = collections.Counter()
word_df = collections.Counter()
word_likes = collections.Counter()
for x in TOP:
    txt = re.sub(r"[^一-龥A-Za-z0-9+#&]", " ", x["title"])
    ws = [w for w in jieba.cut(txt) if len(w) >= 2 and w not in STOP and not w.isdigit()]
    for w in ws:
        word_cnt[w] += 1
        word_likes[w] += x["likes_n"]
    for w in set(ws):
        word_df[w] += 1

# ---------------- 分类体系（可选） ----------------
CATS = getattr(cfg, "CATS", {}) or {}
ORDER = list(CATS.keys())
MOTHER = getattr(cfg, "MOTHER", {}) or {}
MOTHER_DESC = getattr(cfg, "MOTHER_DESC", []) or []
TOPICS = getattr(cfg, "TOPICS", []) or []
AUTH_SELF = getattr(cfg, "AUTH_SELF", re.compile(r"$^"))

def classify(term, _cache={}):
    if term in _cache:
        return _cache[term]
    for name in ORDER:
        for k in CATS[name]:
            if term == k or (len(k) >= 2 and k in term):
                _cache[term] = name
                return name
    _cache[term] = "M 其他/泛话题"
    return _cache[term]

cat_tag = collections.Counter()
cat_tag_likes = collections.Counter()
for t, c in tag_df.items():
    cat_tag[classify(t)] += c
    cat_tag_likes[classify(t)] += tag_likes[t]
cat_word = collections.Counter()
for w, c in word_cnt.items():
    cat_word[classify(w)] += c
cat_video = collections.Counter()
cat_video_likes = collections.Counter()
for x in TOP:
    text = " ".join([x["title"]] + x.get("tags", []))
    for name in ORDER:
        if any((k in text) for k in CATS[name]):
            cat_video[name] += 1
            cat_video_likes[name] += x["likes_n"]

# ---------------- 话题簇（可选） ----------------
topic_hits = {}
topic_hits_broad = {}
for name, pat in TOPICS:
    rx = re.compile(pat)
    strict, broad = [], []
    for x in TOP:
        if rx.search(x["title"]):
            strict.append(x)
        if rx.search(" ".join([x["title"]] + x.get("tags", []))):
            broad.append(x)
    topic_hits[name] = strict
    topic_hits_broad[name] = broad

# ---------------- 身份分桶（可选） ----------------
IDENTITY_BUCKETS = getattr(cfg, "IDENTITY_BUCKETS", {}) or {}
IDENTITY_META = getattr(cfg, "IDENTITY_META", []) or {}
B = {k: [] for k in IDENTITY_BUCKETS}
compiled = {k: re.compile(v) if v else None for k, v in IDENTITY_BUCKETS.items()}

def identity_bucket(a):
    for k, rx in compiled.items():
        if rx and rx.search(a):
            return k
    return "P" if "P" in compiled else (list(IDENTITY_BUCKETS)[-1] if IDENTITY_BUCKETS else "P")

for x in TOP:
    B.setdefault(identity_bucket(x["author"]), []).append(x)
rc = collections.Counter()
for x in TOP:
    for r in IDENTITY_BUCKETS:
        if r in x["author"]:
            rc[r] += 1

lk = sorted(x["likes_n"] for x in TOP)
OVERALL_AVG = int(statistics.mean(lk)) if lk else 0
OVERALL_MED = int(statistics.median(lk)) if lk else 0

# =================== Markdown ===================
out = []
P = out.append
P(f"# {getattr(cfg,'LANDSCAPE_TITLE','抖音搜索结果内容分析')}（数据底稿）\n")
P(f"> 实采 {len(ALL)} 条，分析前 {N} 条\n")
P(f"- 实采/分析条数：{len(ALL)} / {N}；带标签 {sum(1 for x in TOP if x.get('tags'))} 条；去重标签 {len(tag_df)} 个")
P(f"- 点赞中位数 {OVERALL_MED:,}；均值 {OVERALL_AVG:,}；最高 {max(lk):,}")
if CATS:
    P("\n## 一、标签频率 TOP 30\n| 排名 | 标签 | 覆盖视频数 | 平均点赞 |\n|---|---|---|---|")
    for i, (t, c) in enumerate(tag_df.most_common(30), 1):
        P(f"| {i} | #{t} | {c} | {tag_likes[t]//c:,} |")
    P("\n## 二、标题热词 TOP 40\n| 排名 | 关键词 | 出现次数 | 覆盖视频数 | 平均点赞 |\n|---|---|---|---|---|")
    n = 0
    for w, c in word_cnt.most_common(400):
        if c < 3 or n >= 40:
            continue
        n += 1
        P(f"| {n} | {w} | {c} | {word_df[w]} | {word_likes[w]//c:,} |")
    P("\n## 三、关键词分类\n### 3.1 按视频归类\n| 分类 | 命中视频数 | 占比 | 平均点赞 |\n|---|---|---|---|")
    for name, c in sorted(cat_video.items(), key=lambda z: -z[1]):
        P(f"| {name} | {c} | {c/N*100:.0f}% | {cat_video_likes[name]//c:,} |")
    P("\n### 3.2 关键词命中次数\n| 分类 | 热词命中次数 | 分类内高频词 Top8 |\n|---|---|---|")
    for name, c in sorted(cat_word.items(), key=lambda z: -z[1]):
        ex = [w for w, _ in word_cnt.most_common() if classify(w) == name][:8]
        P(f"| {name} | {c} | {'、'.join(ex)} |")
if TOPICS:
    P("\n## 四、话题/观点簇 TOP %d\n| 排名 | 话题 | 标题命中 | 含标签命中 | 平均点赞 | 中位点赞 |\n|---|---|---|---|---|---|" % len(TOPICS))
    for i, (name, hits) in enumerate(sorted(topic_hits.items(), key=lambda z: -len(z[1])), 1):
        lks = [h["likes_n"] for h in hits]
        med = statistics.median(lks) if lks else 0
        avg = sum(lks)//max(1, len(lks))
        P(f"| {i} | {name.split('——')[0].strip()} | {len(hits)} | {len(topic_hits_broad[name])} | {avg:,} | {med:,.0f} |")
if MOTHER_DESC:
    P("\n## 五、母题\n")
    for m, q, color, desc in MOTHER_DESC:
        P(f"- **{m}** · “{q}” — {desc}")
if IDENTITY_META:
    P("\n## 六、身份分桶\n| 身份类型 | 视频数 | 平均点赞 | 中位点赞 | 怎么读 |\n|---|---|---|---|---|")
    for k, nm, color, note in IDENTITY_META:
        v = B.get(k, [])
        if not v:
            P(f"| {nm} | 0 | — | — | {note} |")
            continue
        lks = [z["likes_n"] for z in v]
        P(f"| {nm} | {len(v)} | {sum(lks)//len(v):,} | {int(statistics.median(lks)):,} | {note} |")
P("\n## 七、点赞 TOP 15\n| 排名 | 点赞 | 标题 | 作者 |\n|---|---|---|---|")
for x in sorted(TOP, key=lambda z: -z["likes_n"])[:15]:
    t = x["title"] or ("#" + "/".join(x.get("tags", [])))
    P(f"| {x['rank']} | {x['likes_n']:,} | {t[:40]} | @{x['author']} |")

os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, "landscape_tables.md"), "w", encoding="utf-8").write("\n".join(out))
print("MD ok", len(out))

# =================== HTML ===================
def bars(data, color="#3f6fb5", unit=""):
    mx = max(d[1] for d in data) or 1
    rows = []
    for label, val, *extra in data:
        w = val / mx * 520
        ex = f"<em>{extra[0]}</em>" if extra else ""
        rows.append(f'<div class="bar-row"><div class="bar-label">{label}</div>'
                    f'<div class="bar-track"><div class="bar-fill" style="width:{w:.1f}px;background:{color}"></div>'
                    f'<span class="bar-val">{val}{unit}{ex}</span></div></div>')
    return "\n".join(rows)

chart_tag = bars([(f"#{t}", c, f"均赞 {tag_likes[t]//c:,}") for t, c in tag_df.most_common(15)], "#3f6fb5", "条")
sections = []
if CATS:
    chart_cat = bars([(n, c, f"均赞 {cat_video_likes[n]//c:,}") for n, c in sorted(cat_video.items(), key=lambda z: -z[1])], "#2f7d6f")
    sections.append(("三、关键词分类", f'<div class="card">{chart_cat}</div>'))
if TOPICS:
    ranked = sorted(topic_hits.items(), key=lambda z: -len(z[1]))
    chart_topic = bars([(name.split("——")[0].strip(), len(hits), f"均赞 {sum(x['likes_n'] for x in hits)//max(1,len(hits)):,}") for name, hits in ranked], "#c78a25", "条")
    sections.append(("四、话题/观点簇", f'<div class="card">{chart_topic}</div>'))
if MOTHER_DESC:
    mc = "".join(f'<div class="mother-card" style="border-left:4px solid {color}">'
                 f'<div class="mother-q" style="color:{color}">{m} · “{q}”</div><p>{desc}</p></div>'
                 for m, q, color, desc in MOTHER_DESC)
    sections.append(("五、母题", mc))

word_ww = [(w, c) for w, c in word_cnt.most_common(400) if c >= 3][:35]
word_table = "\n".join(
    f'<tr><td>{i}</td><td><b>{w}</b></td><td>{c}</td><td>{word_df[w]}</td><td>{word_likes[w]//c:,}</td></tr>'
    for i, (w, c) in enumerate(word_ww, 1))

HTML = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{getattr(cfg,'LANDSCAPE_TITLE','抖音搜索结果内容分析')}</title>
<style>
:root{{--bg:#f7f8fa;--card:#fff;--line:#e6e8eb;--tx:#1f2329;--tx2:#5f6672;--accent:#7a5aa8;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);
 font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",Arial,sans-serif;line-height:1.7;font-size:14px}}
.wrap{{max-width:1000px;margin:0 auto;padding:40px 24px 80px}}h1{{font-size:24px;margin:0 0 6px}}
.sub{{color:var(--tx2);font-size:13px;margin-bottom:28px}}
h2{{font-size:19px;margin:36px 0 14px;padding-left:11px;border-left:4px solid var(--accent)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:16px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:8px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
.kpi .v{{font-size:22px;font-weight:700}}.kpi .l{{font-size:12px;color:var(--tx2);margin-top:2px}}
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:7px;font-size:13px}}
.bar-label{{flex:0 0 200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bar-track{{flex:1;display:flex;align-items:center;gap:8px}}
.bar-fill{{height:15px;border-radius:4px;min-width:3px}}
.bar-val{{font-size:12px;color:var(--tx2);white-space:nowrap}}.bar-val em{{font-style:normal;color:#9aa0aa;margin-left:5px}}
.mother-card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:12px}}
.mother-q{{font-size:16px;font-weight:700;margin-bottom:6px}}.mother-card p{{margin:0;font-size:13.5px}}
footer{{color:#9aa0aa;font-size:12px;margin-top:40px;text-align:center}}
</style></head><body><div class="wrap">
<h1>{getattr(cfg,'LANDSCAPE_TITLE','抖音搜索结果内容分析')}</h1>
<div class="sub">分析样本 {N} 条 · 数据源：抖音网页版搜索结果页（视频 tab 默认排序）</div>
<div class="kpis">
<div class="kpi"><div class="v">{len(ALL)}</div><div class="l">实采视频数（分析 {N} 条）</div></div>
<div class="kpi"><div class="v">{len(tag_df)}</div><div class="l">去重话题标签</div></div>
<div class="kpi"><div class="v">{OVERALL_MED:,}</div><div class="l">点赞中位数</div></div>
<div class="kpi"><div class="v">{OVERALL_AVG:,}</div><div class="l">点赞均值</div></div>
<div class="kpi"><div class="v">{len(set(x['author'] for x in TOP))}</div><div class="l">作者数</div></div>
</div>
<h2>一、话题标签 TOP 15</h2><div class="card">{chart_tag}</div>
{(''.join(f'<h2>{t}</h2><div class="card">{c}</div>' for t,c in sections))}
<h2>二、标题热词 TOP 35</h2><div class="card"><table style="width:100%;border-collapse:collapse;font-size:13px">
<thead><tr><th>#</th><th>关键词</th><th>出现次数</th><th>覆盖视频数</th><th>平均点赞</th></tr></thead><tbody>
{word_table}
</tbody></table></div>
<footer>数据口径：抖音网页版搜索视频 tab 默认排序，滚动采集前 {len(ALL)} 条，统计样本为前 {N} 条；点赞为采集时点数值。</footer>
</div></body></html>"""

open(os.path.join(OUT, "landscape_report.html"), "w", encoding="utf-8").write(HTML)
print("HTML ok", len(HTML), "->", os.path.join(OUT, "landscape_report.html"))
