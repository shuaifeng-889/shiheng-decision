#!/usr/bin/env bash
# 史衡 · 五链决策模型 —— 一键安装到 Agent skills 目录
#
# 用法：
#   ./install.sh              # 装到默认位置 ~/.workbuddy/skills/shiheng-decision
#   ./install.sh --copy       # 复制而不是软链接（跨盘或不支持符号链接时用）
#   ./install.sh --target DIR # 装到指定目录
#
# 这个脚本只做三件事：检查环境、把本目录放到 skills 路径下、跑一次自检。
# 不修改任何已有文件，不删除任何东西。

set -euo pipefail

NAME="shiheng-decision"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="link"
TARGET=""

while [ $# -gt 0 ]; do
  case "$1" in
    --copy)   MODE="copy"; shift ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

# ---- 1. 找 Python ----------------------------------------------------------
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>/dev/null; then
      PY="$cand"; break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "错误：找不到 Python 3.8 或更高版本。" >&2
  echo "      本项目的全部功能都依赖 Python，请先安装：https://www.python.org/downloads/" >&2
  exit 1
fi

echo "Python  ：$($PY --version 2>&1)"
echo "源目录  ：$SRC"

# ---- 2. 确定安装位置 --------------------------------------------------------
if [ -z "$TARGET" ]; then
  TARGET="${HOME}/.workbuddy/skills/${NAME}"
fi
echo "安装到  ：$TARGET"

if [ "$SRC" = "$(cd "$(dirname "$TARGET")" 2>/dev/null && pwd)/$(basename "$TARGET")" ] 2>/dev/null; then
  echo "提示：源目录与目标目录相同，无需安装。"
  exit 0
fi

if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  echo ""
  echo "目标已存在：$TARGET"
  printf "覆盖它吗？已有的改动会丢失（建议先备份）。[y/N] "
  read -r ans
  case "$ans" in
    y|Y|yes|YES) rm -rf "$TARGET" ;;
    *) echo "已取消，未做任何改动。"; exit 0 ;;
  esac
fi

mkdir -p "$(dirname "$TARGET")"

# ---- 3. 软链接或复制 --------------------------------------------------------
if [ "$MODE" = "link" ]; then
  if ln -s "$SRC" "$TARGET" 2>/dev/null; then
    echo "已创建软链接。之后在源目录的改动会立即生效。"
  else
    echo "软链接失败（可能是跨文件系统或权限限制），改为复制。"
    MODE="copy"
  fi
fi

if [ "$MODE" = "copy" ]; then
  cp -R "$SRC" "$TARGET"
  echo "已复制全部文件。"
fi

# ---- 4. 自检 ---------------------------------------------------------------
echo ""
echo "运行自检……"
if "$PY" "$SRC/scripts/cli.py" validate >/dev/null 2>&1; then
  echo "自检通过：数据完整，命令行可用。"
else
  echo "自检失败。请手动运行排查：" >&2
  echo "  $PY $SRC/scripts/cli.py validate" >&2
  exit 1
fi

# ---- 5. 提示 ---------------------------------------------------------------
cat <<EOF

安装完成。

在终端里用（不需要任何 Agent）：

  $PY $TARGET/scripts/cli.py decide --interactive
  $PY $TARGET/scripts/cli.py cases --search 粮道

想少敲路径，把这行加进 ~/.bashrc 或 ~/.zshrc：

  alias shiheng='$PY $TARGET/scripts/cli.py'

在用支持 SKILL.md 的 Agent 时，它会自动读取 $TARGET/SKILL.md。

教程在 $TARGET/tutorial/ ，从 01-install.md 开始读。
EOF
