#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块2：Claude CLI 调用验证
功能：用 Python subprocess 调用 Claude CLI，捕获输出结果
依赖：需提前安装并配置 Claude Code CLI（claude 命令可用）

正确使用方式：
  claude -p "指令" --dangerously-skip-permissions
"""

import subprocess
import sys
import os
import shutil

# Claude CLI 可执行文件名（按实际安装情况调整）
# Windows 下会自动尝试 .cmd 和 .exe 后缀
CLAUDE_CMD = "claude"


def _find_claude():
    """
    多路径探测 Claude CLI 可执行文件
    返回：可用命令字符串（可直接传入 subprocess.run）
    """
    candidates = [
        "claude",
        r"C:\Program Files\nodejs\claude.cmd",
        r"C:\Program Files\nodejs\claude.exe",
        os.path.expandvars(r"%APPDATA%\npm\claude.cmd"),
        os.path.expandvars(r"%LOCALAPPDATA%\npm\claude.cmd"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # 用 which 最后试一次
    found = shutil.which("claude")
    if found:
        return found
    return CLAUDE_CMD


def check_claude_available():
    """
    检查 claude 命令是否可用
    用 --version 验证（正确用法：列表 + shell=False）
    """
    cmd_path = _find_claude()
    try:
        result = subprocess.run(
            [cmd_path, "--version"],
            capture_output=True,
            timeout=5,
            shell=False,          # 列表参数必须用 shell=False（默认）
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def call_claude(instruction, timeout=120):
    """
    调用 Claude CLI 执行指令（真实调用）
    参数：
        instruction: 用户指令（字符串）
        timeout: 超时时间（秒），默认 120 秒
    返回：
        (success: bool, output: str, error: str)
    """
    if not check_claude_available():
        return False, None, (
            f"未找到可用的 {CLAUDE_CMD} 命令。\n"
            "请确认已完成以下任一项：\n"
            "  1. 安装 Claude Code Desktop（含 CLI）\n"
            "  2. 将 claude 命令所在目录加入 PATH\n"
            "  3. 修改本文件 _find_claude() 中的路径"
        )

    cmd_path = _find_claude()
    # 构造命令：
    #   -p               → 非交互打印模式（对应 --print）
    #   --dangerously-skip-permissions  → 跳过所有权限确认（自动化必需）
    cmd = [cmd_path, "-p", instruction, "--dangerously-skip-permissions"]

    print(f"[Claude CLI] 执行指令：{instruction}")
    print(f"[Claude CLI] 完整命令：{' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        output = result.stdout.strip()
        err_output = result.stderr.strip()

        if result.returncode == 0:
            print(f"[Claude CLI] 执行成功，输出长度：{len(output)} 字符")
            return True, output, None
        else:
            error_msg = f"Claude CLI 返回码 {result.returncode}\n"
            if err_output:
                error_msg += f"stderr：{err_output[:500]}"
            if output:
                error_msg += f"\nstdout：{output[:500]}"
            print(f"[Claude CLI] 执行失败：{error_msg}")
            return False, output, error_msg

    except subprocess.TimeoutExpired:
        return False, None, f"Claude CLI 执行超时（>{timeout}秒），请检查指令复杂度或网络连接"
    except FileNotFoundError:
        return False, None, f"未找到 {cmd_path}，请检查安装路径"
    except Exception as e:
        return False, None, f"调用 Claude CLI 时发生异常：{str(e)}"


def call_claude_demo_mode(instruction):
    """
    演示模式：当 Claude CLI 不可用时，模拟返回结果
    用于在无 Claude 环境下验证整体链路
    """
    print(f"[演示模式] Claude CLI 不可用，使用模拟返回")
    demo_output = (
        f"[模拟执行结果]\n"
        f"指令：{instruction}\n"
        f"执行状态：成功（模拟）\n"
        f"输出：\n"
        f"Hello World\n"
        f"---\n"
        f"提示：安装 Claude Code CLI 后可执行真实调用"
    )
    return True, demo_output, None


if __name__ == "__main__":
    # 单独运行本模块时，执行一条测试指令
    test_instruction = "用一句话介绍 Python"
    print(f"=== Claude CLI 调用测试 ===")

    if check_claude_available():
        print(f"[状态] 检测到 Claude CLI，执行真实调用...\n")
        success, output, error = call_claude(test_instruction, timeout=60)
    else:
        print(f"[状态] 未检测到 Claude CLI，进入演示模式...\n")
        success, output, error = call_claude_demo_mode(test_instruction)

    print(f"\n--- 执行结果 ---")
    if success:
        print(output)
    else:
        print(f"执行失败：{error}")
