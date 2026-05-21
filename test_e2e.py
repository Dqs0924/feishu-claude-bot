#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端测试：完整流程验证"""

import requests
import json
import time
import re

APP_ID     = "cli_xxxxxxxxxxxxx"
APP_SECRET = "YOUR_FEISHU_APP_SECRET"
CHAT_ID    = "oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
BASE_URL   = "https://open.feishu.cn/open-apis"

print("=" * 60)
print("  端到端测试 - 飞书 → Claude → 飞书")
print("=" * 60)

# Step 1: 获取 token
print("\n[Step 1/4] 获取 tenant_access_token...")
resp = requests.post(f"{BASE_URL}/auth/v3/tenant_access_token/internal",
                     json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
token = resp.json()["tenant_access_token"]
print(f"✅ Token 获取成功")

# Step 2: 获取群聊消息
print("\n[Step 2/4] 获取群聊消息...")
headers = {"Authorization": f"Bearer {token}"}
resp2 = requests.get(f"{BASE_URL}/im/v1/messages",
                     headers=headers,
                     params={"container_id": CHAT_ID, "container_id_type": "chat", "page_size": 10},
                     timeout=10)
data2 = resp2.json()

if data2.get("code") != 0:
    print(f"❌ 获取消息失败：{data2}")
    exit(1)

items = data2.get("data", {}).get("items", [])
print(f"✅ 获取到 {len(items)} 条消息")

# Step 3: 查找用户的 /run 指令（跳过机器人自己发的）
print("\n[Step 3/4] 查找 /run 指令（跳过机器人自己发的消息）...")
target_msg_id = None
target_instruction = None

for msg in reversed(items):
    sender_id = msg.get("sender", {}).get("id", "")
    
    # 跳过机器人自己发的消息
    if sender_id == APP_ID:
        continue
    
    if msg.get("msg_type") != "text":
        continue
    
    body = msg.get("body", {})
    content_str = body.get("content", "{}")
    
    try:
        content_obj = json.loads(content_str)
        text = content_obj.get("text", "")
        
        # 支持 /run 或 @xxx /run 格式
        match = re.search(r'/run\s+(.*)', text, re.DOTALL)
        if match:
            target_msg_id = msg.get("message_id")
            target_instruction = match.group(1).strip()
            print(f"✅ 找到指令：/run {target_instruction}")
            print(f"   message_id: {target_msg_id}")
            break
    except:
        continue

if not target_msg_id:
    print("❌ 没有找到 /run 指令")
    print("请在飞书群聊中发送：/run 你好")
    exit(1)

# Step 4: 调用 Claude（演示模式）并回复
print(f"\n[Step 4/4] 调用 Claude Code（演示模式）...")
result = f"""✅ 指令「{target_instruction}」执行完成（演示模式）

📊 执行结果：
- 指令类型：测试指令
- 执行时间：{time.strftime('%Y-%m-%d %H:%M:%S')}
- 执行状态：成功

💡 提示：
要接入真实 Claude Code，需要：
1. 安装 Claude Code CLI
2. 修改脚本中的 call_claude() 函数
3. 取消注释 subprocess 调用

---
当前运行模式：演示模式（无需真实 Claude 环境）
"""

print(f"→ 正在回复到飞书群聊...")
reply_payload = {
    "msg_type": "text",
    "content": json.dumps({"text": result}),
}
resp3 = requests.post(
    f"{BASE_URL}/im/v1/messages/{target_msg_id}/reply",
    headers={**headers, "Content-Type": "application/json"},
    json=reply_payload,
    timeout=15,
)
data3 = resp3.json()

if data3.get("code") == 0:
    print(f"✅ 已成功回复到飞书群聊！")
    print(f"\n🎉 端到端测试通过！")
    print(f"   流程：飞书消息 → 脚本识别 → Claude执行（演示）→ 飞书回复")
else:
    print(f"❌ 回复失败：{data3}")
    exit(1)

print("\n" + "=" * 60)
