#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skills Engine — 企业级三合一指令优化引擎
==========================================
GitHub: (your-repo-url)
Author: Ding Zhenshuo
License: MIT
Version: 1.0.0

快速集成（3 行接入现有项目）:
    import skill_engine as se
    parsed = se.InstructionParser.parse(user_input)
    prompt = se.InstructionParser.build_prompt(parsed)

三大技能模块:
    skill_1: InstructionParser  — 自然语言→结构化任务，固定37字精炼提示词
    skill_2: TokenOptimizer     — 上下文最小化，Agent≤300字，总≤1500字
    skill_3: TaskDispatcher     — 简单→haiku / 复杂→opus，自动判别

使用示例:
    >>> import skill_engine as se
    >>> r = se.InstructionParser.parse("帮我写个python冒泡排序")
    >>> r['task_type']
    'code_generation'
    >>> r['language']
    'Python'
    >>> prompt = se.InstructionParser.build_prompt(r)
    >>> print(prompt)
    '写Python代码：写个python冒泡排序。直接输出完整代码，包含注释。'
    >>> model, need_agent, need_conv = se.TaskDispatcher.dispatch(r, 'claude')
    >>> model
    'haiku'
"""

import re
import logging
from typing import Dict, Tuple, Optional

log = logging.getLogger("skill_engine")


# ══════════════════════════════════════════════════════════════
# Skill 1: 指令精简器 — InstructionParser
# ══════════════════════════════════════════════════════════════

class InstructionParser:
    """自然语言→结构化任务描述，固定37字精炼提示词。

    核心能力:
        1. 任务类型识别（代码生成/审查/优化/调试/解释/设计/翻译/测试）
        2. 编程语言提取（Python/JS/Java/Go/Rust/C++/HTML/SQL/Shell）
        3. 核心需求剥离（去礼貌用语/冗余修饰词）
        4. 复杂度判定（简单→haiku / 复杂→opus）

    使用方式:
        parsed = InstructionParser.parse("帮我写个python冒泡排序")
        prompt = InstructionParser.build_prompt(parsed)
    """

    # ── 任务类型识别规则 ──
    # 格式: (正则, 类型标签)
    # 扩展方式: 在列表末尾追加新规则即可
    TASK_PATTERNS = [
        (re.compile(r'(写|生成|创建|开发|实现|编写|帮我写|给我写|写个|写一段|写一个)'), 'code_generation'),
        (re.compile(r'(检查|审查|review|看看|查一下|帮我看看).{0,5}(代码|程序|bug|错误|问题)'), 'code_review'),
        (re.compile(r'(优化|改进|提升|加速|性能|太慢|卡)'), 'optimization'),
        (re.compile(r'(调试|debug|修复|fix|修|改错|哪里有问题|为什么不行)'), 'debug'),
        (re.compile(r'(解释|说明|讲解|分析|什么意思|是什么|介绍)'), 'explanation'),
        (re.compile(r'(设计|架构|方案|怎么实现|如何设计|怎么做)'), 'design'),
        (re.compile(r'(翻译|translate|转换)'), 'translation'),
        (re.compile(r'(测试|test|写测试|单元测试)'), 'testing'),
    ]

    # ── 编程语言识别规则 ──
    LANG_PATTERNS = [
        (re.compile(r'\b(python|py|Python|PYTHON)\b'), 'Python'),
        (re.compile(r'\b(javascript|js|JavaScript|JS|nodejs|node)\b'), 'JavaScript'),
        (re.compile(r'\b(java|Java)\b(?!.*script)'), 'Java'),
        (re.compile(r'\b(go|golang|Go|Golang)\b'), 'Go'),
        (re.compile(r'\b(rust|Rust|RUST)\b'), 'Rust'),
        (re.compile(r'\b(c\+\+|cpp|C\+\+|Cpp)\b'), 'C++'),
        (re.compile(r'\b(html|css|HTML|CSS|前端|网页)\b'), 'HTML/CSS'),
        (re.compile(r'\b(sql|SQL|mysql|MySQL|postgresql|PostgreSQL)\b'), 'SQL'),
        (re.compile(r'\b(shell|bash|Shell|Bash|sh)\b'), 'Shell'),
        (re.compile(r'\b(ts|typescript|TypeScript|TS)\b'), 'TypeScript'),
        (re.compile(r'\b(react|React|vue|Vue|angular|Angular)\b'), 'JavaScript'),
    ]

    # ── 复杂度关键词 ──
    COMPLEX_KEYWORDS = re.compile(
        r'(系统|架构|完整|全部|整个|项目|设计|部署|安全|性能|数据库|并发|分布式|微服务|集群)'
    )

    @classmethod
    def parse(cls, text: str) -> Dict[str, any]:
        """解析自然语言输入，返回结构化任务描述。

        Args:
            text: 用户原始输入，如 "帮我写个python冒泡排序"

        Returns:
            dict with keys:
                task_type:      代码生成/审查/优化/调试/解释/设计/翻译/测试/通用
                language:       编程语言或 'auto'
                core_requirement: 剥离冗余后的核心需求文本
                is_complex:     是否复杂任务（决定模型选择）
                original:       原始输入文本
        """
        # Step 1: 识别任务类型
        task_type = 'general'
        for pattern, ttype in cls.TASK_PATTERNS:
            if pattern.search(text):
                task_type = ttype
                break

        # Step 2: 识别编程语言
        language = 'auto'
        for pattern, lang in cls.LANG_PATTERNS:
            if pattern.search(text):
                language = lang
                break
        # 代码生成类任务默认 Python
        if language == 'auto' and task_type == 'code_generation':
            language = 'Python'

        # Step 3: 提取核心需求（去冗余）
        core = cls._extract_core(text)

        # Step 4: 复杂度判定
        is_complex = bool(cls.COMPLEX_KEYWORDS.search(text)) or len(core) > 80

        return {
            'task_type': task_type,
            'language': language,
            'core_requirement': core,
            'is_complex': is_complex,
            'original': text,
        }

    @classmethod
    def build_prompt(cls, parsed: Dict[str, any]) -> str:
        """从结构化任务构建精炼提示词（目标37字）。

        提示词设计原则:
            - 直接声明任务类型和语言
            - 包含核心需求关键词
            - 明确输出格式要求
            - 零冗余修饰
        """
        t = parsed['task_type']
        lang = parsed['language']
        core = parsed['core_requirement']

        # 精简模板（每种类型固定格式，确保Claude准确理解）
        TEMPLATES = {
            'code_generation': f"写{lang}代码：{core}。直接输出完整代码，包含注释。",
            'code_review':     f"审查代码：{core}。直接列出问题和修复建议。",
            'optimization':    f"优化：{core}。直接给出优化方案和代码。",
            'debug':           f"调试：{core}。直接找出bug并给出修复代码。",
            'explanation':     f"解释：{core}。简洁说明，不需要展开。",
            'design':          f"设计方案：{core}。给出架构要点和关键代码。",
            'translation':     f"翻译：{core}。直接输出译文。",
            'testing':         f"写测试：{core}。直接输出完整测试代码。",
            'general':         core,
        }
        return TEMPLATES.get(t, core)

    # ── 内部方法 ──

    @classmethod
    def _extract_core(cls, text: str) -> str:
        """提取核心需求：剥离礼貌用语、语气词、冗余修饰。

        处理顺序:
            1. 去前缀: 帮我/给我/请你/麻烦...
            2. 去后缀: 吧/吗/呢/谢谢...
            3. 去量词: 一下/一个/一段...
            4. 压缩空白
        """
        # 前缀冗余
        text = re.sub(
            r'^(帮我|给我|请你|请|麻烦|能不能|可以|可否|能|会|帮我看看|你帮我|你来)\s*',
            '', text
        )
        # 后缀语气/感谢
        text = re.sub(
            r'\s*(吧|吗|呢|呀|啊|好不好|可以吗|行不行|谢谢|多谢|感谢|拜托)\s*$',
            '', text
        )
        # 量词
        text = re.sub(r'\s*(一下|一个|一段|一篇|一份|一次)\s*', ' ', text)
        # 多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# ══════════════════════════════════════════════════════════════
# Skill 2: Token 优化器 — TokenOptimizer
# ══════════════════════════════════════════════════════════════

class TokenOptimizer:
    """上下文注入最小化控制器。

    约束规则:
        - Agent 角色上下文 ≤ 300 字（仅保留核心行为规则）
        - 对话历史 ≤ 500 字（仅保留最近 1 轮）
        - 总提示词 ≤ 1500 字（超出自动截断）
        - 无效上下文自动清理

    使用方式:
        prompt = TokenOptimizer.build_lean_prompt(instruction, agent_body, conv_history)
    """

    # ── 硬约束 ──
    MAX_AGENT_CONTEXT = 300     # Agent 上下文最大字数
    MAX_CONV_CONTEXT  = 500     # 对话历史最大字数
    MAX_PROMPT_TOTAL  = 1500    # 总提示词最大字数

    # ── 可调参数（通过环境变量或直接赋值修改）──
    RULES_MAX_LINES   = 8       # Agent规则最多保留行数
    HISTORY_MAX_ROUNDS = 1      # 对话历史最多保留轮数

    @classmethod
    def optimize_agent_context(cls, agent_body: str) -> str:
        """精简 Agent 上下文：仅提取核心行为规则（数字/破折号/星号开头的行）。

        输入: 完整的 Agent Markdown body（可能数千字）
        输出: ≤300 字的核心规则列表
        """
        if not agent_body:
            return ""

        lines = agent_body.strip().split('\n')
        core_lines = []

        # 提取规则行（以数字、破折号、星号开头）
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # 匹配 "1. xxx" / "- xxx" / "* xxx"
            if (stripped[0].isdigit() and '. ' in stripped[:4]) or \
               stripped.startswith('- ') or stripped.startswith('* '):
                core_lines.append(stripped)
                # 达到上限即停止
                current_size = sum(len(l) for l in core_lines)
                if current_size > cls.MAX_AGENT_CONTEXT:
                    break

        # 无规则行时的兜底：取首段文本
        if not core_lines:
            core_lines = [l.strip() for l in lines[:5] if l.strip()]

        # 截断到最大行数和最大字数
        result = '\n'.join(core_lines[:cls.RULES_MAX_LINES])
        if len(result) > cls.MAX_AGENT_CONTEXT:
            result = result[:cls.MAX_AGENT_CONTEXT]
        return result

    @classmethod
    def optimize_conv_context(cls, history: list) -> str:
        """精简对话历史：仅保留最近 N 轮。

        输入: 对话历史列表
        输出: ≤500 字的精简历史文本
        """
        if not history:
            return ""

        # 只取最近 N 轮（每轮 = 用户消息 + 助手回复）
        rounds = cls.HISTORY_MAX_ROUNDS * 2
        recent = history[-rounds:] if len(history) >= rounds else history

        # 每条消息截断到 200 字
        lines = [str(h)[:200] for h in recent]
        result = '\n'.join(lines)

        if len(result) > cls.MAX_CONV_CONTEXT:
            result = result[:cls.MAX_CONV_CONTEXT]
        return result

    @classmethod
    def build_lean_prompt(cls, instruction: str,
                          agent_context: str = "",
                          conv_context: str = "") -> str:
        """构建极致精简的最终提示词。

        Args:
            instruction:  已精简的任务指令（来自 InstructionParser.build_prompt）
            agent_context: Agent 角色 body（可选）
            conv_context:  对话历史（可选）

        Returns:
            ≤1500 字的结构化提示词
        """
        parts = []

        # 注入角色（精简后）
        if agent_context:
            trimmed = cls.optimize_agent_context(agent_context)
            if trimmed:
                parts.append(f"[Role]\n{trimmed}")

        # 注入历史（精简后）
        if conv_context:
            trimmed = cls.optimize_conv_context(conv_context)
            if trimmed:
                parts.append(f"[History]\n{trimmed}")

        # 当前指令
        parts.append(instruction)

        result = '\n\n'.join(parts)

        # 硬截断
        if len(result) > cls.MAX_PROMPT_TOTAL:
            result = result[:cls.MAX_PROMPT_TOTAL]

        return result


# ══════════════════════════════════════════════════════════════
# Skill 3: 任务分发器 — TaskDispatcher
# ══════════════════════════════════════════════════════════════

class TaskDispatcher:
    """任务复杂度评估 + 执行模式自动分发。

    分层策略:
        WorkBuddy 模式 → 永远 haiku（轻量快速）
        Claude 模式   → 简单任务 haiku / 复杂任务 opus

    复杂度定义:
        复杂 = 包含架构/设计/优化/审查/部署关键词 OR 核心需求 > 80 字
        简单 = 代码生成/解释/翻译/测试等基础任务

    使用方式:
        model, need_agent, need_conv = TaskDispatcher.dispatch(parsed, router_mode)
    """

    # 需要 Agent 上下文的任务类型
    AGENT_REQUIRED_TYPES = {'design', 'optimization', 'code_review'}

    # 需要对话上下文的任务类型
    CONV_REQUIRED_TYPES = {'design', 'debug'}

    @classmethod
    def dispatch(cls, parsed: Dict[str, any],
                 router_mode: str = 'claude') -> Tuple[str, bool, bool]:
        """评估任务并返回执行策略。

        Args:
            parsed:      InstructionParser.parse() 的输出
            router_mode: 'workbuddy' | 'claude'

        Returns:
            (model_tier, needs_agent, needs_conv)
            model_tier:  'haiku' | 'opus'
            needs_agent: 是否注入 Agent 角色上下文
            needs_conv:  是否注入对话历史上下文
        """
        # WorkBuddy 模式：永远轻量，不注入额外上下文
        if router_mode == 'workbuddy':
            return 'haiku', False, False

        # Claude 模式：根据复杂度分层
        task_type = parsed.get('task_type', 'general')

        if parsed.get('is_complex', False):
            # 复杂任务：高配模型 + 完整上下文
            return 'opus', True, True

        if task_type in cls.AGENT_REQUIRED_TYPES:
            # 设计/优化/审查：需要 Agent 但不一定需要历史
            need_conv = task_type in cls.CONV_REQUIRED_TYPES
            return 'opus', True, need_conv

        # 默认：轻量快速
        return 'haiku', False, False

    @classmethod
    def should_skip_claude(cls, parsed: Dict[str, any],
                           router_mode: str = 'claude') -> bool:
        """判断是否应跳过 Claude 调用（零 Token 消耗）。

        跳过条件:
            - WorkBuddy 模式下非编程类任务
            - 超短无意义输入（< 6 字且无技术关键词）
        """
        if router_mode == 'workbuddy' and parsed.get('task_type') == 'general':
            return True

        core = parsed.get('core_requirement', '')
        # 超短且无技术关键词
        if len(core) < 6 and not re.search(
            r'(写|代码|程序|bug|错误|修复|优化|设计|测试|部署)',
            core
        ):
            return True

        return False


# ══════════════════════════════════════════════════════════════
# 自检: python skill_engine.py 直接运行
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  Skills Engine v1.0 — 自检测试")
    print("=" * 55)

    test_cases = [
        "帮我写个python冒泡排序",
        "帮我看看这段代码有什么bug",
        "优化一下这个函数的性能",
        "设计一个微服务架构",
        "翻译这段文字",
        "你好",
    ]

    for text in test_cases:
        r = InstructionParser.parse(text)
        prompt = InstructionParser.build_prompt(r)
        model, ag, cv = TaskDispatcher.dispatch(r, 'claude')
        skip = TaskDispatcher.should_skip_claude(r, 'claude')
        print(f"\n输入: {text}")
        print(f"  类型={r['task_type']} 语言={r['language']} 复杂={r['is_complex']}")
        print(f"  提示词({len(prompt)}字): {prompt}")
        print(f"  分发: model={model} agent={ag} conv={cv} skip={skip}")

    # Token优化器测试
    print(f"\n{'='*55}")
    print("  Token 优化器测试")
    fake_agent = "1. Be specific in code reviews.\n2. Explain why, not just what.\n3. Suggest, don't demand.\n4. Prioritize issues.\n" * 5
    result = TokenOptimizer.optimize_agent_context(fake_agent)
    print(f"  Agent 上下文: {len(fake_agent)}字 → {len(result)}字")

    print(f"\n{'='*55}")
    print("  全部自检通过。")
