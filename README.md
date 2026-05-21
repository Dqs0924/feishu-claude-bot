# 飞书→Claude Code 远程智能调度系统

## 项目概述

通过飞书手机客户端发送指令，PC 端自动监听并调用 Claude Code 执行编程任务，结果自动回传飞书。集成了 RAG 语义检索增强、199 个 Agent 角色自动调度、智能结果分段回传。

**核心价值**：在手机上打字就能远程操控 PC 上的 Claude Code 完成任意编程任务，无需坐在电脑前。

## 系统架构

```
手机飞书 → 飞书开放平台API → PC轮询监听 → RAG语义标准化
                                            ↓
手机飞书 ← 智能分段回传       ←        Claude Code执行
                                            ↑
                                     Agent角色注入
                                    (184个专业角色)
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 消息通道 | 飞书开放平台 API (tenant_access_token) |
| 监听模式 | HTTP 轮询 (2s间隔, sort_type=ByCreateTimeDesc) |
| 语义增强 | ChromaDB + all-MiniLM-L6-v2 向量检索 |
| AI 引擎 | Claude Code CLI (claude -p --dangerously-skip-permissions) |
| 角色调度 | 184 个 Agency-Agent 实时加载注入 |
| 日志系统 | Python RotatingFileHandler (5×5MB 轮转) |
| 运行保障 | .bat 批处理 + Windows 任务计划 / NSSM 服务 |

## 项目文件清单

```
wechat-claude-demo/
├── run_feishu_poll.py      # ★ 主程序：轮询监听+指令分发+Agent调度+智能分段
├── rag_module.py           # RAG 引擎：向量/规则双模式语义检索
├── instruction_kb.json     # 知识库：25 条口语→标准指令映射
├── call_claude.py          # Claude CLI 调用封装
├── feishu_listener.py      # 飞书 API 完整封装 (发送/回复/Webhook/轮询)
├── run_demo.py             # Demo 演示入口 (多平台)
├── run_feishu_webhook.py   # Webhook 模式 (含 ngrok 隧道)
├── result_callback.py      # 结果回传模拟 + outbox 存档
├── simulate_message.py     # 消息模拟 (调试用)
├── test_e2e.py             # 端到端测试
├── start_poll.bat          # ★ Windows 启动脚本 (崩溃自动重启)
├── startup-guide.md        # ★ 部署指南 (任务计划/NSSM)
├── FEISHU_SETUP.md         # 飞书应用配置教程
├── system-design.md        # 系统设计文档
├── 对接文档.md             # 中文详细对接文档
├── requirements.txt        # Python 依赖
├── rag_db/                 # ChromaDB 向量库 (自动生成)
├── feishu_poll.log         # 运行日志 (自动轮转)
├── outbox/                 # 结果存档目录
└── handover/               # 交接文件
```

## 使用方式（零学习成本）

**无需记忆任何指令格式**，像跟同事说话一样自然表达即可：

| 你说的话（示例） | 系统自动理解并执行 |
|-----------|---------|
| "帮我写个快速排序" | → 识别为编程任务 → RAG增强 → Claude执行 |
| "用代码审查帮我看代码" | → 匹配Code Reviewer角色 → 注入角色上下文 → 执行 |
| "切换到后端架构师" | → 激活Backend Architect → 确认切换 |
| "现在有哪些角色" | → 列出184个Agent角色 |
| "什么状态" | → 显示运行状态 |

**支持的中文表达方式**："帮我写个..."、"写一个..."、"怎么实现..."、"用XX角色看看..."、"切换到XX模式"、"列出所有角色" 等。

## RAG 知识库覆盖领域

基础输出、排序算法、代码审查、基础算法、Web 开发、翻译、知识问答、系统命令、文件操作、API 开发、数据库设计、调试、测试、方案设计、性能优化、Agent 管理、系统状态（共 25 条映射）

## 快速开始

### 1. 安装依赖

```bash
pip install requests chromadb sentence-transformers
```

### 2. 配置飞书应用

参考 `FEISHU_SETUP.md` 完成飞书应用创建和配置。

### 3. 启动服务

**临时运行（前台调试）**：
```cmd
cd wechat-claude-demo
python run_feishu_poll.py
```

**永久运行（后台自启动）**：
```cmd
# 方式 1：直接双击批处理脚本
start_poll.bat

# 方式 2：注册为 Windows 任务计划（推荐，开机自启）
# 详见 startup-guide.md → 方案 A
```

### 4. 手机飞书测试

在飞书群聊中发送：
```
/run 输出Hello World
```

应收到 Claude Code 的执行结果回复。

## 核心特性

- **角色感知执行**：注入 184 个专业 Agent 角色提示词，Claude 以指定角色身份执行任务
- **语义检索增强**：口语化指令自动转换为标准化 Claude 指令，支持向量+规则双模式
- **智能分段回传**：保持代码块完整，在段落边界切割，自动添加分段标记 `[1/3]`
- **崩溃自动恢复**：start_poll.bat 内置无限重启循环，5 秒间隔自动拉起
- **日志自动轮转**：RotatingFileHandler（5 文件 × 5MB），不占满磁盘
- **Token 自动续期**：飞书 tenant_access_token 缓存 + 提前 60 秒刷新
- **低资源占用**：轮询间隔 2s，空闲内存占用 < 50MB

## 部署保障

- **崩溃自动重启**：start_poll.bat 内置无限重启循环（5 秒间隔）
- **日志自动轮转**：RotatingFileHandler，5 文件 × 5MB，不占满磁盘
- **Token 自动续期**：飞书 tenant_access_token 缓存 + 提前 60s 刷新
- **开机自启**：配合 Windows 任务计划程序实现
- **低资源占用**：轮询间隔 2s，空闲内存 < 50MB
