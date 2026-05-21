#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书交互式卡片工具模块
提供卡片构建与发送能力，可被 run_feishu_poll.py 调用
"""

import json
import requests
import os
import logging

log = logging.getLogger("feishu.cards")

# 从 run_feishu_poll 导入依赖（延迟导入，避免循环）
def _get_base_url():
    """延迟获取 BASE_URL"""
    from run_feishu_poll import BASE_URL
    return BASE_URL


def _get_token():
    """延迟调用 get_token"""
    from run_feishu_poll import get_token
    return get_token()


# ── 卡片模板 ───────────────────────────────────

def build_processing_card(task_desc=""):
    """构建「正在处理中」状态卡片"""
    desc = task_desc[:50] + "..." if len(task_desc) > 50 else task_desc
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": "⏳ 正在处理中"},
            "template": "blue",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": f"已收到任务，Claude Code 正在分析中...\n\n> {desc}" if desc else "已收到任务，Claude Code 正在分析中..."}
            ]
        }
    }


def build_agent_activated_card(agent_name, domain, description):
    """构建「角色已激活」确认卡片"""
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": f"✅ 角色已激活"},
            "template": "green",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": f"**{agent_name}** （{domain}）\n\n{description}"}
            ]
        }
    }


def build_status_card(status_text):
    """构建「系统状态」卡片"""
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": "📊 系统运行状态"},
            "template": "purple",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": status_text.replace("\n", "\n\n")}
            ]
        }
    }


def build_error_card(error_msg):
    """构建「错误提示」卡片"""
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": "❌ 执行出错"},
            "template": "red",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": f"```\n{error_msg[:500]}\n```"}
            ]
        }
    }


# ── 卡片发送 ────────────────────────────────────

def send_card(message_id, card, reply_prefix=None):
    """
    回复飞书交互式卡片
    :param message_id: 要回复的消息 ID
    :param card: 卡片字典（build_xxx_card 构建）
    :param reply_prefix: 可选，在卡片前附加的纯文本前缀
    :return: 是否发送成功
    """
    token = _get_token()
    if not token:
        log.warning("[Card] token 获取失败，无法发送卡片")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 飞书卡片通过 msg_type=interactive 发送
    # 注意：content 字段是必需的，需要是 JSON 字符串
    payload = {
        "msg_type": "interactive",
        "content": json.dumps(card),
    }

    try:
        base_url = _get_base_url()
        resp = requests.post(
            f"{base_url}/im/v1/messages/{message_id}/reply",
            headers=headers,
            json=payload,
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            log.error(f"[Card] 发送失败：{data}")
            # 降级：尝试用纯文本重发
            return _fallback_text(message_id, card, reply_prefix)
        log.info("[Card] 卡片已发送")
        return True
    except Exception as e:
        log.error(f"[Card] 发送异常：{e}")
        return False


def _fallback_text(message_id, card, reply_prefix=None):
    """卡片发送失败时降级为纯文本"""
    try:
        from run_feishu_poll import reply_message
        # 从卡片中提取文本内容
        elements = card.get("body", {}).get("elements", [])
        text_parts = []
        for el in elements:
            if el.get("tag") == "markdown":
                text_parts.append(el.get("content", ""))
        text = "\n".join(text_parts)
        if reply_prefix:
            text = reply_prefix + "\n" + text
        reply_message(message_id, text)
        log.info("[Card] 已降级为纯文本发送")
        return True
    except Exception as e:
        log.error(f"[Card] 降级发送也失败：{e}")
        return False


# ── 便捷接口 ───────────────────────────────────

def send_processing(message_id, task_desc=""):
    """发送「正在处理中」卡片"""
    card = build_processing_card(task_desc)
    return send_card(message_id, card)


def send_agent_activated(message_id, agent_name, domain, description):
    """发送「角色已激活」卡片"""
    card = build_agent_activated_card(agent_name, domain, description)
    return send_card(message_id, card)


def send_status(message_id, status_text):
    """发送「系统状态」卡片"""
    card = build_status_card(status_text)
    return send_card(message_id, card)


if __name__ == "__main__":
    # 独立测试
    print("飞书卡片模块 — 独立测试模式")
    print("请通过 run_feishu_poll.py 调用此模块")
