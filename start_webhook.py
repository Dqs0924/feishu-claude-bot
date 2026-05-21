#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Webhook 预初始化启动器 — 解决飞书3秒验证超时
先加载 RAG/Agent/SmartRouter，再启动 HTTP 服务器
"""
import os, sys, json, logging, time
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(os.path.join(PROJECT_DIR, "webhook.log"), encoding="utf-8"),
              logging.StreamHandler(sys.stdout)])
log = logging.getLogger("webhook.preinit")

def pre_init():
    """预初始化所有重组件，返回 (agents, rag, router, rfp)"""
    log.info("=" * 50)
    log.info("  Webhook 预初始化启动")
    log.info("=" * 50)

    log.info("[1/4] 导入 run_feishu_poll...")
    import run_feishu_poll as rfp

    log.info("[2/4] 加载 AgentManager (184角色)...")
    agents = rfp.AgentManager()
    log.info(f"  {len(agents.agents)} 个角色")

    log.info("[3/4] 初始化 RAG 引擎...")
    rag = rfp.RAGEngine() if rfp.RAG_AVAILABLE else None
    log.info(f"  RAG: {'向量模式' if (rag and rag.vector_ready) else '未启用'}")

    log.info("[4/4] 创建 SmartRouter...")
    router = rfp.SmartRouter(agents, rag)
    log.info("  SmartRouter 就绪")

    # ★ 注入预初始化实例到 feishu_webhook 模块（跳过重复加载）
    import feishu_webhook as fw
    fw._router_instance = router
    fw._rfp = rfp
    log.info("  已注入预初始化实例")

    return agents, rag, router, rfp

def start_server():
    """启动 HTTP 服务器"""
    import feishu_webhook as fw
    from http.server import HTTPServer

    with open(os.path.join(PROJECT_DIR, "config.json"), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    wc = cfg.get("webhook", {})
    host = wc.get("host", "0.0.0.0")
    port = int(wc.get("port", 8090))

    log.info(f"[启动] 绑定 {host}:{port}...")
    server = HTTPServer((host, port), fw.WebhookHandler)
    log.info(f"[就绪] http://{host}:{port}/webhook")
    log.info("[就绪] 飞书验证可秒回（所有模块已预加载）")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("[停止] 服务器已关闭")
        server.server_close()

if __name__ == "__main__":
    pre_init()
    start_server()
