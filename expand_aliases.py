#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直接重写 expand_aliases.py，修复 f-string 语法错误"""

import re, os, json

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_feishu_poll.py")

# 新增别名列表（alias, agent_key）
NEW_ALIASES = [
    # 工程类变体
    ("审代码", "code reviewer"),
    ("检查代码", "code reviewer"),
    ("质检代码", "code reviewer"),
    ("后台架构", "backend architect"),
    ("服务端架构", "backend architect"),
    ("后端设计", "backend architect"),
    ("前端页面", "frontend developer"),
    ("web前端", "frontend developer"),
    ("UI开发", "frontend developer"),
    ("安全扫描", "security engineer"),
    ("安全检查", "security engineer"),
    ("渗透测试", "security engineer"),
    ("接口测试", "api tester"),
    ("API测试", "api tester"),
    ("压测", "performance benchmarker"),
    ("性能测试", "performance benchmarker"),
    ("慢查询优化", "database optimizer"),
    ("SQL优化", "database optimizer"),
    ("运维部署", "devops automator"),
    ("CI/CD", "devops automator"),
    ("持续集成", "devops automator"),
    ("系统架构", "software architect"),
    ("高级工程师", "senior developer"),
    ("全栈开发", "senior developer"),
    ("区块链合约", "solidity smart contract engineer"),
    ("合约审计", "solidity smart contract engineer"),
    ("安卓开发", "mobile app builder"),
    ("iOS开发", "mobile app builder"),
    ("APP开发", "mobile app builder"),
    ("技术文档", "technical writer"),
    ("接口文档", "technical writer"),
    ("Git操作", "git workflow master"),
    ("版本管理", "git workflow master"),
    ("可靠性工程", "sre"),
    ("站点可靠性", "sre"),
    ("异常检测", "threat detection engineer"),
    ("入侵检测", "threat detection engineer"),
    ("数据管道", "data engineer"),
    ("ETL开发", "data engineer"),

    # 产品/设计类
    ("产品需求", "product manager"),
    ("PRD", "product manager"),
    ("市场分析", "trend researcher"),
    ("行业研究", "trend researcher"),
    ("UI设计", "ui designer"),
    ("UX设计", "ux designer"),
    ("交互设计", "ux designer"),
    ("视觉设计", "visual designer"),

    # 学术类
    ("论文润色", "academic editor"),
    ("学术写作", "academic editor"),
    ("文献综述", "literature reviewer"),

    # 游戏开发类
    ("游戏逻辑", "game designer"),
    ("关卡设计", "level designer"),
    ("游戏引擎", "game engine developer"),

    # 营销类
    ("营销文案", "marketing copywriter"),
    ("SEO优化", "seo specialist"),
    ("社交媒体", "social media manager"),

    # 销售类
    ("销售话术", "sales copywriter"),
    ("客户跟进", "account executive"),

    # 支持/法律/财务
    ("客服回复", "support responder"),
    ("用户支持", "support responder"),
    ("合规检查", "legal compliance checker"),
    ("法律风险", "legal compliance checker"),
    ("财务报表", "financial analyst"),
    ("投资分析", "financial analyst"),

    # 无障碍/项目管理
    ("无障碍审计", "accessibility auditor"),
    ("A11Y检查", "accessibility auditor"),
    ("项目排期", "project shepherd"),
    ("迭代管理", "project shepherd"),

    # 空间计算类
    ("AR开发", "ar developer"),
    ("VR开发", "vr developer"),
    ("空间计算", "spatial computing engineer"),

    # 通用加强
    ("写一个", "senior developer"),
    ("实现一个", "senior developer"),
    ("帮我做", "senior developer"),
]

def main():
    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    # 找到 AGENT_ALIASES 字典的结束位置
    start_pat = r"AGENT_ALIASES\s*=\s*\{"
    m_start = re.search(start_pat, content)
    if not m_start:
        print("[错误] 未找到 AGENT_ALIASES 字典")
        return

    dict_start = m_start.end()
    depth = 1
    pos = dict_start
    while pos < len(content) and depth > 0:
        ch = content[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        pos += 1
    dict_end = pos - 1  # 指向 }

    # 构建新条目文本（使用字符串拼接，避免 f-string 引号问题）
    indent = "    "
    new_lines = []
    added = 0
    for alias, agent in NEW_ALIASES:
        key = '"' + alias + '"'
        val = '"' + agent + '"'
        entry = indent + key + ": " + val + ","
        if entry.strip() in content:
            continue
        new_lines.append(entry)
        added += 1

    if not new_lines:
        print("[信息] 所有新别名已存在，无需添加")
        return

    new_text = "\n" + "\n".join(new_lines) + "\n"
    new_content = content[:dict_end] + new_text + content[dict_end:]

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[完成] 新增 {added} 条别名映射")
    print(f"[完成] 文件已更新：{TARGET}")

if __name__ == "__main__":
    main()
