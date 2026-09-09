#!/bin/bash
# 批量抓取抖音视频 v3：currentSrc 轮询 + 自动重试 + 可选 BGM 识别
#
# 用法：
#   bash batch_grab.sh <视频ID1> [视频ID2 ...]
#
# 环境变量（可选）：
#   WORKDIR   工作目录（默认当前目录），产物写入此处
#   DOMAIN    Whisper 转写行业词库（默认 health，多个用逗号，如 health,drug）
#   DO_BGM    设为 1 时，抓完后对全部成功视频批量做 CLAP BGM 识别（输出 bgm.json）
#
# 依赖：
#   bsk (BrowserSkill，需已登录抖音)、ffmpeg、curl、
#   video-to-text skill 的 venv（提供 mlx_whisper 转写）
set -u

WORKDIR="${WORKDIR:-.}"
DOMAIN="${DOMAIN:-health}"
DO_BGM="${DO_BGM:-0}"
cd "$WORKDIR"

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${V2T_VENV:-$HOME/.workbuddy/skills/video-to-text/.venv/bin/python}"
TS="${V2T_TS:-$HOME/.workbuddy/skills/video-to-text/scripts/transcribe.py}"
BGM_SCRIPT="$SKILL_ROOT/scripts/classify_bgm.py"

grab_one() {
  local ID="$1"
  local SID="$2"
  bsk navigate "https://www.douyin.com/video/$ID" --session "$SID" --wait-until domcontentloaded --timeout 30000 >/dev/null 2>&1

  # 轮询 currentSrc，最多 20 秒
  local URL=""
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 2
    URL=$(bsk evaluate --session "$SID" "(document.querySelector('video')?.currentSrc||'')" 2>/dev/null | tr -d '\n' | tr -d ' ')
    if [ ${#URL} -gt 100 ]; then
      break
    fi
  done

  if [ -z "$URL" ] || [ ${#URL} -lt 100 ]; then
    echo "[$ID] 抓不到直链（最终URL长度: ${#URL}）"
    return 1
  fi

  # 下载：失败重试
  local ok=0
  for r in 1 2 3; do
    curl -s -L --max-time 180 --http1.1 -f \
      -H "User-Agent: $UA" -H "Referer: https://www.douyin.com/" \
      -o "v_$ID.mp4" "$URL" && [ -s "v_$ID.mp4" ] && { ok=1; break; }
    rm -f "v_$ID.mp4"
    sleep 1
  done
  if [ $ok -ne 1 ]; then
    echo "[$ID] 下载失败"
    return 1
  fi
  echo "[$ID] 下载: $(du -h v_$ID.mp4 | cut -f1)"

  # 抽帧
  mkdir -p "frames_$ID"
  ffmpeg -v error -y -t 6 -i "v_$ID.mp4" -vf "fps=2,scale=540:-1" -q:v 3 -start_number 0 "frames_$ID/a_%02d.jpg" 2>/dev/null
  ffmpeg -v error -y -ss 6 -i "v_$ID.mp4" -vf "fps=0.5,scale=540:-1" -q:v 3 -start_number 0 "frames_$ID/b_%02d.jpg" 2>/dev/null
  local fc=$(ls frames_$ID 2>/dev/null | wc -l | tr -d ' ')
  echo "[$ID] 抽帧: $fc"

  # 转写
  "$PY" "$TS" --input "v_$ID.mp4" --output "script_$ID.txt" --language zh --timestamps --domain "$DOMAIN" 2>&1 | grep -E "完成 ->|失败|错误" | tail -1
  return 0
}

SUCCESS_IDS=()
for ID in "$@"; do
  echo "===== [$ID] 开始 ====="
  if [ -f "script_$ID.txt" ]; then
    echo "[$ID] 已有转写，跳过"
    SUCCESS_IDS+=("$ID")
    continue
  fi

  local_success=0
  for attempt in 1 2 3; do
    SID=$(bsk session start 2>&1 | tail -1 | grep -oE '[A-Za-z0-9]{4}' | tail -1)
    if [ -z "$SID" ]; then
      echo "[$ID] session 创建失败"
      sleep 2
      continue
    fi
    if grab_one "$ID" "$SID"; then
      local_success=1
      SUCCESS_IDS+=("$ID")
      bsk session stop "$SID" >/dev/null 2>&1
      break
    fi
    bsk session stop "$SID" >/dev/null 2>&1
    sleep 3
  done
  echo "===== [$ID] $([ $local_success -eq 1 ] && echo 成功 || echo 失败) ====="
done

# 可选 BGM 识别（CLAP，模型一次加载批量处理）
if [ "$DO_BGM" = "1" ] && [ ${#SUCCESS_IDS[@]} -gt 0 ]; then
  echo ""
  echo "===== BGM 识别（CLAP）====="
  VIDS=""
  for ID in "${SUCCESS_IDS[@]}"; do
    [ -f "v_$ID.mp4" ] && VIDS="$VIDS --video v_$ID.mp4"
  done
  if [ -n "$VIDS" ]; then
    "$PY" "$BGM_SCRIPT" $VIDS --json bgm.json --top 3
  fi
fi

echo "ALL DONE"
