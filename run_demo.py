#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主入口：串联所有模块，完成"指令输入 → RAG解析 → 执行 → 结果输出"闭环

用法：
  # 模拟模式（默认，从 inbox/ 读文件）
  python run_demo.py

  # 飞书 Webhook 模式（推荐）
  export FEISHU_APP_ID="cli_xxx"
  export FEISHU_APP_SECRET="xxx"
  python run_demo.py --platform feishu --mode webhook

  # 飞书轮询模式（无需配置 Webhook）
  python run_demo.py --platform feishu --mode poll --chat-id oc_xxx


"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from call_claude import call_claude, check_claude_available, call_claude_demo_mode
from result_callback import simulate_wechat_send

# ── 尝试导入 RAG 模块 ─────────────────────────────────────
try:
    from rag_module import RAGEngine
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    RAGEngine = None


# ═══════════════════════════════════════════════════════
# 核心处理流程（平台无关）
# ═══════════════════════════════════════════════════════

def process_instruction(instruction: str, sender: str = "unknown") -> str:
    """
    处理一条指令的完整流程：RAG 解析 → 调用 Claude → 返回结果
    """
    print(f"[处理] 来自 {sender} 的指令：{instruction[:50]}...")

    # Step 1.5：RAG 解析
    parsed = instruction
    if RAG_AVAILABLE:
        try:
            rag = RAGEngine()
            parsed = rag.parse(instruction)
            if parsed != instruction:
                print(f"[RAG] 匹配成功：{instruction} → {parsed}")
                instruction = parsed
        except Exception as e:
            print(f"[RAG] 解析失败，使用原始指令：{e}")

    # Step 2：调用 Claude Code
    print(f"[Claude] 执行指令...")
    if check_claude_available():
        success, output, error = call_claude(instruction)
    else:
        print(f"[Claude] 未检测到 CLI，进入演示模式")
        success, output, error = call_claude_demo_mode(instruction)

    if not success:
        return f"❌ 执行失败：\n{error}"

    print(f"[完成] 输出长度：{len(output)} 字符")
    return output


# ═══════════════════════════════════════════════════════
# 模拟模式（从 inbox/ 读文件，写入 outbox/）
# ═══════════════════════════════════════════════════════

def run_simulate_mode():
    from simulate_message import get_instruction
    print("=" * 60)
    print("  飞书 → Claude Code 远程交互系统  [模拟模式]")
    print("=" * 60)
    print()

    instruction, err = get_instruction()
    if err:
        print(f"[失败] {err}")
        sys.exit(1)

    print(f"[指令] {instruction}")
    result = process_instruction(instruction)

    # 结果写入 outbox/
    result_file = simulate_wechat_send(result, instruction)
    print(f"[结果] 已写入：{result_file}")
    print("=" * 60)


# ═══════════════════════════════════════════════════════
# 飞书模式
# ═══════════════════════════════════════════════════════

def _feishu_callback(content: str, sender: str, message_id: str):
    """飞书 Webhook 收到消息时的回调"""
    if not content.startswith("/run"):
        return
    instruction = content[4:].strip()
    result = process_instruction(instruction, sender)

    # 回复结果（分段发送，避免超长）
    from feishu_listener import reply_text
    # 飞书单条消息限制 2048 字符，超长分段
    max_len = 2000
    for i in range(0, len(result), max_len):
        chunk = result[i:i + max_len]
        reply_text(message_id, chunk)


def run_feishu_webhook_mode():
    from feishu_listener import start_webhook, _WebhookHandler
    print("=" * 60)
    print("  飞书 → Claude Code 远程交互系统  [Webhook 模式]")
    print("=" * 60)
    print()

    # 设置回调
    _WebhookHandler.listener_callback = _feishu_callback

    # 启动 Webhook 服务器（阻塞）
    start_webhook(
        on_instruction=None,  # 用 listener_callback 代替
        app_secret=os.environ.get("FEISHU_APP_SECRET", ""),
        port=8080,
    )


def run_feishu_poll_mode(chat_id: str):
    from feishu_listener import poll_messages
    print("=" * 60)
    print("  飞书 → Claude Code 远程交互系统  [轮询模式]")
    print("=" * 60)
    print()

    def on_instruction(content: str, msg_id: str):
        if not content.startswith("/run"):
            return
        instruction = content[4:].strip()
        result = process_instruction(instruction, "feishu_poll")

        # 回复结果
        from feishu_listener import reply_text
        reply_text(msg_id, result[:2000])

    poll_messages(chat_id, on_instruction)


# ═══════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="飞书/飞书 → Claude Code 远程交互系统")
    parser.add_argument(
        "--platform",
        choices=["simulate", "feishu"],
        default="simulate",
        help="运行平台：simulate（模拟）/ feishu（飞书）",
    )
    parser.add_argument(
        "--mode",
        choices=["webhook", "poll"],
        default="webhook",
        help="飞书模式：webhook（需配置回调）/ poll（轮询）",
    )
    parser.add_argument(
        "--chat-id",
        default="",
        help="飞书轮询模式的 chat_id（以 oc_ 开头）",
    )
    args = parser.parse_args()

    if args.platform == "simulate":
        run_simulate_mode()
    elif args.platform == "feishu":
        if args.mode == "webhook":
            run_feishu_webhook_mode()
        else:
            if not args.chat_id:
                print("❌ 轮询模式需要 --chat-id 参数（飞书聊天 ID，以 oc_ 开头）")
                print("   获取方式：飞书后台 → 群聊/私聊 → 复制 URL 中的 chat_id")
                sys.exit(1)
            run_feishu_poll_mode(args.chat_id)

if __name__ == "__main__":
    main()
