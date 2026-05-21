#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书 Webhook 模式 - 异步接收 + 主动推送
需配置：1) 飞书开放平台事件订阅  2) ngrok 公网代理
"""

import os, sys, json, time, logging, subprocess, shutil, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from feishu_listener import (
    start_webhook, reply_text, send_text, _headers, BASE_URL as FS_BASE,
    APP_ID as FS_APP_ID, APP_SECRET as FS_APP_SECRET,
)

# ── 配置 ───────────────────────────────────────────────
PORT = int(os.environ.get('WEBHOOK_PORT', '8080'))
NGROK_AUTHTOKEN = os.environ.get('NGROK_AUTHTOKEN', '')

# ── 日志 ───────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(__file__), 'webhook', 'webhook.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger('webhook')

# ── Claude 调用 ─────────────────────────────────────────
def _find_claude():
    candidates = ['claude', os.path.expandvars(r'%APPDATA%
pm\claude.cmd')]
    for c in candidates:
        if os.path.exists(c) or shutil.which(c):
            return c
    return 'claude'

def call_claude(instruction: str) -> str:
    cmd = _find_claude()
    try:
        result = subprocess.run(
            [cmd, '-p', instruction, '--dangerously-skip-permissions'],
            capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace',
        )
        return result.stdout if result.returncode == 0 else f'❌ {result.stderr}'
    except subprocess.TimeoutExpired:
        return '❌ 执行超时（>5分钟）'
    except Exception as e:
        return f'❌ 异常：{e}'

# ── 消息回调 ───────────────────────────────────────────
def on_message(content: str, sender: str, message_id: str):
    log.info(f'收到消息 from {sender}: {content[:80]}')
    if not content.startswith('/run'):
        return
    instruction = content[4:].strip()
    log.info(f'执行指令: {instruction}')
    result = call_claude(instruction)
    for i in range(0, len(result), 2000):
        reply_text(message_id, result[i:i+2000])

# ── Ngrok 隧道 ──────────────────────────────────────────
def start_ngrok():
    ngrok = shutil.which('ngrok')
    if not ngrok:
        log.warning('ngrok 未安装，跳过公网隧道（Webhook 仅本机可用）')
        return
    if NGROK_AUTHTOKEN:
        subprocess.run([ngrok, 'config', 'add-authtoken', NGROK_AUTHTOKEN],
                       capture_output=True)
    proc = subprocess.Popen(
        [ngrok, 'http', str(PORT), '--log=stdout'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    try:
        import requests
        resp = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=3)
        url = resp.json()['tunnels'][0]['public_url']
        log.info(f'Ngrok 公网 URL: {url}/feishu-webhook')
        log.info(f'请在飞书后台配置此 URL 为事件订阅地址')
    except Exception:
        log.warning('Ngrok 启动中，无法获取 URL')
    return proc

# ── 主入口 ─────────────────────────────────────────────
if __name__ == '__main__':
    log.info('=' * 50)
    log.info('  飞书 Webhook 模式')
    log.info('=' * 50)

    # 启动 Ngrok（如果可用）
    ngrok_proc = start_ngrok()

    # 启动 Webhook 服务器
    log.info(f'Webhook 服务器启动: http://0.0.0.0:{PORT}/feishu-webhook')
    try:
        start_webhook(
            on_instruction=on_message,
            app_secret=FS_APP_SECRET or os.environ.get('FEISHU_APP_SECRET', ''),
            port=PORT,
        )
    except KeyboardInterrupt:
        log.info('已停止')
    finally:
        if ngrok_proc:
            ngrok_proc.terminate()
