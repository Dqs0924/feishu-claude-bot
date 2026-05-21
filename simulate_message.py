#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块1：模拟消息监听（不接入真实飞书）
功能：读取本地文件/命令行输入，过滤以 /run 开头的指令
"""

import os
import time
import sys

INBOX_DIR = os.path.join(os.path.dirname(__file__), "inbox")


def read_instruction_from_file():
    """
    从 inbox 目录读取指令文件
    返回第一个找到的 .txt 文件内容（去掉 /run 前缀）
    """
    if not os.path.exists(INBOX_DIR):
        return None, "inbox 目录不存在，请先创建 inbox/ 目录"

    txt_files = [f for f in os.listdir(INBOX_DIR) if f.endswith(".txt")]
    if not txt_files:
        return None, "inbox/ 目录下没有 .txt 指令文件"

    # 读取第一个找到的指令文件，查找以 /run 开头的行（支持文件内含注释）
    file_path = os.path.join(INBOX_DIR, txt_files[0])
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("/run"):
                # 提取 /run 后的真正指令内容
                instruction = line[len("/run"):].strip()
                print(f"[指令来源] inbox 文件：{txt_files[0]}")
                return instruction, None

    return None, f"文件 {txt_files[0]} 中未找到以 /run 开头的行"


def read_instruction_from_cli():
    """
    从命令行参数读取指令
    用法：python simulate_message.py --cli "你的指令"
    """
    if len(sys.argv) >= 3 and sys.argv[1] == "--cli":
        raw = " ".join(sys.argv[2:])
        if not raw.startswith("/run"):
            return None, f"指令格式错误：请以 /run 开头。收到：{raw[:50]}"
        instruction = raw[len("/run"):].strip()
        return instruction, None
    return None, None  # 不是 CLI 模式，不报错


def watch_inbox(poll_interval=2):
    """
    监听模式：持续监听 inbox 目录，发现新指令文件后返回内容
    （用于后续自动化串联，当前 Demo 为单次执行）
    """
    print(f"[监听中] 正在监听 {INBOX_DIR} 目录...")
    processed = set()
    while True:
        txt_files = {f for f in os.listdir(INBOX_DIR) if f.endswith(".txt")}
        new_files = txt_files - processed
        if new_files:
            for f in new_files:
                file_path = os.path.join(INBOX_DIR, f)
                with open(file_path, "r", encoding="utf-8") as fp:
                    raw = fp.read().strip()
                if raw.startswith("/run"):
                    instruction = raw[len("/run"):].strip()
                    print(f"[新指令] 来自文件 {f}：{instruction}")
                    return instruction
            processed = txt_files
        time.sleep(poll_interval)


def get_instruction():
    """
    统一入口：优先读取 CLI 参数，其次读取 inbox 文件
    返回：(instruction, error_message)
    """
    # 方式1：命令行参数
    instruction, err = read_instruction_from_cli()
    if instruction:
        print(f"[指令来源] 命令行参数")
        return instruction, None
    if err:
        return None, err

    # 方式2：inbox 文件
    instruction, err = read_instruction_from_file()
    if instruction:
        print(f"[指令来源] inbox 文件")
        return instruction, None

    # 两种方式都没有有效指令
    hint = (
        "未找到有效指令。请选择一种方式输入：\n"
        "  方式1：python run_demo.py --cli '/run 输出Hello World'\n"
        "  方式2：在 inbox/ 目录下创建 .txt 文件，内容以 /run 开头"
    )
    return None, hint


if __name__ == "__main__":
    # 单独运行本模块时，打印获取到的指令
    instruction, err = get_instruction()
    if err:
        print(f"[错误] {err}")
    else:
        print(f"[成功] 提取到指令：{instruction}")
