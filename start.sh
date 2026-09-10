#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "未找到 .venv。请先运行：./install.sh" >&2
    exit 1
fi

exec ./.venv/bin/python -m database_system.cli.main "$@"
