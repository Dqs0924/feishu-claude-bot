#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Webhook 服务器启动测试脚本
实际启动服务器并验证其正常工作
"""
import sys
import os
import time
import json
import threading
from urllib.request import urlopen, Request, HTTPError

# 添加项目目录到路径
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import feishu_webhook as fw

def test_webhook_server():
    """测试 Webhook 服务器"""
    print("=" * 60)
    print("  Webhook 服务器启动测试")
    print("=" * 60)
    
    # Step 1: 启动服务器
    print("\n[1/4] 正在启动 Webhook 服务器...")
    server = fw.WebhookServer()
    result = server.start()
    
    if not result:
        print("  ❌ 服务器启动失败")
        return False
    
    print(f"  ✅ 服务器启动成功")
    print(f"  监听地址：http://{server.host}:{server.port}/webhook")
    
    # Step 2: 测试 URL 验证端点
    print("\n[2/4] 测试 URL 验证端点...")
    try:
        test_url = f"http://localhost:{server.port}/webhook"
        test_data = json.dumps({
            "header": {"event_type": "url_verification"},
            "challenge": "test_challenge_12345"
        }).encode("utf-8")
        
        req = Request(test_url, data=test_data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
            
            if status == 200 and "challenge" in body:
                print(f"  ✅ URL 验证端点正常 (status={status})")
                print(f"  返回的 challenge: {body['challenge'][:20]}...")
            else:
                print(f"  ❌ URL 验证端点异常 (status={status})")
                return False
    except Exception as e:
        print(f"  ❌ URL 验证端点测试失败：{e}")
        return False
    
    # Step 3: 测试消息接收端点
    print("\n[3/4] 测试消息接收端点...")
    try:
        test_data = json.dumps({
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "message_id": "test_msg_001",
                "message_type": "text",
                "content": json.dumps({"text": "/status"}),
                "sender": {"sender_type": "user"}
            }
        }).encode("utf-8")
        
        req = Request(test_url, data=test_data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
            
            if status == 200 and body.get("code") == 0:
                print(f"  ✅ 消息接收端点正常 (status={status})")
                print(f"  返回码：{body['code']}")
            else:
                print(f"  ❌ 消息接收端点异常 (status={status})")
                return False
    except Exception as e:
        print(f"  ❌ 消息接收端点测试失败：{e}")
        return False
    
    # Step 4: 停止服务器
    print("\n[4/4] 正在停止服务器...")
    server.stop()
    print("  ✅ 服务器已停止")
    
    print("\n" + "=" * 60)
    print("  ✅ 全部测试通过！Webhook 服务器工作正常")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_webhook_server()
    sys.exit(0 if success else 1)
