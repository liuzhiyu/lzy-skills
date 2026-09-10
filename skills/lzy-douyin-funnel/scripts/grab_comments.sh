#!/bin/bash
# 批量抓取抖音视频评论区
# 用法: ./grab_comments.sh <session> <idfile> <outdir>
#   session: bsk session id（必须已 start）
#   idfile : 每行一个视频 id
#   outdir : 输出目录（已存在的非空 json 会跳过，空文件会重试一次）
SESS=$1
IDFILE=$2
OUTDIR=$3
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
JS=$(cat "$SKILL_DIR/grab_comment.js")
mkdir -p "$OUTDIR"
n=0
while read id; do
  [ -z "$id" ] && continue
  if [ -s "$OUTDIR/$id.json" ]; then n=$((n+1)); continue; fi
  bsk navigate "https://www.douyin.com/video/$id" --session "$SESS" --wait-until commit --timeout 15 >/dev/null 2>&1
  bsk evaluate --session "$SESS" --timeout 100s "$JS" > "$OUTDIR/$id.json" 2>/dev/null
  if [ ! -s "$OUTDIR/$id.json" ]; then
    sleep 3
    bsk evaluate --session "$SESS" --timeout 100s "$JS" > "$OUTDIR/$id.json" 2>/dev/null
  fi
  sleep 1
  n=$((n+1))
  echo "[$SESS] $n done $id $(wc -c < "$OUTDIR/$id.json" | tr -d ' ') bytes"
done < "$IDFILE"
echo "[$SESS] ALL DONE"
