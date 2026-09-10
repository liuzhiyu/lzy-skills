#!/bin/bash
# lzy-skills 发布前校验：frontmatter / 脚本语法 / VERSION / 路由一致性
# 用法：bash validate.sh [仓库根目录]   （默认校验本脚本所在仓库的 skills/）
set -uo pipefail
BASE="$(cd "$(dirname "$0")" && pwd)"
SK="${1:-$BASE}/skills"
FAIL=0

for d in "$SK"/lzy "$SK"/lzy-*; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"

  # 1. 主版本号：只有入口 lzy 有 VERSION；其他子技能不应有
  if [ "$name" = "lzy" ]; then
    v="$(tr -d '[:space:]' < "$d/VERSION" 2>/dev/null || true)"
    if ! printf '%s' "$v" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
      echo "❌ lzy: 主版本号 VERSION 缺失或格式错（got: '$v'）"; FAIL=$((FAIL+1))
    fi
  elif [ -f "$d/VERSION" ]; then
    echo "⚠️  $name: 不应再有独立 VERSION（主版本号统一在 lzy/VERSION）——请删除该文件"
  fi

  # 2. SKILL.md 存在且 frontmatter name == 目录名
  if [ ! -f "$d/SKILL.md" ]; then
    echo "❌ $name: 缺 SKILL.md"; FAIL=$((FAIL+1))
  elif ! head -20 "$d/SKILL.md" | grep -q "^name: $name$"; then
    echo "❌ $name: SKILL.md frontmatter name 与目录名不一致"; FAIL=$((FAIL+1))
  fi

  # 3. bash 脚本语法
  for s in "$d"/scripts/*.sh; do
    [ -f "$s" ] || continue
    if ! bash -n "$s" 2>/dev/null; then
      echo "❌ $name: bash 语法错误 -> $(basename "$s")"; FAIL=$((FAIL+1))
    fi
  done

  # 4. python 脚本语法（ast 解析，不写 pyc）
  for s in "$d"/scripts/*.py; do
    [ -f "$s" ] || continue
    if ! python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$s" 2>/dev/null; then
      echo "❌ $name: python 语法错误 -> $(basename "$s")"; FAIL=$((FAIL+1))
    fi
  done

  # 5. 版本检查脚本必备
  [ -f "$d/scripts/check_update.sh" ] || { echo "❌ $name: 缺 scripts/check_update.sh"; FAIL=$((FAIL+1)); }
done

# 6. 入口路由表引用的技能都必须存在（排除仓库名自身）
for ref in $(grep -o '/lzy-[a-z-]*' "$SK/lzy/SKILL.md" 2>/dev/null | sort -u); do
  r="${ref#/}"
  case "$r" in lzy-skills|lzy-) continue ;; esac
  [ -d "$SK/$r" ] || { echo "❌ 路由表引用了不存在的技能: $r"; FAIL=$((FAIL+1)); }
done

# 7. 每个 lzy-* 子技能都应出现在入口 SKILL.md 中（只警告）
for d in "$SK"/lzy-*; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  grep -q "$name" "$SK/lzy/SKILL.md" 2>/dev/null || echo "⚠️  $name 未出现在入口 SKILL.md 中（路由表/用法说明需回填）"
done

# 8. CHANGELOG.md 必须存在且含今天的条目（无当日条目时警告）
if [ ! -s "$BASE/CHANGELOG.md" ]; then
  echo "❌ CHANGELOG.md 缺失——发布前必须记录本次改动"; FAIL=$((FAIL+1))
elif ! grep -q "$(date +%Y-%m-%d)" "$BASE/CHANGELOG.md"; then
  echo "⚠️  CHANGELOG.md 没有今天的条目——若本次有技能版本变化，先补一节再发布"
fi

if [ "$FAIL" -eq 0 ]; then echo "✅ 全部校验通过"; else echo "⛔ 共 $FAIL 处问题，禁止发布"; fi
exit "$FAIL"
