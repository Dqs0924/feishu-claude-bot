#!/usr/bin/env bash
# 飞书模式启动脚本
# 用法：
#   bash start_feishu.sh webhook   # Webhook 模式（需公网或 ngrok）
#   bash start_feishu.sh poll      # 轮询模式（无需公网，需提供 chat_id）
#   bash start_feishu.sh poll oc_xxx  # 轮询模式（指定 chat_id）

set -e

export FEISHU_APP_ID="cli_xxxxxxxxxxxxx"
export FEISHU_APP_SECRET="YOUR_FEISHU_APP_SECRET"
export FEISHU_CHAT_ID="oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-poll}"
CHAT_ID="${2:-}"

if [ "$MODE" = "webhook" ]; then
    echo "============================================================"
    echo "  飞书 → Claude Code  [Webhook 模式]"
    echo "  监听端口：8080"
    echo "  Webhook URL（填到飞书后台）："
    echo "    http://你的公网IP:8080/feishu-webhook"
    echo "  （本地测试请用 ngrok：ngrok http 8080）"
    echo "============================================================"
    python.exe run_demo.py --platform feishu --mode webhook

elif [ "$MODE" = "poll" ]; then
    if [ -z "$CHAT_ID" ]; then
        echo "============================================================"
        echo "  飞书 → Claude Code  [轮询模式]"
        echo ""
        echo "  需要先获取 chat_id，请按以下步骤操作："
        echo "  1. 在飞书中把你的机器人加入某个群聊或私聊"
        echo "  2. 打开该聊天，查看 URL，复制 chat_id（oc_ 开头）"
        echo "     例如：https://open.feishu.cn/platform/chat/oc_abc123..."
        echo "  3. 运行：bash start_feishu.sh poll oc_你的chat_id"
        echo "============================================================"
        echo ""
        echo "[提示] 也可以通过 API 获取 chat_id，运行以下 Python 代码："
        echo ""
        echo "  python.exe -c \""
        echo "  import requests, os;"
        echo "  token = requests.post("
        echo "    'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',"
        echo "    json={'app_id': '$FEISHU_APP_ID', 'app_secret': '$FEISHU_APP_SECRET'}"
        echo "  ).json()['tenant_access_token'];"
        echo "  resp = requests.get("
        echo "    'https://open.feishu.cn/open-apis/im/v1/chats',"
        echo "    headers={'Authorization': f'Bearer {token}'}"
        echo "  ).json();"
        echo "  print(resp)"
        echo "  \""
        exit 1
    fi
    echo "============================================================"
    echo "  飞书 → Claude Code  [轮询模式]"
    echo "  chat_id = $CHAT_ID"
    echo "  轮询间隔：5 秒"
    echo "============================================================"
    python.exe run_demo.py --platform feishu --mode poll --chat-id "$CHAT_ID"

else
    echo "未知模式：$MODE"
    echo "用法：bash start_feishu.sh [webhook|poll] [chat_id]"
    exit 1
fi
