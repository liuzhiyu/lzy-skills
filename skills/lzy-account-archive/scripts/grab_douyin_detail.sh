#!/bin/bash
# 抓单条抖音视频详情：标题/全文案/发布日期/指标（赞评转藏）
# 用法: bash grab_douyin_detail.sh <video_id> <输出json路径>
# 输出: 单条 JSON（字段宽容，交给 archive.py merge 归一化）
# 优先从 RENDER_DATA（抖音 SSR 数据）提取，DOM 为兜底——DOM 结构变了也能拿到数据
set -u

ID="$1"
OUT="$2"
mkdir -p "$(dirname "$OUT")"

SID=$(bsk session start 2>&1 | tail -1 | grep -oE '[A-Za-z0-9]{4}' | tail -1)
if [ -z "$SID" ]; then echo "session 创建失败"; exit 1; fi

bsk navigate "https://www.douyin.com/video/$ID" --session "$SID" --wait-until domcontentloaded --timeout 30000 >/dev/null 2>&1
sleep 6

# 深搜 SSR 数据：找带 desc + 计数字段的对象
EXTRACT_JS='JSON.stringify((()=>{const el=document.getElementById("RENDER_DATA");let root=null;if(el){try{root=JSON.parse(decodeURIComponent(el.textContent));}catch(e){}}if(!root){root=window.__INITIAL_STATE__||null;}const hits=[];const walk=(o,d)=>{if(!o||typeof o!=="object"||d>9)return;if(typeof o.desc==="string"&&o.desc.length>0&&(o.create_time||o.statistics||o.digg_count!==undefined)){hits.push({id:o.aweme_id||o.awemeId||"",desc:o.desc,title:o.title||"",create_time:o.create_time||null,statistics:o.statistics||{digg_count:o.digg_count,comment_count:o.comment_count,share_count:o.share_count,collect_count:o.collect_count}});}for(const k in o){try{walk(o[k],d+1);}catch(e){}}};walk(root,0);return hits.slice(0,3);})())'

RAW=$(bsk evaluate --session "$SID" "$EXTRACT_JS" 2>/dev/null | tail -1)
bsk session stop "$SID" >/dev/null 2>&1

PY_BIN="${PY_BIN:-python3}"
"$PY_BIN" - "$ID" "$OUT" <<PYEOF
import json, sys, re
vid, out = sys.argv[1], sys.argv[2]
item = {"id": vid, "url": f"https://www.douyin.com/video/{vid}"}
try:
    hits = json.loads('''$RAW''')
except Exception:
    hits = []
best = None
for h in hits:
    if str(h.get("id")) == vid or best is None:
        best = h
    if str(h.get("id")) == vid:
        best = h
        break
if best:
    desc = (best.get("desc") or "").strip()
    item["content"] = desc
    item["title"] = (best.get("title") or desc.split("#")[0].strip() or desc.splitlines()[0][:60]) if desc else ""
    ct = best.get("create_time")
    if isinstance(ct, (int, float)):
        if ct > 1e12: ct /= 1000.0
        from datetime import datetime, timezone, timedelta
        item["publish_date"] = datetime.fromtimestamp(ct, timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    st = best.get("statistics") or {}
    item["metrics"] = {k: st.get(k) for k in ("digg_count","comment_count","share_count","collect_count")}
    item["_source"] = "RENDER_DATA"
else:
    item["_source"] = "none"
json.dump(item, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
has = bool(best)
print(("✅ " if has else "⚠️ SSR 未命中(需校准JS) ") + out)
sys.exit(0 if has else 3)
PYEOF
