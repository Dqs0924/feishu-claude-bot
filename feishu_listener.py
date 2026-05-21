#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书消息监听与发送模块（纯 HTTP 实现，无需 SDK）

前置步骤（一次性）：
  1. 打开 https://open.feishu.cn/app
  2. 点击「创建企业自建应用」
  3. 记录 App ID 和 App Secret
  4. 在「添加应用能力」里启用「机器人」
  5. 在「事件订阅 → 请求网址」里填写：http://你的IP:8080/feishu-webhook
     （本地调试用 ngrok 暴露端口，正式部署用服务器）
  6. 订阅事件：勾选「接收消息」→ im.message.receive_v1

如果不想配置 Webhook，也可以用「轮询模式」（见 bottom 的 poll 函数）。
"""

import os
import time
import json
import requests
from typing import Optional, Callable, List, Dict

# ── 配置（从环境变量或配置文件读取）───────────────────────────────
APP_ID     = os.environ.get("FEISHU_APP_ID",     "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
BASE_URL   = "https://open.feishu.cn/open-apis"

# 缓存 tenant_access_token，避免每次请求都重新获取
_token_cache = {"token": None, "expire_time": 0}


def _get_token() -> Optional[str]:
    """获取 tenant_access_token（自动缓存，过期自动刷新）"""
    global _token_cache
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expire_time"] - 60:
        return _token_cache["token"]

    if not APP_ID or not APP_SECRET:
        print("[飞书] ❌ 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET 环境变量")
        return None

    resp = requests.post(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[飞书] ❌ 获取 token 失败：{data}")
        return None

    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expire_time"] = now + data.get("expire", 7200)
    print("[飞书] ✅ token 获取成功")
    return _token_cache["token"]


def _headers() -> Dict:
    token = _get_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════
# 发送消息
# ══════════════════════════════════════════════════════════════════

def send_text(chat_id: str, content: str) -> bool:
    """
    发送文本消息到指定聊天（私聊 / 群聊）
    chat_id: 聊天 ID（通过 Webhook 事件或调用「获取群列表」获得）
    """
    resp = requests.post(
        f"{BASE_URL}/im/v1/messages?receive_id_type=chat_id",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": content}),
        },
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[飞书] ❌ 发送失败：{data}")
        return False
    print(f"[飞书] ✅ 消息已发送（chat_id={chat_id[:20]}...）")
    return True


def reply_text(message_id: str, content: str) -> bool:
    """回复某条消息（推荐，无需知道 chat_id）"""
    resp = requests.post(
        f"{BASE_URL}/im/v1/messages/{message_id}/reply",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "msg_type": "text",
            "content": json.dumps({"text": content}),
        },
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[飞书] ❌ 回复失败：{data}")
        return False
    print(f"[飞书] ✅ 已回复消息 {message_id[:20]}...")
    return True


# ══════════════════════════════════════════════════════════════════
# Webhook 接收服务器（推荐方式）
# ══════════════════════════════════════════════════════════════════

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import hmac
import hashlib


class _WebhookHandler(BaseHTTPRequestHandler):
    """处理飞书事件订阅的 Webhook 请求"""

    listener_callback: Optional[Callable[[str, str, str], None]] = None
    app_secret: str = ""

    def _validate_signature(self, body: bytes) -> bool:
        """验证请求签名（飞书事件订阅的安全机制）"""
        sig = self.headers.get("X-Lark-Signature", "")
        timestamp = self.headers.get("X-Lark-Timestamp", "")
        if not sig or not timestamp:
            return False
        expected = hmac.new(
            self.app_secret.encode(),
            f"{timestamp}{body.decode()}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(sig, expected)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        data = json.loads(body)

        # 飞书会先发一个 challenge 请求验证 Webhook 可用性
        if data.get("type") == "url_verification":
            challenge = data["challenge"]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"challenge": challenge}).encode())
            print("[飞书 Webhook] ✅ URL 验证通过")
            return

        # 验证签名
        if not self._validate_signature(body):
            self.send_response(403)
            self.end_headers()
            return

        # 处理消息接收事件
        header = data.get("header", {})
        event = data.get("event", {})

        if header.get("event_type") == "im.message.receive_v1":
            msg = event.get("message", {})
            msg_type = msg.get("message_type")
            if msg_type == "text":
                content = json.loads(msg.get("content", "{}")).get("text", "")
                sender = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
                message_id = msg.get("message_id", "")

                print(f"[飞书 Webhook] 📩 收到消息 from {sender}：{content[:50]}")

                # 回调上层处理函数
                if self.listener_callback:
                    self.listener_callback(content, sender, message_id)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"success":true}')
        else:
            self.send_response(200)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # 静默日志


def start_webhook(
    on_instruction: Callable[[str, str, str], None],
    app_secret: str,
    port: int = 8080,
):
    """
    启动 Webhook 服务器（阻塞，建议在独立线程中运行）

    on_instruction(content, sender_open_id, message_id):
        收到 /run 指令时的回调函数
    """
    _WebhookHandler.listener_callback = on_instruction
    _WebhookHandler.app_secret = app_secret

    server = HTTPServer(("0.0.0.0", port), _WebhookHandler)
    print(f"[飞书 Webhook] 🚀 监听中：http://0.0.0.0:{port}/feishu-webhook")
    server.serve_forever()


# ══════════════════════════════════════════════════════════════════
# 轮询模式（无需 Webhook，适合快速测试）
# ══════════════════════════════════════════════════════════════════

def poll_messages(chat_id: str, on_instruction: Callable[[str, str], None], interval: int = 5):
    """
    轮询指定聊天的新消息（简单但不够实时，仅用于快速测试）

    ⚠️ 注意：飞书 API 不推荐高频轮询，正式使用请配置 Webhook
    """
    print(f"[飞书轮询] 开始监听 chat_id={chat_id[:20]}...（间隔 {interval}s）")
    last_msg_id = None

    while True:
        try:
            resp = requests.get(
                f"{BASE_URL}/im/v1/messages",
                headers=_headers(),
                params={"container_id": chat_id, "page_size": 5},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                print(f"[飞书轮询] ❌ 获取消息失败：{data}")
                time.sleep(interval)
                continue

            items = data.get("data", {}).get("items", [])
            for msg in reversed(items):
                msg_id = msg.get("message_id")
                if msg_id == last_msg_id:
                    break
                last_msg_id = msg_id

                if msg.get("msg_type") == "text":
                    content = json.loads(msg.get("body", {}).get("content", "{}")).get("text", "")
                    if content.startswith("/run"):
                        instruction = content[4:].strip()
                        print(f"[飞书轮询] 📩 收到指令：{instruction}")
                        on_instruction(instruction, msg_id)
        except Exception as e:
            print(f"[飞书轮询] ❌ 异常：{e}")

        time.sleep(interval)


# ══════════════════════════════════════════════════════════════════
# 统一入口（供 run_demo.py 调用）
# ══════════════════════════════════════════════════════════════════

def start_feishu_mode(
    on_instruction: Callable[[str, str], None],
    mode: str = "webhook",  # "webhook" 或 "poll"
    chat_id: str = "",
    port: int = 8080,
):
    """
    启动飞书监听（统一入口）

    mode="webhook": 启动 Webhook 服务器（推荐，实时性好）
    mode="poll": 启动轮询模式（无需配置 Webhook，适合快速测试）
    """
    if not APP_ID or not APP_SECRET:
        print("=" * 50)
        print("  [飞书] 未配置 App ID / App Secret")
        print("  请设置环境变量：")
        print("    export FEISHU_APP_ID='your_app_id'")
        print("    export FEISHU_APP_SECRET='your_app_secret'")
        print("  或在 feishu_listener.py 顶部直接填写。")
        print("=" * 50)
        return

    if mode == "webhook":
        # Webhook 模式：启动 HTTP 服务器（需要在飞书后台配置 Webhook URL）
        print("[飞书] Webhook 模式启动中...")
        print("  请确保已在飞书后台配置 Webhook URL：")
        print(f"  http://你的服务器IP:{port}/feishu-webhook")
        print("  （本地调试可使用 ngrok 暴露端口）")
        start_webhook(
            on_instruction=lambda content, sender, msg_id: (
                on_instruction(content[4:].strip(), msg_id)
                if content.startswith("/run")
                else None
            ),
            app_secret=APP_SECRET,
            port=port,
        )
    else:
        # 轮询模式
        if not chat_id:
            print("[飞书] ❌ 轮询模式需要 chat_id，请在调用时传入。")
            return
        poll_messages(chat_id, on_instruction)


if __name__ == "__main__":
    # 单独运行测试：需要先填写上方的 APP_ID / APP_SECRET
    print("=== 飞书模块测试 ===")
    print("请先填写 APP_ID 和 APP_SECRET，然后重新运行。")
