#!/usr/bin/env bash
# FinClaw collectorx 通用安装脚本：把 FinClaw 的采集器 skill 装到 ~/.agents/skills/<slug>/
# 任何 agent 都能执行（不依赖 FinClaw/DSH 运行时）。
# 用法:
#   bash install.sh <skill-slug>      例如: bash install.sh wechat-export
#   或一条命令: curl -sSL https://raw.githubusercontent.com/yannberg08/collectorx/main/install.sh | bash -s wechat-export
set -euo pipefail

SLUG="${1:-}"
if [ -z "$SLUG" ]; then
  echo "用法: $0 <skill-slug>   例如: $0 wechat-export" >&2
  exit 1
fi

REPO="yannberg08/collectorx"
BRANCH="main"
SKILLS_ROOT="${SOULMIRROR_HUB_SKILLS_ROOT:-$HOME/.agents/skills}"
DEST="$SKILLS_ROOT/$SLUG"

echo "FinClaw collectorx 安装: $SLUG  (来源 github.com/$REPO)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -sSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH" | tar -xz -C "$TMP"
SRC="$TMP/collectorx-$BRANCH/skills/$SLUG"
if [ ! -d "$SRC" ]; then
  echo "错误: skill [$SLUG] 不在 $REPO/skills/ 里。" >&2
  echo "可用 skill: https://github.com/$REPO/tree/$BRANCH/skills" >&2
  exit 1
fi

mkdir -p "$SKILLS_ROOT"
rm -rf "$DEST.tmp"
cp -R "$SRC" "$DEST.tmp"
rm -rf "$DEST"
mv "$DEST.tmp" "$DEST"
echo "已安装 $SLUG -> $DEST"