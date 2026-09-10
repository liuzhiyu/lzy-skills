#!/bin/bash
# 抓抖音账号主页作品列表（滚动懒加载，复用 lzy-douyin-teardown 验证过的逻辑）
# 用法: bash grab_douyin_list.sh <主页URL或sec_uid> <输出目录>
# 输出: <输出目录>/list.json   [{id, alt, n}...]（n 为主页展示的点赞数，仅供粗排）
set -u

INPUT="$1"
OUTDIR="${2:-.}"
mkdir -p "$OUTDIR"

SEC_UID=$(printf '%s' "$INPUT" | grep -oE 'user/[A-Za-z0-9_-]+' | sed 's|user/||' | head -1)
[ -z "$SEC_UID" ] && SEC_UID="$INPUT"

echo "=== 抓主页作品列表: sec_uid=$SEC_UID ==="

SID=$(bsk session start 2>&1 | tail -1 | grep -oE '[A-Za-z0-9]{4}' | tail -1)
if [ -z "$SID" ]; then echo "session 创建失败（bsk 未登录抖音？）"; exit 1; fi
echo "SID=$SID"

bsk navigate "https://www.douyin.com/user/$SEC_UID" --session "$SID" --wait-until domcontentloaded --timeout 30000 >/dev/null 2>&1
sleep 8

SCROLL_JS='(()=>{let best=null,bestSh=0;for(const c of document.querySelectorAll("div")){try{const sh=c.scrollHeight,ch=c.clientHeight;if(sh>ch+200&&sh>bestSh){bestSh=sh;best=c;}}catch(e){}}if(best){best.scrollTop=99999;best.dispatchEvent(new Event("scroll"));}window.dispatchEvent(new Event("scroll"));return bestSh;})()'

prev=-1
for i in $(seq 1 80); do
  bsk evaluate --session "$SID" "$SCROLL_JS" >/dev/null 2>&1
  sleep 2
  cnt=$(bsk evaluate --session "$SID" "document.querySelectorAll('a[href*=\"/video/\"]').length" 2>/dev/null | tail -1 | tr -dc '0-9')
  cnt=${cnt:-0}
  if [ "$cnt" = "$prev" ] && [ "$i" -gt 4 ]; then
    echo "懒加载收敛于 $cnt 条（第 $i 轮）"
    break
  fi
  prev=$cnt
done

sleep 2

EXTRACT_JS='JSON.stringify(Array.from(document.querySelectorAll("ul li")).filter(li=>li.querySelector("a[href*=\"/video/\"]")).map(li=>{const a=li.querySelector("a[href*=\"/video/\"]");const img=li.querySelector("img");const spans=Array.from(li.querySelectorAll("span")).map(s=>s.innerText.trim()).filter(t=>t&&/^[\d.]+万?$/.test(t));return {id:(a.href.match(/video\/(\d+)/)||[])[1]||"?",alt:(img?img.alt.slice(0,50):""),n:spans[0]||"?"}}))'

bsk evaluate --session "$SID" "$EXTRACT_JS" 2>/dev/null | tail -1 > "$OUTDIR/list.json"
bsk session stop "$SID" >/dev/null 2>&1

PY_BIN="${PY_BIN:-python3}"
"$PY_BIN" - "$OUTDIR/list.json" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    ids = [d for d in data if d.get("id") and d["id"] != "?"]
    print(f"✅ 抓到 {len(data)} 条（有效 id {len(ids)} 条）→ {sys.argv[1]}")
except Exception as e:
    print(f"❌ list.json 无效: {e}")
    sys.exit(1)
PY
