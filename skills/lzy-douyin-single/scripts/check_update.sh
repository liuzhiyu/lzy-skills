#!/bin/bash
# lzy 技能集版本检查：单一主版本号（存于 lzy 入口的 VERSION，全部子技能共用）
# 对比本地主版本 与 GitHub 远端 skills/lzy/VERSION；不同 → 输出 UPDATE_AVAILABLE
# 静默原则：无更新/无网络/异常 → 不输出
set -u
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"
NAME="$(basename "$SKILL_DIR")"

# 本地主版本：入口技能自己就是 lzy/VERSION；子技能读相邻的 lzy/VERSION
if [ "$NAME" = "lzy" ]; then
  VERSION_FILE="$SKILL_DIR/VERSION"
else
  VERSION_FILE="$SKILL_DIR/../lzy/VERSION"
fi
[ -f "$VERSION_FILE" ] || exit 0

# 每天只联网查一次（stamp 记在 /tmp）
STAMP="/tmp/lzy-vercheck-$NAME"
TODAY="$(date +%Y-%m-%d)"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$TODAY" ]; then exit 0; fi
echo "$TODAY" > "$STAMP" 2>/dev/null

OWNER="liuzhiyu"
REPO="lzy-skills"
URL="https://raw.githubusercontent.com/$OWNER/$REPO/main/skills/lzy/VERSION"
TOKEN_FILE="$HOME/.workbuddy/.lzy-github-token"
REMOTE=""

if [ -f "$TOKEN_FILE" ] && [ -s "$TOKEN_FILE" ]; then
  TOKEN="$(cat "$TOKEN_FILE")"
  REMOTE=$(curl -fsS --max-time 4 -H "Authorization: token $TOKEN" "$URL" 2>/dev/null | tr -d '[:space:]')
else
  REMOTE=$(curl -fsS --max-time 4 "$URL" 2>/dev/null | tr -d '[:space:]')
fi
[ -z "$REMOTE" ] && exit 0

LOCAL="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [ "$REMOTE" != "$LOCAL" ]; then
  echo "UPDATE_AVAILABLE 当前=$LOCAL 远端=${REMOTE}（GitHub: $OWNER/${REPO}，可让 AI 同步更新或重跑 install.sh）"
fi
exit 0
