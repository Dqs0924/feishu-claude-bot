#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动 ngrok 并获取公网 URL
"""
import subprocess
import time
import re
import requests
import json

NGROK_EXE = "ngrok.exe"
PORT = 8090

def start_ngrok():
    """启动 ngrok 并返回公网 URL"""
    print(f"[ngrok] 正在启动内网穿透（端口 {PORT}）...")
    
    # 启动 ngrok 进程
    proc = subprocess.Popen(
        [NGROK_EXE, "http", str(PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    print(f"[ngrok] 进程已启动 (PID: {proc.pid})")
    print(f"[ngrok] 等待 ngrok 初始化...")
    
    # 等待 ngrok API 就绪
    time.sleep(3)
    
    # 查询 ngrok API 获取 URL
    try:
        resp = requests.get("http://localhost:4040/api/tunnels")
        if resp.status_code == 200:
            data = resp.json()
            tunnels = data.get("tunnels", [])
            if tunnels:
                public_url = tunnels[0].get("public_url")
                print(f"[ngrok] ✅ 公网 URL: {public_url}")
                print(f"[ngrok] 转发: {public_url} -> http://localhost:{PORT}")
                return public_url, proc
    except Exception as e:
        print(f"[ngrok] API 查询失败: {e}")
    
    # 如果 API 查询失败，尝试从输出中解析
    print(f"[ngrok] 尝试从输出中解析 URL...")
    output = ""
    for _ in range(50):  # 等待5秒
        if proc.stdout.readable():
            line = proc.stdout.readline()
            if line:
                output += line
                print(f"[ngrok] {line.strip()}")
                # 解析 URL
                match = re.search(r'https://[a-z0-9-]+\.ngrok-free\.app', line)
                if match:
                    public_url = match.group(0)
                    print(f"[ngrok] ✅ 公网 URL: {public_url}")
                    return public_url, proc
        time.sleep(0.1)
    
    print(f"[ngrok] ❌ 无法获取 URL")
    return None, proc

if __name__ == "__main__":
    url, proc = start_ngrok()
    if url:
        print(f"\n{'='*50}")
        print(f"  公网 URL: {url}")
        print(f"  Webhook 地址: {url}/webhook")
        print(f"{'='*50}")
        print(f"\n[提示] 保持此窗口打开，关闭会重置 URL")
        print(f"[提示] 在飞书开放平台配置 Webhook URL: {url}/webhook")
        
        # 保持进程运行
        try:
            proc.wait()
        except KeyboardInterrupt:
            print(f"\n[ngrok] 正在停止...")
            proc.terminate()
    else:
        print(f"\n[错误] 无法获取 ngrok URL")
        print(f"[提示] 请手动运行: .\\ngrok.exe http 8090")
