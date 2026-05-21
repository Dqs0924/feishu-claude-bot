# 飞书→ClaudeCode 远程智能调度系统 — 完整项目结构总览

> 生成时间：2026-05-21 | 版本：v3.0 | 总体完成度：95%
> 用途：WorkBuddy 平台迁移对接，剩余细节补全、参数微调、边角功能完善

---

## 一、项目根目录

```
C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo\
```

---

## 二、分区一：核心运行代码（6个文件）

| 文件 | 路径 | 大小 | 用途 |
|------|------|------|------|
| **run_feishu_poll.py** | `wechat-claude-demo/run_feishu_poll.py` | ~16KB | ★ 主程序：轮询监听+SmartRouter自然语言路由+Agent调度+模型分级+RAG增强+智能分段+日志轮转 |
| **rag_module.py** | `wechat-claude-demo/rag_module.py` | ~11KB | RAG引擎：ChromaDB向量检索+规则双模式，37条知识库 |
| **call_claude.py** | `wechat-claude-demo/call_claude.py` | ~5KB | Claude CLI调用封装（备用，主逻辑已整合进run_feishu_poll.py） |
| **feishu_listener.py** | `wechat-claude-demo/feishu_listener.py` | ~12KB | 飞书API完整封装：Token/发送/回复/Webhook/轮询（备用） |
| **run_demo.py** | `wechat-claude-demo/run_demo.py` | ~7KB | Demo入口：多平台演示（simulate/feishu模式） |
| **result_callback.py** | `wechat-claude-demo/result_callback.py` | ~3.5KB | 结果回传模拟+outbox存档 |

### 核心依赖关系
```
run_feishu_poll.py
  ├── import rag_module (RAGEngine)
  ├── 内置 AgentManager (Agent角色管理)
  ├── 内置 SmartRouter (自然语言路由)
  ├── 内置 call_claude (ClaudeCode调用+模型分级)
  ├── 内置 smart_chunk (智能分段)
  └── 调用飞书API (requests直连)
```

---

## 三、分区二：飞书通信链路（4个文件）

| 文件 | 路径 | 用途 |
|------|------|------|
| **run_feishu_poll.py** | `wechat-claude-demo/run_feishu_poll.py` | 轮询主程序（生产环境） |
| **run_feishu_webhook.py** | `wechat-claude-demo/run_feishu_webhook.py` | Webhook模式（含ngrok隧道，未部署） |
| **feishu_listener.py** | `wechat-claude-demo/feishu_listener.py` | 飞书API完整封装 |
| **simulate_message.py** | `wechat-claude-demo/simulate_message.py` | 消息模拟器（调试） |

### 飞书API配置（硬编码在 run_feishu_poll.py）
```python
APP_ID     = "cli_xxxxxxxxxxxxx"        # 飞书应用ID
APP_SECRET = "YOUR_FEISHU_APP_SECRET"  # 飞书应用密钥
CHAT_ID    = "oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # 目标群聊ID
BASE_URL   = "https://open.feishu.cn/open-apis"
```

---

## 四、分区三：Agent角色体系（外部资源）

### 4.1 Agent角色库
```
C:\Users\丁溱烁\.claude\agents\
```
**226个角色文件（.md），分布18个领域：**

| 领域目录 | 角色数 | 典型角色 |
|---------|--------|---------|
| engineering/ | 29 | Code Reviewer, Backend Architect, Frontend Developer, Security Engineer |
| specialized/ | 41 | 各类专项Agent |
| marketing/ | 30 | 营销相关Agent |
| game-development/ | 20 | 游戏开发Agent |
| strategy/ | 16 | 策略类Agent |
| integrations/ | 14 | 集成类Agent（含Feishu Integration Developer） |
| design/ | 8 | 设计类Agent |
| sales/ | 8 | 销售类Agent |
| testing/ | 8 | 测试类Agent |
| paid-media/ | 7 | 付费媒体Agent |
| examples/ | 6 | 示例Agent |
| project-management/ | 6 | 项目管理Agent |
| spatial-computing/ | 6 | 空间计算Agent |
| support/ | 6 | 支持类Agent |
| academic/ | 5 | 学术类Agent |
| finance/ | 5 | 金融类Agent |
| product/ | 5 | 产品类Agent |
| scripts/ | 1 | 脚本工具 |

### 4.2 Agent调度配置（内置于 run_feishu_poll.py）
```python
AGENT_ALIASES = { ... }  # 40+中文别名映射
# 示例："代码审查"→Code Reviewer, "后端架构师"→Backend Architect
```

### 4.3 Agent上下文提取规则
- 优先级：Critical Rules > Core Mission > Your Identity > 首600字
- 精简比：3000字→400-600字（83%缩减）
- 注入策略：显式指定必注入 / 已激活+复杂任务 / 简单任务零上下文

---

## 五、分区四：RAG知识引擎（3部分）

### 5.1 知识库
```
C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo\instruction_kb.json
```
- 格式：JSON，37条口语→标准指令映射
- 覆盖领域：基础输出、排序算法、代码审查、Web开发、翻译、API开发、数据库设计、调试、测试、方案设计、性能优化、爬虫、脚本、重构、部署、架构设计

### 5.2 向量数据库
```
C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo\rag_db\
  ├── chroma.sqlite3           # ChromaDB持久化文件（~774KB）
  └── 5a27d420-.../            # 向量索引数据
```
- 引擎：ChromaDB + all-MiniLM-L6-v2（SentenceTransformer）
- 相似度度量：cosine距离，阈值0.65
- 镜像加速：HF_ENDPOINT=https://hf-mirror.com

### 5.3 RAG触发条件（v3.0优化）
- 仅对含编程关键词的输入启用（TECH_KEYWORDS正则）
- 纯对话/问候/状态查询跳过RAG

---

## 六、分区五：运行保障体系（3个文件）

| 文件 | 路径 | 用途 |
|------|------|------|
| **start_poll.bat** | `wechat-claude-demo/start_poll.bat` | Windows启动脚本（崩溃自动重启，5秒间隔） |
| **feishu_poll.log** | `wechat-claude-demo/feishu_poll.log` | 运行日志（RotatingFileHandler，5×5MB轮转） |
| **requirements.txt** | `wechat-claude-demo/requirements.txt` | Python依赖：requests, chromadb, sentence-transformers |

### 环境依赖
```
Python: C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe
Claude CLI: %APPDATA%\npm\claude.cmd (v2.1.145)
Node.js: C:\Program Files\nodejs\
```

---

## 七、分区六：ClaudeCode模型配置

```
C:\Users\丁溱烁\.claude\settings.json
```
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "sk-ae70e4f63a544671bde62c6aea264e61",
    "ANTHROPIC_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro"
  },
  "permissions": { "allow": [...], "deny": [...] }
}
```
- 默认模型：v4-flash（快速/低成本）
- 复杂任务模型：v4-pro（仅opus级触发）
- 权限：永久skip确认，仅拦截极致危险操作

---

## 八、分区七：Skills规则库

```
C:\Users\丁溱烁\.claude\skills\
```

| Skill | 路径 | 用途 |
|-------|------|------|
| **agency-agents** | `skills/agency-agents/SKILL.md` | Agent角色调度规则（list/activate/search） |
| **auto-executor** | `skills/auto-executor/SKILL.md` | 全局自动执行规则（免确认） |
| **deepseek-scheduler** | `skills/deepseek-scheduler/SKILL.md` | DeepSeek模型调度策略 |
| **docs** | `skills/docs/SKILL.md` | 文档生成规范 |
| **find-skills** | `skills/find-skills/SKILL.md` | 技能发现与匹配 |
| **playwright** | `skills/playwright/SKILL.md` | 浏览器自动化 |
| **research** | `skills/research/SKILL.md` | 调研分析 |
| **skill-creator** | `skills/skill-creator/SKILL.md` | 技能创建器 |

---

## 九、分区八：文档手册（6个文件）

| 文件 | 路径 | 用途 |
|------|------|------|
| **README.md** | `wechat-claude-demo/README.md` | 项目说明+快速开始 |
| **startup-guide.md** | `wechat-claude-demo/startup-guide.md` | Windows部署指南（任务计划/NSSM） |
| **FEISHU_SETUP.md** | `wechat-claude-demo/FEISHU_SETUP.md` | 飞书应用配置教程 |
| **system-design.md** | `wechat-claude-demo/system-design.md` | 系统架构设计文档 |
| **对接文档.md** | `wechat-claude-demo/对接文档.md` | 中文详细对接文档 |
| **PROJECT_OVERVIEW.md** | `wechat-claude-demo/PROJECT_OVERVIEW.md` | 本文档 |

---

## 十、分区九：测试与调试工具（8个文件）

| 文件 | 路径 | 用途 |
|------|------|------|
| **test_e2e.py** | `wechat-claude-demo/test_e2e.py` | 端到端测试 |
| **test_feishu_token.py** | `wechat-claude-demo/test_feishu_token.py` | Token获取测试 |
| **test_poll.py** | `wechat-claude-demo/test_poll.py` | 轮询基础测试 |
| **test_poll2.py** | `wechat-claude-demo/test_poll2.py` | 轮询测试2 |
| **test_poll3.py** | `wechat-claude-demo/test_poll3.py` | 轮询测试3 |
| **test_poll_once.py** | `wechat-claude-demo/test_poll_once.py` | 单次轮询测试 |
| **test_poll_debug.py** | `wechat-claude-demo/test_poll_debug.py` | 轮询调试 |
| **test_poll_permission.py** | `wechat-claude-demo/test_poll_permission.py` | 权限测试 |
| **debug_messages.py** | `wechat-claude-demo/debug_messages.py` | 消息调试 |
| **test_hello.py** | `wechat-claude-demo/test_hello.py` | Hello World测试 |

---

## 十一、分区十：暂存与存档目录

| 目录 | 路径 | 内容 |
|------|------|------|
| **outbox/** | `wechat-claude-demo/outbox/` | 9个历史结果文件（.txt） |
| **inbox/** | `wechat-claude-demo/inbox/` | 2个测试指令文件 |
| **handover/** | `wechat-claude-demo/handover/` | 旧版交接文件（7个文件，已过期） |
| **webhook/** | `wechat-claude-demo/webhook/` | Webhook配置目录（空） |
| **__pycache__/** | `wechat-claude-demo/__pycache__/` | Python字节码缓存 |

---

## 十二、全局行为契约

```
d:\agent实现文档\CLAUDE.md
```
- 12条核心规则（基础4+进阶8）
- Skills启用声明（9个已启用）
- Agency-Agents调度规则
- 禁止私装库/爬数据

---

## 十三、WorkBuddy迁移对接清单

### 已完成（无需改动）
- [x] 核心轮询+自然语言路由（SmartRouter v3.0）
- [x] Agent角色体系（226角色+40别名+精简上下文）
- [x] RAG知识引擎（37条+ChromaDB向量）
- [x] 模型分级调度（v4-flash默认/v4-pro复杂任务）
- [x] 智能分段回传（段落边界+代码块保持）
- [x] 崩溃重启+日志轮转
- [x] 闲聊过滤+重复消息防护
- [x] 全局免确认权限

### 待补全/微调（WorkBuddy可操作）
- [ ] **飞书配置外置**：APP_ID/SECRET/CHAT_ID 从环境变量或配置文件读取（当前硬编码）
- [ ] **Webhook模式部署**：run_feishu_webhook.py 需ngrok隧道+飞书后台配置
- [ ] **Agent别名扩展**：AGENT_ALIASES 字典可继续补充中文别名
- [ ] **RAG知识库扩充**：instruction_kb.json 从37条继续扩展至100+条
- [ ] **飞书卡片美化**：当前纯文本回复，可升级为交互式卡片
- [ ] **测试脚本清理**：test_poll*.py等调试文件可归档或删除
- [ ] **handover/目录清理**：旧版交接文件已过期可删除
- [ ] **多群聊支持**：当前单CHAT_ID，可扩展为多群聊并发监听
- [ ] **执行状态推送**：Claude执行中→飞书"正在处理..."提示
- [ ] **GUI管理面板**：Tauri/Electron桌面托盘程序

### 参数/配置待补全
- [ ] `settings.json` 中 `ANTHROPIC_AUTH_TOKEN` 如需更换
- [ ] 飞书APP_SECRET 如需轮换
- [ ] `_find_claude()` 候选路径如需扩展
- [ ] `start_poll.bat` 中 Python 路径（当前硬编码）

---

## 十四、快速启动命令

```cmd
:: 前台调试
cd C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo
C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe -u run_feishu_poll.py

:: 后台自恢复
start_poll.bat

:: 注册Windows服务（开机自启）
:: 详见 startup-guide.md 方案A
```

---

> **文档结束** | 可直接导入 WorkBuddy 平台继续开发
