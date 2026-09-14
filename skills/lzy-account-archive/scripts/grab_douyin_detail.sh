#!/bin/bash
# 抓单条抖音视频详情：标题/全文案/发布时间/指标（赞评转藏）+ 作品时长
# 用法: bash grab_douyin_detail.sh <video_id> <输出json路径>
# 输出: 单条 JSON（字段宽容，交给 archive.py merge 归一化）
#
# 提取策略（2026-09-14 重写）：
#   ⚠️ 旧版读 RENDER_DATA（SSR）——已失效：现在视频页的 RENDER_DATA 只含 app.user 等壳数据，
#      不含 aweme detail。改为从渲染后的 DOM 提取（data-e2e 锚点 + document.title）。
set -u

ID="$1"
OUT="$2"
mkdir -p "$(dirname "$OUT")"

SID=$(bsk session start 2>&1 | tail -1 | grep -oE '[A-Za-z0-9]{4}' | tail -1)
if [ -z "$SID" ]; then echo "session 创建失败"; exit 1; fi

bsk navigate "https://www.douyin.com/video/$ID" --session "$SID" --wait-until domcontentloaded --timeout 30000 >/dev/null 2>&1
sleep 7

EXTRACT_JS=$(cat <<'JSEOF'
JSON.stringify((()=>{
  const q=s=>{try{const e=document.querySelector('[data-e2e="'+s+'"]');return e?(e.innerText||'').trim():'';}catch(e){return '';}};
  const wrap=document.querySelector('[data-e2e="detail-video-info"]');
  let desc='';
  if(wrap&&wrap.children&&wrap.children[0]){
    desc=(wrap.children[0].innerText||'').replace(/^\s*(展开|收起)\s*/,'').trim();
  }
  const t=(document.title||'').replace(/\s*[-\u2013]\s*抖音\s*$/,'').trim();
  if(t.length>desc.length) desc=t;
  const v=document.querySelector('video');
  return {
    id:(location.pathname.split('/video/')[1]||'').split('?')[0],
    desc:desc,
    ptime:q('detail-video-publish-time'),
    digg:q('video-player-digg'),
    comment:q('feed-comment-icon'),
    collect:q('video-player-collect'),
    share:q('video-player-share'),
    dur:(v&&isFinite(v.duration)&&v.duration>0)?v.duration:null
  };
})())
JSEOF
)

RAW=$(bsk evaluate --session "$SID" "$EXTRACT_JS" 2>/dev/null | tail -1)
bsk session stop "$SID" >/dev/null 2>&1

PY_BIN="${PY_BIN:-python3}"
"$PY_BIN" - "$ID" "$OUT" <<PYEOF
import json, sys, re
from datetime import datetime, timezone, timedelta

vid, out = sys.argv[1], sys.argv[2]
TZ = timezone(timedelta(hours=8))
item = {"id": vid, "url": f"https://www.douyin.com/video/{vid}"}
try:
    d = json.loads('''$RAW''')
except Exception:
    d = None

if isinstance(d, dict) and (d.get("desc") or d.get("digg")):
    desc = (d.get("desc") or "").strip()
    item["content"] = desc
    item["title"] = desc.split("#")[0].strip() or desc.splitlines()[0][:60] if desc else ""
    # 发布时间：文本 "发布时间：2026-09-10 16:49"
    pt = d.get("ptime") or ""
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})[\sT]*(\d{1,2})?:?(\d{2})?", pt)
    if m:
        y, mo, dd = m.group(1), int(m.group(2)), int(m.group(3))
        hh = m.group(4) or "0"
        mi = m.group(5) or "00"
        item["publish_date"] = f"{y}-{mo:02d}-{dd:02d}"
        item["publish_time"] = f"{y}/{mo}/{dd} {int(hh):02d}:{mi}"
    dur = d.get("dur")
    if isinstance(dur, (int, float)) and dur > 0:
        item["duration_ms"] = int(round(float(dur) * 1000))   # 与原 CSV「作品时长」同单位（毫秒）
    # 计数：保留原始字符串（可能是 "1.1万"），archive.py 归一化时处理
    item["metrics"] = {
        "likes": d.get("digg") or 0,
        "comments": d.get("comment") or 0,
        "shares": d.get("share") or 0,
        "collects": d.get("collect") or 0,
    }
    item["_source"] = "DOM"
else:
    item["_source"] = "none"

json.dump(item, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
has = item["_source"] == "DOM" and bool(item.get("content"))
print(("✅ " if has else "⚠️ DOM 未命中 ") + out)
sys.exit(0 if has else 3)
PYEOF
