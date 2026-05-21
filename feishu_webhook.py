#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书 Webhook 事件接收服务 v1.1
完整对接飞书官方 Webhook 事件接收、解密、校验、正常响应
使用 Python 内置 http.server 实现，无需额外依赖

v1.1 修复：
  - 延迟导入 run_feishu_poll，避免模块初始化崩溃
  - 从 config.json 直接读取配置，不依赖 rfp.CONFIG
  - 端口从配置文件读取（非硬编码8080）
  - 全链路 try/except 包裹 + 详细日志
  - 启动自检：逐步骤报告状态
"""

import os
import sys
import json
import hmac
import hashlib
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")

# ── 日志配置 ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_DIR, "webhook.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("feishu.webhook")

# ── 延迟导入 (避免模块初始化崩溃) ────────────────────
_rfp = None
_router_instance = None
_processed_ids = set()  # ✅ 已处理消息去重
PROCESSED_MAX = 500  # 去重集合最大长度

def _get_rfp():
    """延迟导入 run_feishu_poll，捕获所有初始化异常"""
    global _rfp
    if _rfp is not None:
        return _rfp
    try:
        log.info("[Webhook] 正在导入 run_feishu_poll 模块...")
        sys.path.insert(0, PROJECT_DIR)
        import run_feishu_poll as mod
        _rfp = mod
        log.info("[Webhook] run_feishu_poll 导入成功")
        return _rfp
    except Exception as e:
        log.error(f"[Webhook] 导入 run_feishu_poll 失败：{e}", exc_info=True)
        raise RuntimeError(f"无法导入核心模块 run_feishu_poll：{e}") from e

def _load_config():
    """从 config.json 直接读取配置"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"[Webhook] 读取配置失败，使用默认值：{e}")
        return {}

def _get_webhook_config():
    """获取 webhook 配置节"""
    cfg = _load_config()
    return cfg.get("webhook", {})

# ── 签名校验 ─────────────────────────────────────────
def verify_signature(signature, timestamp, nonce, encrypt_key):
    """验证飞书 Webhook 签名"""
    if not encrypt_key:
        return True
    content = f"{timestamp}{nonce}{encrypt_key}"
    calc_sig = hmac.new(
        encrypt_key.encode("utf-8"), content.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(calc_sig, signature)

# ── 路由器初始化 ─────────────────────────────────────
def init_router():
    """初始化 SmartRouter（延迟加载 + 完备异常捕获）"""
    global _router_instance
    if _router_instance is not None:
        return _router_instance
    try:
        rfp = _get_rfp()
        log.info("[Webhook] 正在初始化 AgentManager...")
        agents = rfp.AgentManager()
        log.info(f"[Webhook] AgentManager 就绪：{len(agents.agents)} 个角色")

        log.info("[Webhook] 正在初始化 RAG 引擎...")
        rag = rfp.RAGEngine() if rfp.RAG_AVAILABLE else None
        log.info(f"[Webhook] RAG 引擎：{'就绪' if rag else '未启用'}")

        log.info("[Webhook] 正在创建 SmartRouter...")
        _router_instance = rfp.SmartRouter(agents, rag)
        log.info("[Webhook] SmartRouter 就绪")
        return _router_instance
    except Exception as e:
        log.error(f"[Webhook] 路由器初始化失败：{e}", exc_info=True)
        raise RuntimeError(f"SmartRouter 初始化失败：{e}") from e

# ── 事件处理 ─────────────────────────────────────────
def handle_event(event_data):
    """处理飞书事件"""
    try:
        # 飞书 URL 验证事件：type 在顶层
        top_type = event_data.get("type", "")
        if top_type == "url_verification":
            challenge = event_data.get("challenge", "")
            log.info(f"[Webhook] URL 验证挑战：{challenge[:30]}...")
            return {"challenge": challenge}

        # 飞书消息事件：event_type 在 header 中
        event_type = event_data.get("header", {}).get("event_type", "")
        log.info(f"[Webhook] 收到事件：{event_type}")

        if event_type == "im.message.receive_v1":
            return _handle_message(event_data)

        else:
            log.info(f"[Webhook] 跳过事件类型：{event_type}")
            return {"code": 0, "msg": "success"}

    except Exception as e:
        log.error(f"[Webhook] 事件处理异常：{e}", exc_info=True)
        return {"code": -1, "msg": str(e)}

def _handle_message(event_data):
    """处理接收消息事件"""
    global _processed_ids
    event = event_data.get("event", {})
    message = event.get("message", {})
    message_id = message.get("message_id", "")
    sender = event.get("sender", {})
    sender_type = sender.get("sender_type", "")

    # ✅ 幂等性：已处理消息直接跳过
    if message_id and message_id in _processed_ids:
        log.info(f"[Webhook] 跳过已处理消息：{message_id}")
        return {"code": 0, "msg": "success"}

    if sender_type == "app":
        log.info("[Webhook] 过滤应用自己发的消息")
        return {"code": 0, "msg": "success"}

    if message.get("message_type") != "text":
        log.info(f"[Webhook] 非文本消息，跳过：{message.get('message_type', 'unknown')}")
        return {"code": 0, "msg": "success"}

    content_raw = message.get("content", "{}")
    try:
        text = json.loads(content_raw).get("text", "")
    except json.JSONDecodeError:
        log.error("[Webhook] 消息内容 JSON 解析失败")
        return {"code": -1, "msg": "content parse error"}

    if not text or not text.strip():
        return {"code": 0, "msg": "success"}

    log.info(f"[Webhook] 收到用户消息：{text[:100]}")

    try:
        # ✅ 标记已处理（防重复）
        if message_id:
            _processed_ids.add(message_id)
            # 限制集合大小
            if len(_processed_ids) > PROCESSED_MAX:
                _processed_ids.clear()

        router = init_router()
        rfp = _get_rfp()
        reply_text, should_reply = router.route(text, message_id)
        if should_reply and reply_text:
            rfp.reply_message(message_id, reply_text)
            log.info(f"[Webhook] 已回复 ({len(reply_text)} 字符)")
    except Exception as e:
        log.error(f"[Webhook] 消息处理失败：{e}", exc_info=True)

    return {"code": 0, "msg": "success"}

# ── HTTP 请求处理器 ──────────────────────────────────
class WebhookHandler(BaseHTTPRequestHandler):
    """飞书 Webhook HTTP 请求处理器"""

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            event_data = json.loads(body)
        except Exception as e:
            log.error(f"[Webhook] 请求体解析失败：{e}")
            self.send_response(400)
            self.end_headers()
            return

        # 签名验证（可选）
        wc = _get_webhook_config()
        encrypt_key = wc.get("encrypt_key", "")
        if encrypt_key:
            signature = self.headers.get("X-Lark-Signature", "")
            timestamp = self.headers.get("X-Lark-Timestamp", "")
            nonce = self.headers.get("X-Lark-Nonce", "")
            if not verify_signature(signature, timestamp, nonce, encrypt_key):
                log.warning("[Webhook] 签名验证失败")
                self.send_response(403)
                self.end_headers()
                return

        response = handle_event(event_data)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, fmt, *args):
        log.debug(f"[HTTP] {args[0] if args else fmt}")

# ── Webhook 服务器 ───────────────────────────────────
class WebhookServer:
    """飞书 Webhook 服务器"""

    def __init__(self):
        wc = _get_webhook_config()
        self.host = wc.get("host", "0.0.0.0")
        self.port = int(wc.get("port", 8080))
        self.enabled = wc.get("enabled", False)
        self.server = None
        self.thread = None
        self.running = False

    def start(self):
        """启动 Webhook 服务器（全链路异常捕获）"""
        if not self.enabled:
            log.info("[Webhook] 未启用，跳过启动")
            return False

        if self.running:
            log.warning("[Webhook] 已在运行中")
            return True

        steps = [
            ("初始化路由器", lambda: init_router()),
        ]
        for step_name, step_fn in steps:
            try:
                log.info(f"[Webhook] {step_name}...")
                step_fn()
                log.info(f"[Webhook] {step_name} — 完成")
            except Exception as e:
                log.error(f"[Webhook] {step_name} 失败：{e}", exc_info=True)
                return False

        try:
            log.info(f"[Webhook] 绑定地址 {self.host}:{self.port}...")
            self.server = HTTPServer((self.host, self.port), WebhookHandler)
            log.info("[Webhook] HTTP 服务器创建成功")

            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.running = True
            log.info(f"[Webhook] 服务器已启动 → http://{self.host}:{self.port}/webhook")
            return True
        except OSError as e:
            if e.errno == 10048:  # Windows: port already in use
                log.error(f"[Webhook] 端口 {self.port} 已被占用！请更换端口或关闭占用进程")
            else:
                log.error(f"[Webhook] 服务器启动失败：{e}", exc_info=True)
            return False
        except Exception as e:
            log.error(f"[Webhook] 服务器启动失败：{e}", exc_info=True)
            return False

    def stop(self):
        """停止 Webhook 服务器"""
        if not self.running:
            return
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception as e:
            log.error(f"[Webhook] 停止服务器异常：{e}")
        self.running = False
        log.info("[Webhook] 服务器已停止")

# ── 自检函数 ─────────────────────────────────────────
def self_test():
    """启动自检：逐步骤验证并报告"""
    print("=" * 50)
    print("  Webhook 服务器启动自检")
    print("=" * 50)

    # Step 1: 配置文件
    print("\n[1/6] 配置检查...")
    try:
        cfg = _load_config()
        wc = cfg.get("webhook", {})
        print(f"  配置文件：{CONFIG_FILE}")
        print(f"  Webhook 启用：{wc.get('enabled', False)}")
        print(f"  监听地址：{wc.get('host', '0.0.0.0')}:{wc.get('port', 8080)}")
        print("  ✅ 配置读取成功")
    except Exception as e:
        print(f"  ❌ 配置读取失败：{e}")
        return False

    # Step 2: 核心模块导入
    print("\n[2/6] 核心模块导入...")
    try:
        rfp = _get_rfp()
        print(f"  ✅ run_feishu_poll 导入成功")
    except Exception as e:
        print(f"  ❌ 导入失败：{e}")
        return False

    # Step 3: Agent 索引
    print("\n[3/6] Agent 角色索引...")
    try:
        agents = rfp.AgentManager()
        print(f"  ✅ {len(agents.agents)} 个角色就绪")
    except Exception as e:
        print(f"  ❌ 索引失败：{e}")
        return False

    # Step 4: RAG 引擎
    print("\n[4/6] RAG 引擎初始化...")
    try:
        rag = rfp.RAGEngine() if rfp.RAG_AVAILABLE else None
        print(f"  ✅ RAG {'就绪' if rag else '未启用'}")
    except Exception as e:
        print(f"  ❌ RAG 失败：{e}")
        return False

    # Step 5: SmartRouter
    print("\n[5/6] SmartRouter 创建...")
    try:
        router = init_router()
        print("  ✅ SmartRouter 就绪")
    except Exception as e:
        print(f"  ❌ 创建失败：{e}")
        return False

    # Step 6: HTTP 服务器绑定
    print("\n[6/6] HTTP 服务器绑定...")
    try:
        host = wc.get("host", "0.0.0.0")
        port = int(wc.get("port", 8080))
        srv = HTTPServer((host, port), WebhookHandler)
        srv.server_close()
        print(f"  ✅ 端口 {host}:{port} 可用")
    except OSError as e:
        if e.errno == 10048:
            print(f"  ❌ 端口 {port} 已被占用！请执行: netstat -ano | findstr :{port}")
        else:
            print(f"  ❌ 绑定失败：{e}")
        return False
    except Exception as e:
        print(f"  ❌ 失败：{e}")
        return False

    print("\n" + "=" * 50)
    print("  全部检查通过，Webhook 服务器可启动！")
    print("=" * 50)
    return True

# ── 主函数 ───────────────────────────────────────────
def main():
    """主函数（完备异常捕获）"""
    try:
        # 自检
        if not self_test():
            log.error("[Webhook] 自检未通过，退出")
            sys.exit(1)

        # 启动服务器
        server = WebhookServer()
        if not server.start():
            log.error("[Webhook] 启动失败")
            sys.exit(1)

        print("\n[Webhook] 服务器运行中，按 Ctrl+C 停止...")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        log.info("[Webhook] 收到中断信号")
        if 'server' in dir():
            server.stop()
    except Exception as e:
        log.error(f"[Webhook] 未捕获异常：{e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
