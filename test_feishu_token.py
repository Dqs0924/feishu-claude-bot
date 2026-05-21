#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试飞书 token 和权限是否生效"""

import requests
import json
import sys

APP_ID = "cli_xxxxxxxxxxxxx"
APP_SECRET = "YOUR_FEISHU_APP_SECRET"

print("=" * 60)
print("  飞书 Token + 权限测试")
print("=" * 60)

# Step 1: 获取 tenant_access_token
print("\n[1/3] 获取 tenant_access_token...")
resp = requests.post(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": APP_ID, "app_secret": APP_SECRET},
    timeout=10,
)
data = resp.json()
if data.get("code") != 0:
    print(f"❌ 获取 token 失败：{data}")
    sys.exit(1)

token = data["tenant_access_token"]
print(f"✅ token 获取成功（有效期 {data.get('expire', 'N/A')} 秒）")

# Step 2: 测试机器人能力（获取群聊列表）
print("\n[2/3] 测试机器人能力（获取群聊列表）...")
resp2 = requests.get(
    "https://open.feishu.cn/open-apis/im/v1/chats",
    headers={"Authorization": f"Bearer {token}"},
    params={"page_size": 20},
    timeout=10,
)
data2 = resp2.json()
print(f"响应 code: {data2.get('code')}")
print(f"响应 msg:  {data2.get('msg', '')}")

if data2.get("code") == 0:
    items = data2.get("data", {}).get("items", [])
    print(f"✅ 机器人能力已激活！找到 {len(items)} 个群聊")
    for chat in items:
        print(f"  - {chat.get('name', '(无名称)')}  chat_id={chat.get('chat_id', '')}")
else:
    print(f"❌ 机器人能力未激活或权限不足")
    print(json.dumps(data2, ensure_ascii=False, indent=2))

# Step 3: 测试发送消息权限（获取用户信息）
print("\n[3/3] 测试应用信息...")
resp3 = requests.get(
    "https://open.feishu.cn/open-apis/authen/v1/user_info",
    headers={"Authorization": f"Bearer {token}"},
    timeout=10,
)
data3 = resp3.json()
print(f"用户信息 API 响应 code: {data3.get('code')}")
if data3.get("code") == 0:
    print(f"✅ 用户信息 API 可用")
else:
    print(f"⚠️ 用户信息 API 需要额外权限（正常）")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
