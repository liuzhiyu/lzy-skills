#!/bin/bash
# 抓单条抖音视频：页面指标(带抓取时间戳) + 视频文案 + 作者 + 前排评论 + 视频下载 + 抽帧
# 用法: bash grab_one.sh <抖音URL或video_id> <工作目录>
# 产出: <工作目录>/data.json  <工作目录>/v_<ID>.mp4  <工作目录>/frames_<ID>/a_XX.jpg,b_XX.jpg
#
# 设计要点（2026-09-29 首版）：
#   - 指标全部从渲染后 DOM 读（RENDER_DATA 已不含 aweme detail，见 lzy-account-archive 踩坑）
#   - 视频流读 video.currentSrc（100% 命中，比 network 嗅探稳），带签名有时效，拿到立刻下载
#   - 所有指标必须带 captured_at 抓取时刻——抖音数字是活的，脱离时间的指标没有分析价值
#   - 任何一段抓不到都只降级不中断，字段留 null，绝不编数
set -u

BSK="${BSK_BIN:-$HOME/.local/bin/bsk}"
FFMPEG="${FFMPEG_BIN:-ffmpeg}"
IN="$1"
WORKDIR="${2:-.}"
mkdir -p "$WORKDIR"

# --- 从 URL / 纯 id / 短链 提取 video_id ---
VID="$(printf '%s' "$IN" | grep -oE '/video/[0-9]+' | grep -oE '[0-9]+' | head -1)"
if [ -z "$VID" ]; then
  VID="$(printf '%s' "$IN" | grep -oE '^[0-9]{15,25}$' | head -1)"
fi
PAGE_URL="$IN"
if [ -n "$VID" ]; then PAGE_URL="https://www.douyin.com/video/$VID"; fi

if ! command -v "$BSK" >/dev/null 2>&1; then
  echo "❌ 未找到 bsk（BrowserSkill CLI）。预期路径 $BSK，可用 BSK_BIN 覆盖。"
  echo "   安装：安装 BrowserSkill 技能后重启终端；或 export BSK_BIN=/path/to/bsk"
  exit 1
fi

SID=$("$BSK" session start 2>&1 | tail -1 | grep -oE '[A-Za-z0-9]{4,}' | tail -1)
if [ -z "$SID" ]; then echo "❌ bsk session 创建失败（daemon 没起？跑 bsk daemon start）"; exit 1; fi

"$BSK" navigate "$PAGE_URL" --session "$SID" --wait-until domcontentloaded --timeout 30000 >/dev/null 2>&1
sleep 7

EXTRACT_JS=$(cat <<'JSEOF'
JSON.stringify((()=>{
  const q=s=>{try{const e=document.querySelector('[data-e2e="'+s+'"]');return e?(e.innerText||'').trim():'';}catch(e){return '';}};
  const t1=s=>{try{const e=document.querySelector(s);return e?(e.innerText||'').trim():'';}catch(e){return '';}};
  const wrap=document.querySelector('[data-e2e="detail-video-info"]');
  let desc='';
  if(wrap&&wrap.children&&wrap.children[0]){
    desc=(wrap.children[0].innerText||'').replace(/^\s*(展开|收起)\s*/,'').trim();
  }
  const dt=(document.title||'').replace(/\s*[-\u2013]\s*抖音\s*$/,'').trim();
  if(dt.length>desc.length) desc=dt;
  const v=document.querySelector('video');
  // 前排评论：宽容抓取，抓不到就是空数组
  let comments=[];
  try{
    const nodes=document.querySelectorAll('[data-e2e="comment-list"] [data-e2e^="comment-item"], [data-e2e="comment-item"], [data-e2e="comment-list"] .comment-item');
    nodes.forEach(n=>{
      if(comments.length>=15) return;
      const s=(n.innerText||'').trim().split(/\n+/).filter(Boolean);
      if(s.length) comments.push(s.slice(0,3).join(' | ').slice(0,200));
    });
  }catch(e){}
  return {
    id:(location.pathname.split('/video/')[1]||'').split('?')[0],
    url:location.href,
    desc:desc,
    ptime:q('detail-video-publish-time'),
    digg:q('video-player-digg'),
    comment:q('feed-comment-icon'),
    collect:q('video-player-collect'),
    share:q('video-player-share'),
    author: t1('[data-e2e="video-player-nickname"]') || t1('[data-e2e="live-room-nickname"]') || t1('.author-info .nickname') || '',
    fans: t1('[data-e2e="video-author-fans"]') || '',
    src:(v&&v.currentSrc)?v.currentSrc:'',
    dur:(v&&isFinite(v.duration)&&v.duration>0)?v.duration:null,
    comments:comments
  };
})())
JSEOF
)

RAW=$("$BSK" evaluate --session "$SID" "$EXTRACT_JS" 2>/dev/null | tail -1)

# --- 下载视频流（拿到直链立刻下，签名有时效） ---
SRC="$(printf '%s' "$RAW" | python3 -c "import sys,json,re
try:
    s=sys.stdin.read()
    m=re.search(r'\{.*\}', s, re.S)
    d=json.loads(m.group(0)) if m else {}
    print(d.get('src') or '')
except Exception:
    print('')" 2>/dev/null)"

MP4="$WORKDIR/v_${VID:-unknown}.mp4"
if [ -n "$SRC" ]; then
  curl -fsSL --retry 3 --max-time 180 \
    -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" \
    -H "Referer: https://www.douyin.com/" \
    -o "$MP4" "$SRC" 2>/dev/null
  if [ ! -s "$MP4" ]; then echo "⚠️ 视频下载失败（直链可能过期）"; rm -f "$MP4"; MP4=""; fi
else
  echo "⚠️ 未取到视频流直链（未登录抖音？）"
  MP4=""
fi

"$BSK" session stop "$SID" >/dev/null 2>&1

# --- 抽帧：0-6s 每 0.5s（看钩子），6s 后每 2s（看结构） ---
FRAMES=""
if [ -n "$MP4" ] && command -v "$FFMPEG" >/dev/null 2>&1; then
  FRAMES="$WORKDIR/frames_${VID:-unknown}"
  mkdir -p "$FRAMES"
  "$FFMPEG" -y -loglevel error -i "$MP4" -vf "fps=2,scale=540:-1" -frames:v 12 "$FRAMES/a_%02d.jpg" 2>/dev/null
  "$FFMPEG" -y -loglevel error -ss 6 -i "$MP4" -vf "fps=0.5,scale=540:-1" -frames:v 10 "$FRAMES/b_%02d.jpg" 2>/dev/null
  [ -z "$(ls -A "$FRAMES" 2>/dev/null)" ] && FRAMES=""
fi

# --- 归一化 + 派生指标 + 写 data.json ---
export WORKDIR MP4 FRAMES VID
python3 - "$RAW" <<'PYEOF'
import json, os, re, sys
from datetime import datetime, timezone, timedelta

raw = sys.argv[1]
workdir = os.environ.get("WORKDIR", ".")
mp4 = os.environ.get("MP4", "")
frames = os.environ.get("FRAMES", "")
vid = os.environ.get("VID", "")
out = os.path.join(workdir, "data.json")

try:
    m = re.search(r"\{.*\}", raw, re.S)
    d = json.loads(m.group(0)) if m else {}
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}

TZ = timezone(timedelta(hours=8))
now = datetime.now(TZ)
vid = d.get("id") or vid or "unknown"

def parse_num(s):
    """'1.1万' -> 11000；'3.5w' -> 35000；'1,234' -> 1234"""
    if s is None: return None
    s = str(s).strip().replace(",", "")
    if not s: return None
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([万wW千kK亿]?)$", s)
    if not m:
        m2 = re.search(r"[0-9]*\.?[0-9]+", s)
        return int(float(m2.group(0))) if m2 else None
    n = float(m.group(1)); u = m.group(2)
    mult = {"万": 1e4, "w": 1e4, "W": 1e4, "亿": 1e8, "千": 1e3, "k": 1e3, "K": 1e3}.get(u, 1)
    return int(round(n * mult))

item = {
    "video_id": vid,
    "url": d.get("url") or f"https://www.douyin.com/video/{vid}",
    "captured_at": now.isoformat(timespec="seconds"),
    "captured_at_human": now.strftime("%Y-%m-%d %H:%M:%S") + " (UTC+8)",
    "author": {"nickname": d.get("author") or None, "fans_raw": d.get("fans") or None, "fans": parse_num(d.get("fans"))},
    "content": (d.get("desc") or "").strip() or None,
    "publish_time_raw": d.get("ptime") or None,
    "duration_ms": int(round(float(d["dur"]) * 1000)) if isinstance(d.get("dur"), (int, float)) and d.get("dur") else None,
    "metrics_raw": {"likes": d.get("digg"), "comments": d.get("comment"), "collects": d.get("collect"), "shares": d.get("share")},
    "top_comments": d.get("comments") or [],
    "files": {"video": os.path.abspath(mp4) if mp4 and os.path.exists(mp4) else None,
              "frames_dir": os.path.abspath(frames) if frames and os.path.isdir(frames) else None},
}

# 发布时间归一化
pt = d.get("ptime") or ""
m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[\sT]*(\d{1,2})?:?(\d{2})?)?", pt)
if m:
    y, mo, dd = m.group(1), int(m.group(2)), int(m.group(3))
    hh = int(m.group(4) or 0); mi = m.group(5) or "00"
    item["publish_time"] = f"{y}-{mo:02d}-{dd:02d} {hh:02d}:{mi}"
    try:
        pub = datetime(int(y), mo, dd, hh, int(mi), tzinfo=TZ)
        item["age_days"] = max(round((now - pub).total_seconds() / 86400, 2), 0.01)
    except Exception:
        item["age_days"] = None
else:
    item["publish_time"] = None
    item["age_days"] = None

# 指标归一化 + 派生
mt = {k: parse_num(v) for k, v in item["metrics_raw"].items()}
item["metrics"] = mt
likes = mt.get("likes")
der = {}
if isinstance(likes, int) and likes > 0:
    for k in ("comments", "collects", "shares"):
        v = mt.get(k)
        der[f"{k[:-1] if k.endswith('s') else k}_per_like"] = round(v / likes, 4) if isinstance(v, int) else None
    der["engagement_total"] = sum(v for v in mt.values() if isinstance(v, int))
if isinstance(item.get("age_days"), float) and isinstance(likes, int):
    der["likes_per_day"] = round(likes / item["age_days"], 1)
item["derived"] = der

json.dump(item, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

ok = bool(item["content"]) or bool(likes)
print(("✅ " if ok else "⚠️ 抓取不完整 ") + os.path.abspath(out))
print(f"   抓取时刻 {item['captured_at_human']} | 赞 {mt.get('likes')} 评 {mt.get('comments')} 藏 {mt.get('collects')} 转 {mt.get('shares')}")
if item["files"]["video"]: print(f"   视频 {item['files']['video']}")
if item["files"]["frames_dir"]: print(f"   帧图 {item['files']['frames_dir']}")
sys.exit(0 if ok else 3)
PYEOF
