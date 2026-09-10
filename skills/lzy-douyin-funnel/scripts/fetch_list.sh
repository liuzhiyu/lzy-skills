#!/bin/bash
# 抓取抖音搜索结果列表（视频 tab）
# 用法: ./fetch_list.sh <关键词> <session> <outdir> [目标条数，默认 130]
set -u
KW=$1
SESS=$2
OUTDIR=$3
TARGET=${4:-130}
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUTDIR"
KWENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$KW")
URL="https://www.douyin.com/search/${KWENC}?type=video"

echo "navigate: $URL"
bsk navigate "$URL" --session "$SESS" --wait-until commit --timeout 30 >/dev/null 2>&1
sleep 5

# 滚动加载，直到条数不增长或达到目标
bsk evaluate --session "$SESS" --timeout 180s "(async()=>{ const sleep=ms=>new Promise(r=>setTimeout(r,ms)); let last=0,stall=0; for(let i=0;i<40;i++){ window.scrollBy(0,1200); await sleep(1100); const n=document.querySelectorAll('li div.search-result-card').length; if(n>last){last=n;stall=0;} else {stall++; if(stall>=5) break;} if(n>=$TARGET) break;} return {n:last}; })()" 2>&1 | tail -2

# 抽取卡片
bsk evaluate --session "$SESS" --timeout 60s '(() => { const cards=[...document.querySelectorAll("li div.search-result-card")]; const out=[]; const seen=new Set(); for(const c of cards){ const a=c.querySelector("a[href*=\"/video/\"]"); if(!a) continue; const m=(a.getAttribute("href")||"").match(/\/video\/(\d+)/); if(!m) continue; if(seen.has(m[1])) continue; seen.add(m[1]); out.push({id:m[1], lines:(c.innerText||"").split("\n").map(s=>s.trim()).filter(Boolean)}); } return out; })()' > "$OUTDIR/raw.json" 2>/dev/null

echo "raw saved: $OUTDIR/raw.json"
python3 "$SKILL_DIR/parse_list.py" "$OUTDIR/raw.json" "$OUTDIR/list.json"
