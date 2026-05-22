#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话上下文同步模块 — 飞书 ↔ 本地 Claude 双向状态共享
=====================================================
职责:
  1. 持久化会话摘要到 .claude/shared_sessions/{chat_id}.json
  2. 本地 Claude 可读取上下文文件恢复会话
  3. 飞书桥接可写入更新，本地端可读取
  4. 提供紧凑的飞书消息格式（做了什么 + 下一步）

文件结构:
  .claude/shared_sessions/
  ├── {chat_id}.json      ← 会话状态
  ├── {chat_id}_full.md   ← 完整对话历史（Claude 可读）
  └── inbox/              ← 待处理消息（本地 Claude 监听用）
"""

import json
import os
import time
import re
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger("session.context")

SESSIONS_DIR = Path.home() / ".claude" / "shared_sessions"
INBOX_DIR = SESSIONS_DIR / "inbox"


def ensure_dirs():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)


class SessionContext:
    """单个飞书会话的持久化状态"""

    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.state_file = SESSIONS_DIR / f"{chat_id}.json"
        self.full_file = SESSIONS_DIR / f"{chat_id}_full.md"
        ensure_dirs()
        self._load()

    def _load(self):
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {
                "chat_id": self.chat_id,
                "created": datetime.now().isoformat(),
                "last_activity": None,
                "total_tasks": 0,
                "last_instruction": "",
                "last_result_summary": "",
                "files_created": [],
                "files_modified": [],
                "active_agent": None,
                "pending_actions": [],
            }

    def _save(self):
        self.data["last_activity"] = datetime.now().isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def record_task(self, instruction: str, result: str):
        """记录一次任务执行"""
        self.data["total_tasks"] += 1
        self.data["last_instruction"] = instruction[:200]
        self.data["last_result_summary"] = compact_reply(result, instruction)

        # 提取文件变更
        created = re.findall(r'(?:创建|写入|saved|written|创建文件)\s*[：:]*\s*(.+?\.\w+)', result, re.I)
        modified = re.findall(r'(?:修改|修改了|changed|updated)\s*[：:]*\s*(.+?\.\w+)', result, re.I)
        self.data["files_created"] = list(set(created))[-5:]
        self.data["files_modified"] = list(set(modified))[-5:]

        self._save()

        # 同步写入完整对话历史（追加）
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.full_file, "a", encoding="utf-8") as f:
            f.write(f"\n## {ts} — 飞书指令\n\n> {instruction[:300]}\n\n")
            f.write(f"{result[:2000]}\n\n---\n")

    def record_browse(self, action: str, url: str = ""):
        """记录一次浏览器操作"""
        self.data["last_instruction"] = action[:200]
        if url:
            self.data["pending_actions"].append({"type": "browse", "url": url, "time": datetime.now().isoformat()})
        self.data["total_tasks"] += 1
        self._save()

    def get_summary(self) -> str:
        """返回飞书版精简摘要"""
        d = self.data
        parts = []
        if d["total_tasks"] > 0:
            parts.append(f"📊 已执行 {d['total_tasks']} 个任务")
        if d["last_instruction"]:
            parts.append(f"📝 最近: {d['last_instruction'][:80]}")
        if d["files_created"]:
            parts.append(f"📁 新文件: {', '.join(d['files_created'][:3])}")
        if d["files_modified"]:
            parts.append(f"✏️ 修改: {', '.join(d['files_modified'][:3])}")
        if d["active_agent"]:
            parts.append(f"🤖 角色: {d['active_agent']}")
        return "\n".join(parts) if parts else "暂无会话记录"

    def get_full_context(self) -> str:
        """返回完整 Claude 可读上下文"""
        if self.full_file.exists():
            return self.full_file.read_text(encoding="utf-8")
        return ""

    def set_agent(self, name: str):
        self.data["active_agent"] = name
        self._save()

    def add_pending(self, action: str):
        self.data["pending_actions"].append({
            "action": action, "time": datetime.now().isoformat()
        })
        self._save()

    def clear_pending(self):
        self.data["pending_actions"] = []
        self._save()


# ── Claude 输出 → 飞书摘要 ────────────────────────

def compact_reply(claude_output: str, instruction: str = "", max_len: int = 800) -> str:
    """将 Claude 的完整输出压缩为飞书友好的精简回复

    格式:
      ✅ 已完成: <一句话总结>
      📁 涉及文件: <列表>
      👉 下一步: <建议>
    """
    if not claude_output or len(claude_output) < 10:
        return claude_output or "执行完成，无输出。"

    # 提取关键信息
    lines = claude_output.strip().split("\n")

    # 取前 3 行非空行作为摘要
    meaningful = [l for l in lines if l.strip() and not l.startswith("```")][:5]
    summary = " ".join(meaningful)[:200]

    # 提取文件名
    files = re.findall(r'[`\*]?([\w./-]+\.(?:py|js|ts|json|md|txt|yaml|yml|html|css|sh|bat))[`\*]?', claude_output)
    files = list(set(files))[:5]

    # 检测是否有代码块
    has_code = "```" in claude_output

    # 构建精简回复
    parts = []

    # 1. 完成声明
    if has_code:
        parts.append("✅ 代码已生成")
    else:
        parts.append("✅ 已完成")

    # 2. 涉及文件
    if files:
        parts.append(f"📁 涉及: {', '.join(files)}")

    # 3. 核心结果（截取关键内容）
    if summary:
        # 去掉 markdown 标记，取关键句
        clean = re.sub(r'[#*`>]', '', summary).strip()
        # 找第一句有意义的话
        sentences = re.split(r'[。.!！?\n]', clean)
        key_sentence = next((s.strip() for s in sentences if len(s.strip()) > 10), clean[:120])
        parts.append(f"📋 {key_sentence[:150]}")

    # 4. 下一步建议
    next_step = _suggest_next(claude_output, instruction)
    if next_step:
        parts.append(f"👉 {next_step}")

    # 5. 如果有更多内容
    if len(claude_output) > max_len * 2:
        parts.append(f"💡 完整结果已保存（{len(claude_output)}字符），回复「详情」查看")

    result = "\n".join(parts)
    return result[:max_len]


def _suggest_next(output: str, instruction: str) -> str:
    """根据输出内容推断下一步建议"""
    if re.search(r'(错误|error|失败|fail|异常|exception)', output, re.I):
        return "修复上述错误后可继续"
    if re.search(r'(测试|test|验证)', instruction, re.I) or "```" in output:
        return "可以运行测试验证结果"
    if re.search(r'(设计|架构|方案)', instruction, re.I):
        return "确认方案后可开始实现"
    if re.search(r'(审查|review|检查)', instruction, re.I):
        return "审查完成，可继续开发"
    return "如需修改请直接说明"


def browser_reply(action: str, result: dict, url: str = "") -> str:
    """浏览器操作的飞书精简回复"""
    parts = []
    if action == 'screenshot':
        parts.append(f"📸 截图完成")
    elif action == 'navigate':
        parts.append(f"🌐 已打开 {url[:60]}")
    elif action == 'tabs':
        return result.get("text", "")  # 标签页列表保持原样
    elif action == 'analyze':
        parts.append("🔍 页面分析完成")
    elif action == 'snapshot':
        parts.append(f"📄 页面结构已提取")
    else:
        parts.append(f"✅ {action} 完成")

    if result.get("title"):
        parts.append(f"📋 {result['title'][:100]}")
    if result.get("screenshot_path"):
        parts.append(f"📁 截图已保存")
    parts.append("👉 可继续操作或分析页面内容")

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ensure_dirs()

    # 测试1: SessionContext
    ctx = SessionContext("test-chat")
    ctx.record_task("写一个冒泡排序", "```python\ndef bubble_sort(arr):\n    ...\n```\n创建文件: bubble_sort.py")
    print("=== 会话摘要 ===")
    print(ctx.get_summary())
    print()

    # 测试2: 精简回复
    claude_out = (
        "```python\ndef quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n"
        "    pivot = arr[0]\n    left = [x for x in arr[1:] if x <= pivot]\n"
        "    right = [x for x in arr[1:] if x > pivot]\n"
        "    return quicksort(left) + [pivot] + quicksort(right)\n```\n\n"
        "这个实现使用了列表推导式和递归。时间复杂度 O(n log n)，最坏 O(n²)。\n"
        "已创建 quick_sort.py 文件。"
    )
    reply = compact_reply(claude_out, "写一个快速排序")
    print("=== 精简回复 ===")
    print(reply)
    print()

    # 测试3: 浏览器回复
    print("=== 浏览器回复 ===")
    print(browser_reply("screenshot", {"title": "百度一下"}, "https://baidu.com"))
    print()
    print(browser_reply("analyze", {"title": "GitHub Repo"}, ""))

    print("\n全部测试完成。")
