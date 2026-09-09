#!/bin/bash
# 安装/更新 lzy 技能集到 ~/.claude/skills/
# 用法：克隆仓库后  bash install.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/skills"
DST="$HOME/.claude/skills"
mkdir -p "$DST"

installed=0
for d in "$SRC"/lzy "$SRC"/lzy-*; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude '.DS_Store' "$d/" "$DST/$name/"
  echo "✅ 已安装 $name -> $DST/$name"
  installed=$((installed+1))
done
echo "完成，共 $installed 个技能。在 Claude Code 里输入 /lzy help 查看用法。"
