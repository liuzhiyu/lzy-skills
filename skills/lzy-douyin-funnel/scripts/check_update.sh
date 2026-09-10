#!/bin/bash
# lzy 技能集版本检查：对比本地 VERSION 与 GitHub 远端 VERSION
# 用法：bash scripts/check_update.sh（自动从所在目录推断技能名）
# 静默原则：无更新/无网络/异常 → 不输出；有更新 → 输出一行 UPDATE_AVAILABLE
# 私有仓库兼容：本机存在 ~/.workbuddy/.lzy-github-token 时带认证请求
set -u
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"
NAME="$(basename "$SKILL_DIR")"
VERSION_FILE="$SKILL_DIR/VERSION"
[ -f "$VERSION_FILE" ] || exit 0

# 每天只联网查一次（stamp 记在 /tmp）
STAMP="/tmp/lzy-vercheck-$NAME"
TODAY="$(date +%Y-%m-%d)"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$TODAY" ]; then exit 0; fi
echo "$TODAY" > "$STAMP" 2>/dev/null

OWNER="liuzhiyu"
REPO="lzy-skills"
URL="https://raw.githubusercontent.com/$OWNER/$REPO/main/skills/$NAME/VERSION"
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
