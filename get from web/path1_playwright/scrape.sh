#!/bin/bash
# 组卷网题目抓取封装脚本
# 用法: ./scrape.sh -k zsd27977 -t t1 -l 5

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 确保已登录
if [ ! -f /Users/song/project/STUDYAGENT/get from web/shared/storage-state.json ]; then
    echo "尚未登录，请先运行: python3 login.py"
    echo "或手动提供 cookie: ./scrape.sh -k zsd27977 --cookie 'key=val; ...'"
    exit 1
fi

exec python3 scrape.py "$@"
