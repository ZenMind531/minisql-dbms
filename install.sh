#!/usr/bin/env bash
# MiniSQL 一键安装：自动准备环境 + 装测试依赖
# 用法：在 minisql-dbms 根目录执行  ./install.sh
# 目标：一条命令跑完。能自动处理的绝不让用户手动来。
set -e

cd "$(dirname "$0")"

echo "==> 检查 Python ..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "错误：找不到 python3，请先安装 Python 3.11+" >&2
    exit 1
fi
if ! python3 -c 'import sys; exit(sys.version_info < (3, 11))'; then
    echo "错误：需要 Python 3.11+，当前 $(python3 --version)" >&2
    exit 1
fi

echo "==> 准备虚拟环境 ..."
# .venv 已存在且完整可用（有 python 也有 pip）→ 直接用；否则删掉重建
if [ ! -x .venv/bin/python ] || [ ! -x .venv/bin/pip ]; then
    rm -rf .venv
    # 首次失败多半是缺 python3-venv 组件，自动安装后重试一次
    if ! python3 -m venv .venv 2>/dev/null; then
        echo "    创建失败，尝试安装 python3-venv（需要 sudo 密码）..."
        sudo apt-get install -y python3-venv
        rm -rf .venv
        python3 -m venv .venv
    fi
fi

echo "==> 安装测试依赖 ..."
./.venv/bin/pip install --quiet pytest

echo "==> 创建快捷命令 minidb ..."
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/minidb" <<EOF
#!/usr/bin/env bash
cd "$PROJECT_DIR" && exec ./.venv/bin/python -m database_system.cli.main
EOF
chmod +x "$HOME/.local/bin/minidb"

# ---- 成功动画：MiniDB 大字 logo 逐行点亮（树莓派风格）----
green=$'\033[32m'; bold=$'\033[1m'; reset=$'\033[0m'

echo ""
# 五行 logo 一行一色（红→黄→绿→青→蓝），逐行从屏幕上"扫"出来
colors=(31 33 32 36 34)
i=0
while IFS= read -r line; do
    [ -n "$line" ] || continue
    printf "\033[${colors[$i]}m%s${reset}\n" "$line"
    i=$((i + 1))
    sleep 0.1
done <<'LOGO'
 __  __ _       _ ____  ____
|  \/  (_)_ __ (_)  _ \| __ )
| |\/| | | '_ \| | | | |  _ \
| |  | | | | | | | |_| | |_) |
|_|  |_|_|_| |_|_|____/|____/
LOGO
sleep 0.2
printf "${bold}${green}  ✅ MiniDB 安装成功！${reset}\n"
echo ""
echo "  任意目录敲 minidb 进入数据库"
echo "  跑全部测试:    ./.venv/bin/python -m pytest"
