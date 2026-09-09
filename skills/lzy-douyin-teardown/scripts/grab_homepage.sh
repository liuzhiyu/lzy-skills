#!/bin/bash
# 抓取抖音账号主页完整作品列表（含滚动懒加载），输出 all_videos.json
# 用法: bash grab_homepage.sh <主页URL或sec_uid> [输出目录]
# 主页URL示例: https://www.douyin.com/user/MS4wLjABAAAA...
set -u

INPUT="$1"
OUTDIR="${2:-.}"
mkdir -p "$OUTDIR"

# 提取 sec_uid：从 URL 里截 user/ 后面的部分；若本身就是 sec_uid 则直接用
SEC_UID=$(printf '%s' "$INPUT" | grep -oE 'user/[A-Za-z0-9_-]+' | sed 's|user/||' | head -1)
[ -z "$SEC_UID" ] && SEC_UID="$INPUT"

echo "=== 抓主页作品列表: sec_uid=$SEC_UID ==="

SID=$(bsk session start 2>&1 | tail -1 | grep -oE '[A-Za-z0-9]{4}' | tail -1)
if [ -z "$SID" ]; then echo "session 创建失败"; exit 1; fi
echo "SID=$SID"

bsk navigate "https://www.douyin.com/user/$SEC_UID" --session "$SID" --wait-until domcontentloaded --timeout 30000 >/dev/null 2>&1
sleep 8

# 滚动容器查找 + 滚动（抖音主容器是 .parent-route-container，但 class 可能变，动态找 scrollHeight 最大的 div）
SCROLL_JS='(()=>{let best=null,bestSh=0;for(const c of document.querySelectorAll("div")){try{const sh=c.scrollHeight,ch=c.clientHeight;if(sh>ch+200&&sh>bestSh){bestSh=sh;best=c;}}catch(e){}}if(best){best.scrollTop=99999;best.dispatchEvent(new Event("scroll"));}window.dispatchEvent(new Event("scroll"));return bestSh;})()'

prev=-1
for i in $(seq 1 50); do
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

# 提取作品列表 JSON
EXTRACT_JS='JSON.stringify(Array.from(document.querySelectorAll("ul li")).filter(li=>li.querySelector("a[href*=\"/video/\"]")).map(li=>{const a=li.querySelector("a[href*=\"/video/\"]");const img=li.querySelector("img");const spans=Array.from(li.querySelectorAll("span")).map(s=>s.innerText.trim()).filter(t=>t&&/^[\d.]+万?$/.test(t));return {id:(a.href.match(/video\/(\d+)/)||[])[1]||"?",alt:(img?img.alt.slice(0,30):""),n:spans[0]||"?"}}))'

bsk evaluate --session "$SID" "$EXTRACT_JS" 2>/dev/null | tail -1 > "$OUTDIR/all_videos.json"

bsk session stop "$SID" >/dev/null 2>&1

# 校验 JSON 有效性（仅用标准库，任何 python3 均可）
PY_BIN="${PY_BIN:-python3}"
"$PY_BIN" - "$OUTDIR/all_videos.json" <<'PY'
import json,sys
p=sys.argv[1]
try:
    data=json.load(open(p))
    print(f"✅ 抓到 {len(data)} 条作品 → {p}")
    # 打印点赞分布概览
    def parse(n):
        if not n or n=='?': return 0
        return float(n.replace('万',''))*10000 if '万' in n else float(n)
    vals=sorted((parse(d['n']) for d in data), reverse=True)
    if vals:
        print(f"   最高赞 {vals[0]:.0f} / 最低赞 {vals[-1]:.0f}")
except Exception as e:
    print(f"❌ JSON 解析失败: {e}")
    print(open(p).read()[:300])
PY

echo "DONE"
