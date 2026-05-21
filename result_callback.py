#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块3：结果回传模拟（反向闭环验证）
功能：将 Claude CLI 返回的结果写入本地文件，模拟"回传至手机端"的逻辑
后续可替换为真实消息发送接口
"""

import os
import sys
import time
from datetime import datetime


OUTBOX_DIR = os.path.join(os.path.dirname(__file__), "outbox")


def ensure_outbox():
    """确保 outbox 目录存在"""
    os.makedirs(OUTBOX_DIR, exist_ok=True)


def write_result(result_text, instruction=""):
    """
    将执行结果写入 outbox 目录
    文件名格式：result_YYYYMMDD_HHMMSS.txt
    返回：写入的文件路径
    """
    ensure_outbox()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"result_{timestamp}.txt"
    file_path = os.path.join(OUTBOX_DIR, filename)

    # 构造结果文件内容（模拟飞书消息格式）
    content = build_result_message(result_text, instruction)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[结果回传] 结果已写入：{file_path}")
    return file_path


def build_result_message(result_text, instruction=""):
    """
    构造格式化的结果消息（模拟飞书消息展示）
    后续可对接飞书发送 API，直接发送此内容
    """
    separator = "=" * 40
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"{separator}",
        f"  Claude Code 执行结果",
        f"{separator}",
    ]
    if instruction:
        lines.append(f"指令：{instruction}")
        lines.append(f"{separator}")
    lines.append(f"")
    lines.append(result_text)
    lines.append(f"")
    lines.append(f"{separator}")
    lines.append(f"  完成时间：{time_str}")
    lines.append(f"{separator}")
    return "\n".join(lines)


def simulate_wechat_send(result_text, instruction=""):
    """
    模拟发送飞书消息（当前为打印，后续可替换为真实发送）
    替换点：将 print 替换为 WeChatFerry / WeChatMsg 发送接口
    """
    message = build_result_message(result_text, instruction)
    print("\n" + "=" * 50)
    print("  [模拟飞书发送] 以下内容将发送至手机飞书：")
    print("=" * 50)
    print(message)
    print("=" * 50)
    print("[提示] 接入真实飞书接口后，此处将自动推送至手机。\n")

    # 同时写入 outbox（持久化存档）
    return write_result(result_text, instruction)


def read_latest_result():
    """读取最近一次执行结果（供调试查看）"""
    ensure_outbox()
    txt_files = [f for f in os.listdir(OUTBOX_DIR) if f.endswith(".txt")]
    if not txt_files:
        return None, "outbox/ 目录下没有结果文件"
    latest = max(txt_files)
    file_path = os.path.join(OUTBOX_DIR, latest)
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read(), file_path


if __name__ == "__main__":
    # 单独运行本模块时，模拟一次结果回传
    demo_instruction = "输出Hello World"
    demo_result = (
        "Hello World\n"
        "执行状态：成功\n"
        "耗时：约 3 秒"
    )
    print("[测试] 模拟结果回传...")
    path = simulate_wechat_send(demo_result, demo_instruction)
    print(f"[完成] 结果文件已保存至：{path}")

    # 验证读取
    content, _ = read_latest_result()
    print(f"[验证] 最近一次结果预览：{content[:100]}...")
