#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书 → Claude Code 远程智能调度系统 v3.1
==============================================
新增功能（v3.1）：
  • 配置外置化（config.json 统一管理）
  • 上下文记忆机制（多轮对话 / 任务接续）
  • 任务实时状态推送（"正在处理中..."）
"""

import os
import sys
import time
import json
import re
import logging
import shutil
import subprocess
import requests
import feishu_cards as fc   # 飞书交互式卡片模块
import skill_engine as se   # Skills引擎：指令精简+Token优化+任务分发
import glob as glob_mod
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── 路径常量 ──────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE   = os.path.join(PROJECT_DIR, "feishu_poll.log")
AGENTS_DIR = os.path.expanduser(r"~/.claude/agents")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")

# ── 日志配置（轮转：5个文件 × 5MB）────────────────────
log = logging.getLogger("feishu")
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_rh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
_rh.setFormatter(_fmt)
_ch = logging.StreamHandler(sys.stdout)
_ch.setFormatter(_fmt)
log.addHandler(_rh)
log.addHandler(_ch)

# ── 配置文件加载 ───────────────────────────────────
def _deep_merge(default, override):
    result = dict(default)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def load_config():
    """从 config.json 加载配置，缺失项使用默认值"""
    defaults = {
        "feishu": {
            "app_id": "cli_xxxxxxxxxxxxx",
            "app_secret": "YOUR_SECRET_HERE",
            "chat_id": "oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "base_url": "https://open.feishu.cn/open-apis",
        },
        "claude": {
            "cli_candidates": [
                os.path.expandvars(r"%APPDATA%\npm\claude.cmd"),
                os.path.expandvars(r"%APPDATA%\npm\claude"),
                "claude",
            ],
            "timeout": 300,
            "default_model": "haiku",
            "complex_model": "opus",
        },
        "rag": {
            "kb_path": "instruction_kb.json",
            "db_path": "rag_db",
            "similarity_threshold": 0.65,
            "enabled": True,
        },
        "polling": {"interval": 2, "page_size": 10, "max_seen_ids": 500},
        "logging": {"file": "feishu_poll.log", "max_bytes": 5242880, "backup_count": 5, "level": "INFO"},
        "conversation": {"max_history": 20, "max_age_minutes": 30},
        "status": {"sending_processing_message": True},
    }
    if not os.path.isfile(CONFIG_FILE):
        log.warning(f"[Config] {CONFIG_FILE} 不存在，使用默认配置")
        return defaults
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg = _deep_merge(defaults, user_cfg)
        log.info(f"[Config] 已加载：{CONFIG_FILE}")
        return cfg
    except Exception as e:
        log.error(f"[Config] 加载失败：{e}，使用默认配置")
        return defaults

CONFIG = load_config()

# ── 飞书配置（从 config.json 读取）──────────────
APP_ID     = CONFIG["feishu"]["app_id"]
APP_SECRET = CONFIG["feishu"]["app_secret"]
CHAT_ID    = CONFIG["feishu"]["chat_id"]
BASE_URL   = CONFIG["feishu"]["base_url"]

# ── Token 管理 ──────────────────────────────────────────
_token_cache = {"token": None, "expire": 0}

def get_token():
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expire"] - 60:
        return _token_cache["token"]
    log.info("[Token] 正在获取 tenant_access_token ...")
    try:
        resp = requests.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": APP_ID, "app_secret": APP_SECRET},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            log.error(f"[Token] 获取失败：{data}")
            return None
        _token_cache["token"] = data["tenant_access_token"]
        _token_cache["expire"] = now + data.get("expire", 7200)
        log.info("[Token] 获取成功")
        return _token_cache["token"]
    except Exception as e:
        log.error(f"[Token] 异常：{e}")
        return None

# ── RAG 模块 ───────────────────────────────────────────
try:
    from rag_module import RAGEngine
    RAG_AVAILABLE = True
    log.info("[RAG] 模块加载成功")
except ImportError:
    RAG_AVAILABLE = False
    RAGEngine = None
    log.info("[RAG] 模块未安装，跳过 RAG 解析")

# ═══════════════════════════════════════════════════════
#  Agent 角色调度系统
# ═══════════════════════════════════════════════════════

def _extract_core_rules(body):
    """从Agent body中智能提取核心行为规则，大幅精简Token消耗"""
    m = re.search(r'(?:##\s*🔧\s*Critical Rules.*?)(?=##\s|\Z)', body, re.DOTALL | re.I)
    if m and len(m.group(0)) > 80:
        return m.group(0).strip()[:800]
    m = re.search(r'(?:##\s*🎯\s*Your Core Mission.*?)(?=##\s|\Z)', body, re.DOTALL | re.I)
    if m and len(m.group(0)) > 80:
        return m.group(0).strip()[:800]
    m = re.search(r'(?:##\s*🧠\s*Your Identity.*?)(?=##\s|\Z)', body, re.DOTALL | re.I)
    if m:
        return m.group(0).strip()[:600]
    return body[:600]


class ConversationManager:
    """管理多轮对话上下文，支持跨消息记忆"""

    def __init__(self, max_history=20, max_age_minutes=30):
        self.history = []       # list of {"role": "user"/"assistant", "content": str, "time": float}
        self.max_history = max_history
        self.max_age = max_age_minutes * 60
        self.last_user = None   # 最近一次用户消息（用于"接着改"类指令）

    def _prune(self):
        """清理过期和超量的历史记录"""
        now = time.time()
        # 去掉过期记录
        self.history = [h for h in self.history if now - h["time"] < self.max_age]
        # 保留最近 max_history 条
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def add_user(self, text):
        self._prune()
        self.last_user = text
        self.history.append({"role": "user", "content": text, "time": time.time()})

    def add_assistant(self, text):
        self._prune()
        # 截断过长回复，避免上下文膨胀
        trimmed = text[:2000] if len(text) > 2000 else text
        self.history.append({"role": "assistant", "content": trimmed, "time": time.time()})

    def get_context(self):
        """返回格式化的上下文字符串，供 Claude 使用"""
        self._prune()
        if not self.history:
            return ""
        lines = ["[对话历史]", ""]
        for h in self.history:
            label = "用户" if h["role"] == "user" else "助手"
            lines.append(f"{label}：{h['content']}")
        lines += ["", "[当前指令]"]
        return "\n".join(lines)

    def has_context(self):
        return len(self.history) > 0

    def clear(self):
        self.history.clear()
        self.last_user = None

    def detect_continuation(self, text):
        """检测是否是接续指令（如'接着改'、'加注释'、'再优化一下'）"""
        patterns = [
            r'接着', r'继续', r'然后', r'再',
            r'加.*注释', r'加.*文档', r'优化', r'改进',
            r'还有', r'另外', r'顺便',
            r'上一个', r'刚才', r'前面',
        ]
        return any(re.search(p, text) for p in patterns)


class AgentManager:
    """管理 Agent 角色的加载、检索、激活"""

    def __init__(self):
        self.agents = {}
        self.active_agent = None
        self.start_time = datetime.now()
        self._load_all()

    def _load_all(self):
        if not os.path.isdir(AGENTS_DIR):
            log.warning(f"[Agent] 目录不存在：{AGENTS_DIR}")
            return
        pattern = os.path.join(AGENTS_DIR, "**", "*.md")
        files = glob_mod.glob(pattern, recursive=True)
        for fp in files:
            try:
                info = self._parse_agent_file(fp)
                if info:
                    self.agents[info["name"].lower()] = info
            except Exception as e:
                log.warning(f"[Agent] 解析失败 {fp}：{e}")
        log.info(f"[Agent] 已加载 {len(self.agents)} 个角色")

    def _parse_agent_file(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
        if not fm_match:
            return None
        fm_text = fm_match.group(1)
        body = fm_match.group(2).strip()
        name = desc = ""
        for line in fm_text.split("\n"):
            line = line.strip()
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                desc = line.split(":", 1)[1].strip()
        if not name:
            return None
        body_short = _extract_core_rules(body)
        domain = os.path.basename(os.path.dirname(filepath))
        return {"name": name, "file": filepath, "description": desc, "body": body_short, "domain": domain}

    def list_agents(self):
        groups = {}
        for name, info in sorted(self.agents.items()):
            d = info["domain"]
            groups.setdefault(d, []).append(f"  {info['name']} — {info['description'][:60]}")
        lines = []
        for domain in sorted(groups.keys()):
            lines.append(f"【{domain}】（{len(groups[domain])}个）")
            lines.extend(groups[domain])
        return "\n".join(lines)

    def search(self, keyword):
        kw = keyword.lower().strip()
        if not kw or len(kw) < 2:
            return None
        if kw in self.agents:
            return self.agents[kw]
        matches = [(len(name), info) for name, info in self.agents.items() if kw in name]
        if matches:
            matches.sort()
            return matches[0][1]
        kw_words = kw.split()
        if len(kw_words) >= 2:
            for name, info in self.agents.items():
                if all(w in name for w in kw_words):
                    return info
        return None

    def activate(self, keyword):
        info = self.search(keyword)
        if info:
            self.active_agent = info["name"].lower()
            return True, f"已激活角色：{info['name']}（{info['domain']}）\n{info['description']}"
        return False, f"未找到匹配角色「{keyword}」。\n可用 /list agents 查看全部角色。"

    def get_active_context(self):
        if not self.active_agent or self.active_agent not in self.agents:
            return ""
        info = self.agents[self.active_agent]
        return f"[Active Role: {info['name']} — {info['description']}]\n\n{info['body']}"

    def status(self):
        uptime = datetime.now() - self.start_time
        agent_name = self.agents[self.active_agent]["name"] if self.active_agent and self.active_agent in self.agents else "无"
        return (
            f"运行状态：正常运行\n"
            f"运行时长：{str(uptime).split('.')[0]}\n"
            f"当前角色：{agent_name}\n"
            f"可用角色：{len(self.agents)} 个\n"
            f"RAG 状态：{'启用' if RAG_AVAILABLE else '未安装'}"
        )


# ═══════════════════════════════════════════════════════
#  智能消息分段引擎
# ═══════════════════════════════════════════════════════

def smart_chunk(text, max_len=1800):
    if len(text) <= max_len:
        return [(text, 1, 1)]
    paragraphs = re.split(r'(\n{2,})', text)
    merged = []
    i = 0
    while i < len(paragraphs):
        if i + 1 < len(paragraphs) and re.match(r'^\n{2,}$', paragraphs[i + 1]):
            merged.append(paragraphs[i] + paragraphs[i + 1])
            i += 2
        else:
            merged.append(paragraphs[i])
            i += 1
    chunks = []
    current = ""
    for para in merged:
        if len(current) + len(para) <= max_len:
            current += para
        else:
            if current.strip():
                chunks.append(current)
            if len(para) > max_len:
                for j in range(0, len(para), max_len):
                    chunks.append(para[j:j + max_len])
                current = ""
            else:
                current = para
    if current.strip():
        chunks.append(current)
    total = len(chunks)
    return [(c, i + 1, total) for i, c in enumerate(chunks)]


# ═══════════════════════════════════════════════════════
#  消息发送（含智能分段）
# ═══════════════════════════════════════════════════════

def reply_message(message_id, text, reply_prefix=None):
    """回复飞书消息，自动分段；reply_prefix 为状态提示前缀"""
    # 防御：确保 reply_prefix 是字符串
    if reply_prefix is not None and not isinstance(reply_prefix, str):
        reply_prefix = str(reply_prefix)
    token = get_token()
    if not token:
        return False
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    chunks = smart_chunk(text)
    success = True
    for chunk_text, idx, total in chunks:
        prefix = f"[{idx}/{total}]\n" if total > 1 else ""
        if reply_prefix and idx == 1:
            prefix = reply_prefix + "\n" + prefix
        payload = {"msg_type": "text", "content": json.dumps({"text": prefix + chunk_text})}
        try:
            resp = requests.post(
                f"{BASE_URL}/im/v1/messages/{message_id}/reply",
                headers=headers, json=payload, timeout=15,
            )
            data = resp.json()
            if data.get("code") != 0:
                log.error(f"[Reply] 失败：{data}")
                success = False
            else:
                log.info(f"[Reply] 分段 {idx}/{total} 已发送（{len(chunk_text)} 字符）")
        except Exception as e:
            log.error(f"[Reply] 异常：{e}")
            success = False
    return success


# ═══════════════════════════════════════════════════════
#  Claude CLI 调用（含上下文记忆）
# ═══════════════════════════════════════════════════════

def _find_claude():
    """多路径探测 Claude CLI（路径来自 config.json）"""
    candidates = CONFIG["claude"]["cli_candidates"]
    for c in candidates:
        expanded = os.path.expandvars(c)
        if os.path.exists(expanded) or shutil.which(expanded):
            return expanded
    return "claude"

def _assess_complexity(instruction, agent_context=""):
    text = instruction.lower()
    has_agent = bool(agent_context)
    complex_patterns = [
        r'(设计|架构|重构|审查|review|安全|security|优化|性能|performance)',
        r'(系统|system|完整|complete|部署|deploy|数据库|database|schema)',
        r'(全部|所有|整个|整个项目|project|codebase)',
        r'(写|创建|生成|开发|实现).{0,10}(系统|平台|应用|网站|服务|API)',
        r'(?:explain|分析|解释).{0,10}(?:架构|系统|代码库|整体)',
    ]
    score = sum(1 for p in complex_patterns if re.search(p, text))
    if has_agent:
        score += 1
    if len(text) > 200:
        score += 1
    is_complex = score >= 2
    return is_complex, 'opus' if is_complex else 'haiku'

def call_claude(instruction, agent_context="", conversation_context=""):
    """调用 Claude Code CLI，根据任务复杂度自动选择模型；支持对话上下文"""
    claude_cmd = _find_claude()

    # 构建完整 prompt（Agent上下文 + 对话历史 + 当前指令）
    parts = []
    if agent_context:
        parts.append(agent_context)
    if conversation_context:
        parts.append(conversation_context)
    parts.append(f"[User Instruction]\n{instruction}")
    full_prompt = "\n\n".join(parts)

    is_complex, model_tier = _assess_complexity(instruction, agent_context)
    model_flag = ["--model", model_tier] if model_tier != 'haiku' else []

    log.info(f"[Claude] 执行：{instruction[:80]}...")
    log.info(f"[Claude] 模型={model_tier} | Agent={'有' if agent_context else '无'} | 上下文={'有' if conversation_context else '无'} | 复杂度={'高' if is_complex else '低'}")

    try:
        result = subprocess.run(
            [claude_cmd, "-p", full_prompt, "--dangerously-skip-permissions"] + model_flag,
            capture_output=True, text=True, timeout=CONFIG["claude"]["timeout"],
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            log.info(f"[Claude] 成功（{len(output)} 字符）via {model_tier}")
            return output
        else:
            error = result.stderr or result.stdout
            log.error(f"[Claude] 失败（exit={result.returncode}）：{error[:200]}")
            return f"[Claude Code 执行失败]\n退出码：{result.returncode}\n{error}"
    except subprocess.TimeoutExpired:
        log.error("[Claude] 超时")
        return "[Claude Code 执行超时] 任务超过 {} 秒，请简化指令或分阶段执行。".format(CONFIG["claude"]["timeout"])
    except Exception as e:
        log.error(f"[Claude] 异常：{e}")
        return f"[Claude Code 调用异常] {str(e)}"


def call_claude_lean(prompt, model_tier='haiku'):
    """精简Claude调用：直接传入已构建prompt，无额外拼装开销"""
    claude_cmd = _find_claude()
    model_flag = ["--model", model_tier] if model_tier != 'haiku' else []

    log.info(f"[Claude] 执行({model_tier}, {len(prompt)}字)：{prompt[:80]}...")

    try:
        result = subprocess.run(
            [claude_cmd, "-p", prompt, "--dangerously-skip-permissions"] + model_flag,
            capture_output=True, text=True, timeout=CONFIG["claude"]["timeout"],
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            log.info(f"[Claude] 成功（{len(output)} 字符）via {model_tier}")
            return output
        else:
            error = result.stderr or result.stdout
            log.error(f"[Claude] 失败（exit={result.returncode}）：{error[:200]}")
            return f"[Claude Code 执行失败]\n退出码：{result.returncode}\n{error}"
    except subprocess.TimeoutExpired:
        log.error("[Claude] 超时")
        return f"[Claude Code 执行超时]"
    except Exception as e:
        log.error(f"[Claude] 异常：{e}")
        return f"[Claude Code 调用异常] {str(e)}"


# ═══════════════════════════════════════════════════════
#  自然语言智能路由器（v3.1 — 多轮对话 + 状态推送）
# ═══════════════════════════════════════════════════════

AGENT_ALIASES = {
    '代码审查': 'code reviewer', '审查代码': 'code reviewer', 'review': 'code reviewer',
    '后端': 'backend architect', '后端架构': 'backend architect', '后端架构师': 'backend architect',
    '前端': 'frontend developer', '前端开发': 'frontend developer', '前端工程师': 'frontend developer',
    '安全': 'security engineer', '安全工程师': 'security engineer', '安全审查': 'security engineer',
    '测试': 'api tester', '接口测试': 'api tester', 'api测试': 'api tester',
    '性能': 'performance benchmarker', '性能优化': 'performance benchmarker',
    '数据库': 'database optimizer', '数据库优化': 'database optimizer',
    '运维': 'devops automator', 'devops': 'devops automator', '部署': 'devops automator',
    '架构': 'software architect', '架构师': 'software architect',
    '全栈': 'senior developer', '高级开发': 'senior developer',
    '嵌入式': 'embedded firmware engineer', '固件': 'embedded firmware engineer',
    'solidity': 'solidity smart contract engineer', '智能合约': 'solidity smart contract engineer',
    '移动端': 'mobile app builder', '移动开发': 'mobile app builder', 'app开发': 'mobile app builder',
    '技术写作': 'technical writer', '文档': 'technical writer',
    'git': 'git workflow master', 'git工作流': 'git workflow master',
    'sre': 'sre', '可靠性': 'sre', '站点可靠性': 'sre',
    '威胁检测': 'threat detection engineer', '安全检测': 'threat detection engineer',
    '数据工程': 'data engineer', '数据工程师': 'data engineer',
    '产品经理': 'product manager', '产品': 'product manager',
    '趋势': 'trend researcher', '趋势研究': 'trend researcher', '市场研究': 'trend researcher',
    '支持': 'support responder', '客服': 'support responder',
    '法律': 'legal compliance checker', '合规': 'legal compliance checker',
    '财务': 'finance tracker', '金融分析': 'financial analyst',
    '无障碍': 'accessibility auditor', 'a11y': 'accessibility auditor',
    '性能测试': 'performance benchmarker', '压测': 'performance benchmarker',
    '项目管理': 'project shepherd', '项目经理': 'project shepherd',

    "审代码": "code reviewer",
    "检查代码": "code reviewer",
    "质检代码": "code reviewer",
    "后台架构": "backend architect",
    "服务端架构": "backend architect",
    "后端设计": "backend architect",
    "前端页面": "frontend developer",
    "web前端": "frontend developer",
    "UI开发": "frontend developer",
    "安全扫描": "security engineer",
    "安全检查": "security engineer",
    "渗透测试": "security engineer",
    "接口测试": "api tester",
    "API测试": "api tester",
    "压测": "performance benchmarker",
    "性能测试": "performance benchmarker",
    "慢查询优化": "database optimizer",
    "SQL优化": "database optimizer",
    "运维部署": "devops automator",
    "CI/CD": "devops automator",
    "持续集成": "devops automator",
    "系统架构": "software architect",
    "高级工程师": "senior developer",
    "全栈开发": "senior developer",
    "区块链合约": "solidity smart contract engineer",
    "合约审计": "solidity smart contract engineer",
    "安卓开发": "mobile app builder",
    "iOS开发": "mobile app builder",
    "APP开发": "mobile app builder",
    "技术文档": "technical writer",
    "接口文档": "technical writer",
    "Git操作": "git workflow master",
    "版本管理": "git workflow master",
    "可靠性工程": "sre",
    "站点可靠性": "sre",
    "异常检测": "threat detection engineer",
    "入侵检测": "threat detection engineer",
    "数据管道": "data engineer",
    "ETL开发": "data engineer",
    "产品需求": "product manager",
    "PRD": "product manager",
    "市场分析": "trend researcher",
    "行业研究": "trend researcher",
    "UI设计": "ui designer",
    "UX设计": "ux designer",
    "交互设计": "ux designer",
    "视觉设计": "visual designer",
    "论文润色": "academic editor",
    "学术写作": "academic editor",
    "文献综述": "literature reviewer",
    "游戏逻辑": "game designer",
    "关卡设计": "level designer",
    "游戏引擎": "game engine developer",
    "营销文案": "marketing copywriter",
    "SEO优化": "seo specialist",
    "社交媒体": "social media manager",
    "销售话术": "sales copywriter",
    "客户跟进": "account executive",
    "客服回复": "support responder",
    "用户支持": "support responder",
    "合规检查": "legal compliance checker",
    "法律风险": "legal compliance checker",
    "财务报表": "financial analyst",
    "投资分析": "financial analyst",
    "无障碍审计": "accessibility auditor",
    "A11Y检查": "accessibility auditor",
    "项目排期": "project shepherd",
    "迭代管理": "project shepherd",
    "AR开发": "ar developer",
    "VR开发": "vr developer",
    "空间计算": "spatial computing engineer",
    "写一个": "senior developer",
    "实现一个": "senior developer",
    "帮我做": "senior developer",
}

CHAT_FILTER = re.compile(
    r'^[好的嗯哦啊哈呀啦吧呢么嘿嗨呵嗐]{1,4}$|'
    r'^(谢谢|多谢|感谢|ok|OK|Ok|收到|明白|懂了|知道了|好的|可以|行|对|是的|没错)$|'
    r'^(你好|您好|hi|hello|hey|在吗|在不|在不在|有人吗|能收到|收到了吗|测试|test|测试消息)$|'
    r'^[.。,，!！?？…~～]+$'
)

NON_TECH_PATTERNS = re.compile(
    r'^(你好|您好|hi|hello|hey|在吗|在不|有人吗|能收到|收到|测试|早上好|晚上好|中午好|'
    r'晚安|再见|拜拜|谢谢|不客气|辛苦了|加油|好的|收到|明白|懂了|知道了|'
    r'你有什么|你能做|你有哪些|你的功能|你可以|你是谁|你是做什么|介绍.*自己|'
    r'怎么用|如何使用|帮助|help)'
)

TECH_KEYWORDS = re.compile(
    r'写|代码|程序|函数|算法|排序|爬虫|API|接口|数据库|SQL|前端|后端|页面|网站|'
    r'Python|Java|Go|Rust|JS|HTML|CSS|React|Vue|Node|部署|配置|安装|'
    r'优化|重构|调试|debug|bug|测试|编译|构建|设计|架构|实现|开发|创建|生成|'
    r'修复|改|检查|审查|review|翻译|解释|分析|转换|运行|执行|命令|脚本'
)

MANAGE_PATTERNS = [
    (re.compile(r'(列出|查看|看看|显示|展示|有哪些|什么|多少).*(角色|agent|可用|所有)', re.I), 'list'),
    (re.compile(r'(角色|agent).*(列表|清单|有哪些|全部)', re.I), 'list'),
    (re.compile(r'^(list|show|what).*agent', re.I), 'list'),
    (re.compile(r'(有什么|有哪些).*(角色|agent|人|用的)', re.I), 'list'),
    (re.compile(r'(现在|当前|目前).*(状态|情况|怎么样|是什么|谁|哪个|啥)', re.I), 'status'),
    (re.compile(r'(运行|工作).*(状态|怎么样|正常)', re.I), 'status'),
    (re.compile(r'(激活|设置|使用).*(的是|哪个|什么|啥)', re.I), 'status'),
    (re.compile(r'^(status|状态)$', re.I), 'status'),
    (re.compile(r'(激活|切换|换成|改为|启用|转成|变成|设置)\s*(到|成)?\s*.{1,20}(角色|模式|agent)', re.I), 'activate'),
    (re.compile(r'^(activate|switch|change)\s', re.I), 'activate'),
    (re.compile(r'(用|使用|以|让|叫|请).*(角色|模式|身份|agent).*(用|使用|以|做|帮|干活|处理|执行)', re.I), 'agent_task'),
]

AGENT_REF_PATTERNS = [
    re.compile(r'(?:用|使用|以|让|叫|请|通过|切换到?|换成|激活|启用)\s*[\'"【「]?\s*([a-zA-Z一-鿿\s]+?)\s*[\'"】」]?\s*(?:角色|模式|身份|agent|来)?\s*(?:帮|做|处理|执行|写|干|操作|运行|分析)', re.I),
    re.compile(r'(?:切换|换成|激活|启用|改为)\s*[到成]?\s*[\'"【「]?\s*([a-zA-Z一-鿿\s]+?)\s*[\'"】」]?\s*(?:角色|模式|身份|agent)?\s*$', re.I),
    re.compile(r'^(?:用|使用|以)\s*[\'"【「]?\s*([a-zA-Z一-鿿\s]+?)\s*[\'"】」]?\s*(?:角色|模式|身份|agent|来)\s+(.+)', re.I),
]


class SmartRouter:
    def __init__(self, agents, rag):
        self.routes_handled = 0
        self.agents = agents
        self.rag = rag
        self.mode = "claude"  # "workbuddy" | "claude"
        self.conv = ConversationManager(
            max_history=CONFIG["conversation"]["max_history"],
            max_age_minutes=CONFIG["conversation"]["max_age_minutes"],
        )

    def route(self, text, message_id):
        text = text.strip()
        if not text:
            return None, False

        if len(text) <= 5 and CHAT_FILTER.match(text):
            log.info(f"[路由] 过滤闲聊：{text}")
            return None, False

        # 模式切换指令
        mode_m = re.match(r'^(?:/)?mode\s+(workbuddy|claude|wb|c)\s*$', text, re.I)
        if mode_m:
            target = mode_m.group(1).lower()
            if target in ('wb', 'workbuddy'):
                self.mode = "workbuddy"
                return f"已切换至 WorkBuddy 模式（轻量对话，低Token消耗）", True
            else:
                self.mode = "claude"
                return f"已切换至 Claude 深度处理模式（Agent调度+RAG增强）", True

        # 内置自答（系统能力类问题，双模式均跳过Claude，零Token）
        builtin = self._try_builtin_answer(text)
        if builtin:
            return builtin, True

        # WorkBuddy 模式下，非编程类简单问题也跳过 Claude
        if self.mode == "workbuddy" and not TECH_KEYWORDS.search(text):
            if len(text) < 30:
                return f"[WorkBuddy 轻量模式]\n收到你的消息，但我只处理编程相关任务。\n如需深度对话请发送 /mode claude", True

        agent_info, extracted_agent_name, clean_text = self._extract_agent_ref(text)
        intent = self._classify_intent(text, clean_text, agent_info)
        log.info(f"[路由] 意图={intent} | Agent={'有' if agent_info else '无'} | 模式={self.mode} | 输入={text[:60]}")

        if intent == 'list':
            return self._handle_list(), True
        elif intent == 'status':
            return self._handle_status(message_id), True
        elif intent == 'activate':
            return self._handle_activate(text, message_id), True
        elif intent == 'agent_task':
            return self._handle_task(clean_text, agent_info, message_id, text)
        elif intent == 'task':
            current_agent = self.agents.get_active_context()
            if agent_info:
                return self._handle_task(clean_text, agent_info, message_id, text)
            else:
                return self._handle_task(clean_text, None, message_id, text)
        else:
            log.info(f"[路由] 未明确分类，兜底作为任务处理")
            return self._handle_task(text, None, message_id, text)

    def _try_builtin_answer(self, text):
        """WorkBuddy模式下对系统类问题直接回答，零Token消耗"""
        t = text.strip().lower()
        # 能力/自我介绍类
        if re.search(r'(你是谁|你是做什么|你能做|你有哪些功能|你的能力|介绍一下自己)', t):
            return ("我是飞书→ClaudeCode 远程编程助手。\n\n"
                    "当前模式：WorkBuddy（轻量对话）\n"
                    "发送 /mode claude 可切换深度处理模式。\n\n"
                    "我能帮你：\n"
                    "• 写代码、调试、审查\n"
                    "• 设计架构、优化性能\n"
                    "• 管理Agent角色（226个专业角色）\n"
                    "• 自然语言自由输入，无需记命令"), True
        # 帮助类
        if re.search(r'(帮助|help|怎么用|如何使用|有什么命令)', t):
            return ("使用方式（自然语言，无需格式）：\n\n"
                    "• \"帮我写个快速排序\" → 执行编程任务\n"
                    "• \"用代码审查帮我看代码\" → 指定Agent执行\n"
                    "• \"切换到后端架构师\" → 激活Agent角色\n"
                    "• \"现在有哪些角色\" → 查看全部Agent\n"
                    "• \"/mode claude\" → 切换深度模式\n"
                    "• \"/mode workbuddy\" → 切换轻量模式\n\n"
                    f"当前模式：{self.mode}"), True
        return None

    # ── 内部方法 ─────────────────────────────────────

    def _extract_agent_ref(self, text):
        for pattern in AGENT_REF_PATTERNS:
            m = pattern.search(text)
            if m:
                candidate = m.group(1).strip()
                if len(candidate) >= 2:
                    info = self._match_agent(candidate)
                    if info:
                        clean = text[:m.start()] + text[m.end():]
                        if m.lastindex and m.lastindex >= 2:
                            try:
                                clean = m.group(2).strip()
                            except IndexError:
                                pass
                        clean = re.sub(r'\s+', ' ', clean).strip('.。,，!！?？\s')
                        if len(clean) < 3:
                            clean = text
                        return info, candidate, clean
        for alias, agent_key in AGENT_ALIASES.items():
            if alias in text:
                if agent_key in self.agents.agents:
                    clean = text.replace(alias, '').strip()
                    clean = re.sub(r'^(用|使用|以|让|叫|请|的|来|帮我?|给我|一下|角色|模式|身份)\s*', '', clean)
                    clean = re.sub(r'\s*(帮我?|给我|一下|吧|吗|呢|吗|好不好|可以吗)\s*$', '', clean)
                    clean = clean.strip('.。,，!！?？\s')
                    if len(clean) < 3:
                        clean = text
                    return self.agents.agents[agent_key], alias, clean
        text_lower = text.lower()
        for name, info in self.agents.agents.items():
            if len(name) > 4 and name in text_lower:
                clean = text_lower.replace(name, '').strip()
                clean = re.sub(r'^(用|使用|以|让|叫|请|的|来|帮我?)\s*', '', clean)
                clean = clean.strip('.。,，!！?？\s')
                if len(clean) < 3:
                    clean = text
                return info, name, clean
        return None, None, text

    def _match_agent(self, keyword):
        kw = keyword.strip().lower()
        if not kw or len(kw) < 2:
            return None
        if kw in AGENT_ALIASES:
            key = AGENT_ALIASES[kw]
            return self.agents.agents.get(key)
        if kw in self.agents.agents:
            return self.agents.agents[kw]
        matches = [(len(name), info) for name, info in self.agents.agents.items() if kw in name]
        if matches:
            matches.sort()
            return matches[0][1]
        kw_words = kw.split()
        if len(kw_words) >= 2:
            for name, info in self.agents.agents.items():
                if all(w in name for w in kw_words):
                    return info
        return None

    def _classify_intent(self, text, clean_text, agent_info):
        for pattern, intent in MANAGE_PATTERNS:
            if pattern.search(text):
                return intent
        if len(text) <= 8:
            if any(w in text for w in ['状态', 'status', '怎么样']):
                return 'status'
            if any(w in text for w in ['角色', 'agent', '列表']):
                return 'list'
        if agent_info and (len(clean_text) < 4 or clean_text == text):
            return 'activate'
        if agent_info and len(clean_text) >= 4:
            return 'agent_task'
        return 'task'

    def _handle_list(self):
        agent_list = self.agents.list_agents()
        return f"当前可用 Agent 角色（共 {len(self.agents.agents)} 个）：\n\n{agent_list}", True

    def _handle_status(self, message_id):
        status_base = self.agents.status()
        mode_info = f"\n交互模式：{'WorkBuddy轻量' if self.mode == 'workbuddy' else 'Claude深度处理'}"
        status_text = status_base + mode_info
        if fc and message_id:
            try:
                fc.send_status(message_id, status_text)
                return None, True
            except Exception as e:
                log.warning(f"[Card] 状态卡片失败：{e}")
        return status_text, True

    def _handle_activate(self, text, message_id):
        for alias, agent_key in AGENT_ALIASES.items():
            if alias in text:
                if agent_key in self.agents.agents:
                    info = self.agents.agents[agent_key]
                    self.agents.active_agent = info["name"].lower()
                    # 尝试发送激活确认卡片
                    if fc and message_id:
                        try:
                            fc.send_agent_activated(message_id, info["name"], info["domain"], info["description"])
                            return None, True
                        except Exception as e:
                            log.warning(f"[Card] 激活卡片失败：{e}")
                    # 降级为纯文本
                    return f"已激活角色：{info['name']}（{info['domain']}）\n{info['description']}", True
        clean = re.sub(r'(激活|切换|换成|改为|启用|请|帮我?|一下|角色|模式|agent)', '', text, flags=re.I).strip()
        if clean:
            info = self.agents.search(clean)
            if info:
                self.agents.active_agent = info["name"].lower()
                return f"已激活角色：{info['name']}（{info['domain']}）\n{info['description']}", True
        return f"未识别到有效的角色名。请说\"切换到代码审查\"或\"激活后端架构师\"，也可以说\"列出角色\"查看全部可选角色。", True

    def _handle_task(self, instruction, agent_info=None, message_id=None, original_text=""):
        """Skills引擎驱动：精简指令→Token优化→智能分发→Claude执行"""

        # Skill 1: 指令精简 — 提取结构化任务+生成精简提示词
        parsed = se.InstructionParser.parse(instruction)
        lean_prompt = se.InstructionParser.build_prompt(parsed)
        log.info(f"[Skill] 解析: type={parsed['task_type']} lang={parsed['language']} complex={parsed['is_complex']}")

        # 非编程类超短输入 → 跳过Claude
        if se.TaskDispatcher.should_skip_claude(parsed, self.mode):
            log.info(f"[Skill] 跳过Claude（非编程超短输入）")
            return None, False

        # Skill 3: 任务分发 — 决定模型+上下文策略
        model_tier, need_agent, need_conv = se.TaskDispatcher.dispatch(parsed, self.mode)

        # Skill 2: Token优化 — 构建最小化上下文
        agent_ctx = ""
        if need_agent and agent_info:
            agent_ctx = agent_info['body']
        elif need_agent and self.agents.active_agent:
            info = self.agents.agents.get(self.agents.active_agent, {})
            agent_ctx = info.get('body', '')

        conv_ctx = ""
        if need_conv and self.conv.has_context():
            conv_ctx = str(self.conv.history[-2:]) if len(self.conv.history) >= 2 else ""

        # 构建极致精简prompt
        final_prompt = se.TokenOptimizer.build_lean_prompt(lean_prompt, agent_ctx, conv_ctx)
        prompt_size = len(final_prompt)
        log.info(f"[Skill] 分发: model={model_tier} agent={need_agent} conv={need_conv} prompt={prompt_size}字")

        # 状态推送
        if CONFIG["status"].get("sending_processing_message", True) and message_id:
            try:
                if fc:
                    fc.send_processing(message_id, parsed['core_requirement'][:50])
            except Exception as e:
                log.warning(f"[Card] 状态推送失败：{e}")

        # 记录用户指令
        self.conv.add_user(instruction)

        # 调用 Claude（精简prompt + 模型参数）
        result = call_claude_lean(final_prompt, model_tier)

        # 记录回复
        self.conv.add_assistant(result[:1000])

        return result, True


# ═══════════════════════════════════════════════════════
#  主轮询循环
# ═══════════════════════════════════════════════════════

def poll_loop():
    log.info("=" * 55)
    log.info("  飞书 → Claude Code  远程智能调度系统  v3.1")
    log.info(f"  群聊 ID：{CHAT_ID}")
    log.info(f"  日志文件：{LOG_FILE}")
    log.info(f"  RAG 模块：{'启用' if RAG_AVAILABLE else '未安装'}")
    log.info(f"  Agent 目录：{AGENTS_DIR}")
    log.info(f"  配置外置化：{'已启用' if os.path.isfile(CONFIG_FILE) else '使用默认'}")
    log.info("=" * 55)

    agents = AgentManager()
    log.info(f"[Agent] 索引完成，{len(agents.agents)} 个角色就绪")
    rag = RAGEngine() if RAG_AVAILABLE else None
    router = SmartRouter(agents, rag)
    seen_ids = set()
    error_count = 0

    while True:
        try:
            token = get_token()
            if not token:
                time.sleep(3)
                continue

            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(
                f"{BASE_URL}/im/v1/messages",
                headers=headers,
                params={
                    "container_id": CHAT_ID,
                    "container_id_type": "chat",
                    "page_size": CONFIG["polling"]["page_size"],
                    "sort_type": "ByCreateTimeDesc",
                },
                timeout=10,
            )
            data = resp.json()

            if data.get("code") != 0:
                log.warning(f"[Poll] 获取消息失败：{data.get('msg')}")
                error_count += 1
                if error_count >= 10:
                    log.error("[Poll] 连续错误过多，退出")
                    break
                time.sleep(3)
                continue

            error_count = 0
            items = data.get("data", {}).get("items", [])

            for msg in reversed(items):
                msg_id = msg.get("message_id", "")
                if not msg_id or msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                if len(seen_ids) > CONFIG["polling"]["max_seen_ids"]:
                    seen_ids = set(list(seen_ids)[-200:])

                sender_type = msg.get("sender", {}).get("sender_type", "")
                if sender_type == "app":
                    continue
                if msg.get("msg_type") != "text":
                    continue

                body = msg.get("body", {})
                try:
                    content = json.loads(body.get("content", "{}")).get("text", "")
                except (json.JSONDecodeError, TypeError):
                    continue
                if not content.strip():
                    continue

                reply_text, should_reply = router.route(content, msg_id)
                if should_reply and reply_text:
                    reply_message(msg_id, reply_text)
                elif not should_reply:
                    pass

        except KeyboardInterrupt:
            log.info("用户中断，已停止。")
            break
        except Exception as e:
            log.error(f"[Poll] 异常：{e}")
            error_count += 1
            if error_count >= 10:
                log.error("[Poll] 连续异常过多，退出")
                break

        time.sleep(CONFIG["polling"]["interval"])


def process_message(text, message_id):
    """
    处理消息的通用函数，可被轮询模式和 Webhook 模式共用
    :param text: 消息文本
    :param message_id: 消息 ID（用于回复）
    :return: (reply_text, should_reply) 元组
    """
    # 初始化 router（如果尚未初始化）
    if not hasattr(process_message, "router"):
        agents = AgentManager()
        rag = RAGEngine() if RAG_AVAILABLE else None
        process_message.router = SmartRouter(agents, rag)
    
    return process_message.router.route(text, message_id)

def start_webhook_server(host="0.0.0.0", port=8080):
    """
    启动 Webhook 服务器（在新线程中运行）
    """
    import threading
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    
    @app.route("/webhook", methods=["POST"])
    def webhook():
        """处理飞书 Webhook 事件"""
        # 验证签名（如果配置了 Encrypt Key）
        encrypt_key = CONFIG.get("webhook", {}).get("encrypt_key", "")
        if encrypt_key:
            signature = request.headers.get("X-Lark-Signature", "")
            timestamp = request.headers.get("X-Lark-Timestamp", "")
            nonce = request.headers.get("X-Lark-Nonce", "")
            
            # 构造待签名字符串
            content = f"{timestamp}{nonce}{encrypt_key}"
            # 计算签名
            import hmac
            import hashlib
            calc_sig = hmac.new(
                encrypt_key.encode("utf-8"),
                content.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(calc_sig, signature):
                log.warning("[Webhook] 签名验证失败")
                return jsonify({"code": 401, "msg": "signature verification failed"}), 401
        
        # 解析事件数据
        event_data = request.get_json()
        if not event_data:
            return jsonify({"code": 400, "msg": "invalid json"}), 400
        
        # 处理事件
        event_type = event_data.get("header", {}).get("event_type", "")
        log.info(f"[Webhook] 收到事件：{event_type}")
        
        if event_type == "url_verification":
            # URL 验证挑战
            challenge = event_data.get("challenge", "")
            return jsonify({"challenge": challenge})
        
        elif event_type == "im.message.receive_v1":
            # 处理接收消息事件
            event = event_data.get("event", {})
            msg_id = event.get("message_id", "")
            sender = event.get("sender", {})
            sender_type = sender.get("sender_type", "")
            
            # 过滤应用自己发的消息
            if sender_type == "app":
                return jsonify({"code": 0, "msg": "success"})
            
            # 获取消息内容
            msg_type = event.get("message_type", "")
            if msg_type != "text":
                return jsonify({"code": 0, "msg": "success"})
            
            content = event.get("content", "{}")
            try:
                content_data = json.loads(content)
                text = content_data.get("text", "")
            except json.JSONDecodeError:
                return jsonify({"code": 0, "msg": "success"})
            
            # 处理消息
            reply_text, should_reply = process_message(text, msg_id)
            
            if should_reply and reply_text:
                # 回复消息
                reply_message(msg_id, reply_text)
        
        return jsonify({"code": 0, "msg": "success"})
    
    # 在新线程中启动 Flask 服务器
    def run_server():
        app.run(host=host, port=port, debug=False, use_reloader=False)
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    
    log.info(f"[Webhook] Webhook 服务器已启动：http://{host}:{port}/webhook")
    return thread

if __name__ == "__main__":
    # 检查是否以 Webhook 模式启动
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--webhook":
        # Webhook 模式
        start_webhook_server()
        # 保持主线程运行
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Webhook 服务器已停止")
    else:
        # 轮询模式
        poll_loop()
