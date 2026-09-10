#!/bin/bash
# 抓小红书账号作品（列表 / 单篇详情）
# 用法:
#   bash grab_xhs.sh list  <主页URL或user_id> <输出目录>     → list.json [{id,alt,n}...]
#   bash grab_xhs.sh note  <note_id> <输出json路径>          → 单条 JSON（标题/全文/日期/指标）
# 小红书数据在 window.__INITIAL_STATE__，深搜提取；未登录可能触发验证墙（见 SKILL.md 校准协议）
set -u

CMD="$1"

EXTRACT_LIST_JS='JSON.stringify(Array.from(document.querySelectorAll("a[href*=\"/explore/\"],a[href*=\"/discovery/item/\"]")).map(a=>{const m=a.href.match(/(?:explore|discovery\/item)\/([0-9a-f]{24})/);const img=a.querySelector("img");const sec=a.closest("section");const spans=sec?Array.from(sec.querySelectorAll("span")).map(s=>s.innerText.trim()).filter(t=>t&&/^[\d.]+万?$/.test(t)):[];return m?{id:m[1],alt:(img?img.alt.slice(0,50):""),n:spans[0]||"?"}:null}).filter(Boolean))'

EXTRACT_NOTE_JS='JSON.stringify((()=>{const root=window.__INITIAL_STATE__||{};const hits=[];const walk=(o,d)=>{if(!o||typeof o!=="object"||d>9)return;if(typeof o.noteId==="string"&&o.noteId.length>0&&(o.desc!==undefined||o.interactInfo)){hits.push({id:o.noteId,title:o.title||"",desc:o.desc||"",time:o.time||o.publishTime||null,interactInfo:o.interactInfo||{}});}for(const k in o){try{walk(o[k],d+1);}catch(e){}}};walk(root,0);return hits.slice(0,3);})())'

start_session() {
  SID=$(bsk session start 2>&1 | tail -1 | grep -oE '[A-Za-z0-9]{4}' | tail -1)
  [ -z "$SID" ] && { echo "session 创建失败（bsk 未登录小红书？）"; exit 1; }
}

if [ "$CMD" = "list" ]; then
  INPUT="$2"; OUTDIR="${3:-.}"; mkdir -p "$OUTDIR"
  UID_X=$(printf '%s' "$INPUT" | grep -oE 'profile/[0-9a-f]+' | sed 's|profile/||' | head -1)
  [ -z "$UID_X" ] && UID_X="$INPUT"
  echo "=== 抓小红书主页作品列表: user=$UID_X ==="
  start_session
  bsk navigate "https://www.xiaohongshu.com/user/profile/$UID_X" --session "$SID" --wait-until domcontentloaded --timeout 30000 >/dev/null 2>&1
  sleep 8
  SCROLL_JS='(()=>{window.scrollTo(0,999999);window.dispatchEvent(new Event("scroll"));return document.querySelectorAll("a[href*=\"/explore/\"],a[href*=\"/discovery/item/\"]").length;})()'
  prev=-1
  for i in $(seq 1 80); do
    bsk evaluate --session "$SID" "$SCROLL_JS" >/dev/null 2>&1
    sleep 2
    cnt=$(bsk evaluate --session "$SID" "document.querySelectorAll('a[href*=\"/explore/\"],a[href*=\"/discovery/item/\"]').length" 2>/dev/null | tail -1 | tr -dc '0-9')
    cnt=${cnt:-0}
    if [ "$cnt" = "$prev" ] && [ "$i" -gt 4 ]; then
      echo "懒加载收敛于 $cnt 条（第 $i 轮）"; break
    fi
    prev=$cnt
  done
  sleep 2
  bsk evaluate --session "$SID" "$EXTRACT_LIST_JS" 2>/dev/null | tail -1 > "$OUTDIR/list.json"
  bsk session stop "$SID" >/dev/null 2>&1
  PY_BIN="${PY_BIN:-python3}"
  "$PY_BIN" - "$OUTDIR/list.json" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    print(f"✅ 抓到 {len(data)} 条笔记 → {sys.argv[1]}")
except Exception as e:
    print(f"❌ list.json 无效: {e}（可能触发了登录墙/验证码，需人工过一次）")
    sys.exit(1)
PY

elif [ "$CMD" = "note" ]; then
  NID="$2"; OUT="$3"; mkdir -p "$(dirname "$OUT")"
  start_session
  bsk navigate "https://www.xiaohongshu.com/explore/$NID" --session "$SID" --wait-until domcontentloaded --timeout 30000 >/dev/null 2>&1
  sleep 6
  RAW=$(bsk evaluate --session "$SID" "$EXTRACT_NOTE_JS" 2>/dev/null | tail -1)
  bsk session stop "$SID" >/dev/null 2>&1

  PY_BIN="${PY_BIN:-python3}"
  "$PY_BIN" - "$NID" "$OUT" <<PYEOF
import json, sys
from datetime import datetime, timezone, timedelta
nid, out = sys.argv[1], sys.argv[2]
item = {"id": nid, "url": f"https://www.xiaohongshu.com/explore/{nid}"}
try:
    hits = json.loads('''$RAW''')
except Exception:
    hits = []
best = None
for h in hits:
    best = h
    if str(h.get("id")) == nid:
        break
if best:
    desc = (best.get("desc") or "").strip()
    item["content"] = desc
    item["title"] = (best.get("title") or desc.splitlines()[0][:60] if desc else "").strip()
    t = best.get("time")
    if isinstance(t, (int, float)):
        if t > 1e12: t /= 1000.0
        item["publish_date"] = datetime.fromtimestamp(t, timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    ii = best.get("interactInfo") or {}
    item["metrics"] = {k: ii.get(k) for k in ("likedCount","collectedCount","commentCount","shareCount")}
    item["_source"] = "INITIAL_STATE"
else:
    item["_source"] = "none"
json.dump(item, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(("✅ " if best else "⚠️ 未命中(需校准JS/可能验证墙) ") + out)
sys.exit(0 if best else 3)
PYEOF
else
  echo "用法: bash grab_xhs.sh list|note ..."
  exit 2
fi
