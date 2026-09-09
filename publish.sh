#!/bin/bash
# lzy-skills 发布：~/.claude/skills 是源，GitHub 是分发。所有 git 操作在 /tmp 完成。
# 用法：bash publish.sh "本次改动说明"
# 前提：~/.workbuddy/.lzy-github-token 存在且有效（repo 权限）
set -euo pipefail

SRC="$HOME/.claude/skills"
TOKEN_FILE="$HOME/.workbuddy/.lzy-github-token"
REPO="liuzhiyu/lzy-skills"
SELF="$(cd "$(dirname "$0")" && pwd)"
MSG="${1:-update lzy skills}"

[ -f "$TOKEN_FILE" ] && [ -s "$TOKEN_FILE" ] || { echo "❌ 缺少 token：$TOKEN_FILE（需重新走设备码授权）"; exit 1; }
[ -d "$SRC/lzy" ] || { echo "❌ 找不到源技能目录 $SRC/lzy"; exit 1; }

WORK="$(mktemp -d /tmp/lzy-publish.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

echo "→ clone 仓库到 $WORK"
git clone -q "https://x-access-token:$(cat "$TOKEN_FILE")@github.com/$REPO.git" "$WORK/repo"
cd "$WORK/repo"
git remote set-url origin "https://github.com/$REPO.git"   # 去掉 URL 里的 token
git config user.name "liuzhiyu"
git config user.email "liuzhiyu@gmail.com"

echo "→ 同步 ~/.claude/skills/lzy* → skills/"
mkdir -p skills
for d in "$SRC"/lzy "$SRC"/lzy-*; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  mkdir -p "skills/$name"
  rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude '.DS_Store' "$d/" "skills/$name/"
done

# 工具脚本与文档以本地镜像为准，一并发布
for f in validate.sh install.sh publish.sh README.md .gitignore; do
  [ -f "$SELF/$f" ] && cp "$SELF/$f" "$WORK/repo/$f"
done

echo "→ 校验"
bash "$SELF/validate.sh" "$WORK/repo"

git add -A
if git diff --cached --quiet; then
  echo "ℹ️  没有变更，无需发布"
  exit 0
fi

git commit -q -m "$MSG"
echo "→ push 到 GitHub"
git push -q origin HEAD:main

echo "→ 验证远端（防显示异常）"
LOCAL_SHA="$(git rev-parse --short HEAD)"
REMOTE_SHA="$(git ls-remote -q origin refs/heads/main | cut -c1-7)"
echo "   本地 HEAD：$LOCAL_SHA  远端 HEAD：$REMOTE_SHA"
if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
  echo "❌ 远端与本地不一致，推送可能失败，请检查"
  exit 1
fi

echo "✅ 已发布：$REPO"
echo "   提交说明：$MSG"
