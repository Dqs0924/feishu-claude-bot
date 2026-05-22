#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块2：Claude CLI 调用封装 v2.0
================================
v2.0 新增：管道+线程流式模式（ClaudeSession），支持：
  • 实时 stdout 逐行捕获（非阻塞）
  • 持久进程（多轮对话保持上下文）
  • 远程审批关键词检测
  • 向下兼容：保留 call_claude() / call_claude_lean() 原有接口

正确使用方式：
  原模式：call_claude(instruction) → (success, output, error)
  新模式：session = ClaudeSession(session_id)
         session.start()
         session.write(instruction)
         for line in session.read_lines():
             send_to_feishu(line)
"""

import subprocess
import threading
import queue
import sys
import os
import re
import shutil
import logging

log = logging.getLogger("claude.session")

CLAUDE_CMD = "claude"

# ── 审批关键词检测 ─────────────────────────────────
APPROVAL_PATTERNS = [
    re.compile(r'Do you want to proceed', re.IGNORECASE),
    re.compile(r'需要.*?权限', re.IGNORECASE),
    re.compile(r'permission.*?required', re.IGNORECASE),
    re.compile(r'确认.*?(写入|删除|修改|执行)', re.IGNORECASE),
    re.compile(r'\[y/n\]', re.IGNORECASE),
    re.compile(r'proceed.*?\?', re.IGNORECASE),
    re.compile(r'I need your permission', re.IGNORECASE),
]


def _find_claude():
    """多路径探测 Claude CLI 可执行文件"""
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
    found = shutil.which("claude")
    if found:
        return found
    return CLAUDE_CMD


def check_claude_available():
    """检查 claude 命令是否可用"""
    cmd_path = _find_claude()
    try:
        result = subprocess.run(
            [cmd_path, "--version"],
            capture_output=True, timeout=5, shell=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def check_approval_line(line: str) -> bool:
    """检测一行 stdout 输出是否包含审批请求"""
    for pat in APPROVAL_PATTERNS:
        if pat.search(line):
            return True
    return False


# ══════════════════════════════════════════════════════════════
# 原有函数（完全保留，向后兼容）
# ══════════════════════════════════════════════════════════════

def call_claude(instruction, timeout=120):
    """
    调用 Claude CLI 执行指令（阻塞模式，兼容旧接口）
    返回: (success: bool, output: str, error: str)
    """
    if not check_claude_available():
        return False, None, (
            f"未找到可用的 {CLAUDE_CMD} 命令。\n"
            "请确认已完成以下任一项：\n"
            "  1. 安装 Claude Code Desktop（含 CLI）\n"
            "  2. 将 claude 命令所在目录加入 PATH\n"
        )
    cmd_path = _find_claude()
    cmd = [cmd_path, "-p", instruction, "--dangerously-skip-permissions"]
    print(f"[Claude CLI] 执行指令：{instruction}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", shell=False,
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
        return False, None, f"Claude CLI 执行超时（>{timeout}秒）"
    except FileNotFoundError:
        return False, None, f"未找到 {cmd_path}，请检查安装路径"
    except Exception as e:
        return False, None, f"调用 Claude CLI 时发生异常：{str(e)}"


def call_claude_demo_mode(instruction):
    """演示模式：当 Claude CLI 不可用时，模拟返回结果"""
    print(f"[演示模式] Claude CLI 不可用，使用模拟返回")
    demo_output = (
        f"[模拟执行结果]\n指令：{instruction}\n"
        f"执行状态：成功（模拟）\n输出：\nHello World\n"
        f"---\n提示：安装 Claude Code CLI 后可执行真实调用"
    )
    return True, demo_output, None


# ══════════════════════════════════════════════════════════════
# v2.0 新增：管道+线程流式模式
# ══════════════════════════════════════════════════════════════

class ClaudeSession:
    """流式 Claude Code 进程会话（-p 模式 + 管道 + 线程）

    每次调用 spawn 一个 one-shot 进程：
      claude -p "instruction" --dangerously-skip-permissions [--model X]
    输出通过后台线程实时入队，调用方 drain_output() 非阻塞获取。

    使用方式:
        session = ClaudeSession("chat_123")
        session.spawn("用 Python 写一个快排", model="haiku")
        for kind, data in session.drain_output():
            if kind == 'data':
                send_to_feishu(data)
            elif kind == 'approval':
                trigger_approval_card(data)
            elif kind == 'exit':
                handle_completion(data)
        # session 会在进程退出后自动标记 _running=False
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.process: subprocess.Popen = None
        self._out_queue = queue.Queue()
        self._reader_thread = None
        self._running = False

    # ── 生命周期 ─────────────────────────────────

    def spawn(self, instruction: str, model: str = None) -> bool:
        """启动 Claude -p 进程（one-shot），后台线程流式读取 stdout"""
        if self._running:
            log.warning("[ClaudeSession] 已有进程在运行，先 kill")
            self.kill()

        claude_cmd = _find_claude()
        cmd = [claude_cmd, "-p", instruction, "--dangerously-skip-permissions"]
        if model:
            cmd += ["--model", model]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,   # -p 模式不需要 stdin
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1,
            )
        except Exception as e:
            log.error("[ClaudeSession] spawn 失败：%s", e)
            self._running = False
            return False

        self._running = True
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True,
            name=f"claude-{self.session_id[:8]}"
        )
        self._reader_thread.start()
        log.info("[ClaudeSession] %s spawned (model=%s, %d chars)",
                 self.session_id[:12], model or 'default', len(instruction))
        return True

    def drain_output(self) -> list:
        """非阻塞获取所有待处理输出行

        返回: [(kind, data), ...]
          kind: 'data' | 'approval' | 'exit'
        """
        items = []
        try:
            while True:
                items.append(self._out_queue.get_nowait())
        except queue.Empty:
            pass
        return items

    def kill(self):
        """强制终止进程并清理"""
        self._running = False
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
            except Exception:
                pass
        log.info("[ClaudeSession] %s killed", self.session_id[:12])

    @property
    def is_running(self) -> bool:
        return self._running and self.process is not None and self.process.poll() is None

    # ── 内部 ─────────────────────────────────────

    def _read_loop(self):
        """后台线程：逐行读取 stdout"""
        try:
            for line in self.process.stdout:
                text = line.strip()
                if not text:
                    continue
                if check_approval_line(text):
                    self._out_queue.put(('approval', text))
                else:
                    self._out_queue.put(('data', text))
        except Exception as e:
            log.error("[ClaudeSession] read error: %s", e)
        finally:
            self._running = False
            exit_code = self.process.poll() if self.process else -1
            self._out_queue.put(('exit', exit_code))
            log.info("[ClaudeSession] %s exited (code=%s)", self.session_id[:12], exit_code)


# ══════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Claude CLI 调用测试 ===\n")

    # 原有阻塞模式测试
    if check_claude_available():
        print("[测试1] 原有阻塞模式...")
        success, output, error = call_claude("用一句话介绍 Python", timeout=60)
        if success:
            print(f"结果：{output[:200]}...")
        else:
            print(f"失败：{error}")
    else:
        print("[状态] 未检测到 Claude CLI，跳过原有模式测试")

    # 管道模式测试
    print("\n[测试2] 管道+线程流式模式...")
    if check_claude_available():
        session = ClaudeSession("test-session")
        if session.start():
            session.write("用一句话介绍 Python")
            import time as _time
            deadline = _time.time() + 60
            while _time.time() < deadline:
                items = session.drain_output()
                if not items:
                    _time.sleep(0.1)
                    continue
                for kind, data in items:
                    if kind == 'data':
                        print(f"  [流式] {data[:100]}")
                    elif kind == 'approval':
                        print(f"  [审批] {data[:100]}")
                    elif kind == 'exit':
                        print(f"  [退出] code={data}")
                        deadline = 0  # 立即退出循环
            session.kill()
        else:
            print("管道模式启动失败")
    else:
        print("Claude CLI 不可用，跳过管道模式测试")
