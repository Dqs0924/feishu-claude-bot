# WorkBuddy 对接交付包 — 飞书→ClaudeCode 远程智能调度系统

> 交付日期：2026-05-21 | 版本：v3.1 | 状态：生产就绪
> Claude角色：技术后盾（仅处理WorkBuddy无法自行解决的疑难问题）

---

## 一、项目位置

**主项目**（生产环境，最新功能）：
```
C:\Users\丁溱烁\WorkBuddy\2026-05-21-task-5\wechat-claude-demo\
```

**旧版项目**（参考备份，功能完整但无新增模块）：
```
C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo\
```

---

## 二、核心文件清单（按功能分区）

### 分区A：主程序 [启动即运行]

| 文件 | 用途 | 启动方式 |
|------|------|---------|
| `run_feishu_poll.py` | ★ 轮询主程序 | `python -u run_feishu_poll.py` |
| `feishu_webhook.py` | Webhook服务器 | `python feishu_webhook.py`（含自检） |
| `gui_manager.py` | GUI管理面板 | `python gui_manager.py`（需桌面） |
| `start_poll.bat` | 批处理启动+崩溃重启 | 双击运行 |

### 分区B：配置文件

| 文件 | 用途 | 可修改项 |
|------|------|---------|
| `config.json` | ★ 统一配置 | APP_ID/SECRET/CHAT_ID/端口/模型/知识库参数 |
| `C:\Users\丁溱烁\.claude\settings.json` | Claude模型配置 | API密钥/模型选择/权限 |

### 分区C：功能模块（被主程序引用，不独立运行）

| 文件 | 功能 |
|------|------|
| `rag_module.py` | RAG语义引擎（ChromaDB向量+规则双模式） |
| `feishu_cards.py` | 飞书交互式卡片（3种卡片类型） |
| `feishu_listener.py` | 飞书API完整封装（备用） |
| `call_claude.py` | Claude CLI调用封装（备用） |
| `result_callback.py` | 结果回传+outbox存档 |

### 分区D：知识库与数据

| 文件/目录 | 内容 |
|----------|------|
| `instruction_kb.json` | RAG知识库：109条口语→标准指令映射 |
| `rag_db/` | ChromaDB向量数据库（自动同步） |

### 分区E：外部资源（不在项目目录内）

| 资源 | 路径 | 说明 |
|------|------|------|
| Agent角色库 | `C:\Users\丁溱烁\.claude\agents\` | 226个.md角色文件，18个领域 |
| Skills规则库 | `C:\Users\丁溱烁\.claude\skills\` | 8个技能模块 |
| Claude配置 | `C:\Users\丁溱烁\.claude\settings.json` | API端点+模型+权限 |
| CLAUDE.md | `d:\agent实现文档\CLAUDE.md` | 全局行为契约 |

### 分区F：文档

| 文件 | 用途 |
|------|------|
| `PROJECT_OVERVIEW.md` | 完整项目结构总览 |
| `README.md` | 快速开始+功能说明 |
| `startup-guide.md` | Windows部署指南 |
| `FEISHU_SETUP.md` | 飞书应用配置教程 |
| `system-design.md` | 系统架构设计 |
| `对接文档.md` | 中文详细对接文档 |
| `HANDOVER.md` | ★ 本文档（WorkBuddy对接） |

---

## 三、已完成的全部功能

| 功能 | 版本 | 状态 |
|------|------|------|
| 飞书消息轮询监听 | v1.0 | ✅ |
| RAG语义增强（规则+向量双模式） | v1.0 | ✅ |
| ClaudeCode CLI真实调用 | v1.0 | ✅ |
| 智能分段回传 | v1.0 | ✅ |
| 日志轮转+崩溃重启 | v1.0 | ✅ |
| Agent角色自动调度（226角色） | v2.0 | ✅ |
| 自然语言自由输入（无需/command） | v3.0 | ✅ |
| 智能意图识别（5类自动分流） | v3.0 | ✅ |
| 中英文Agent别名匹配（131条） | v3.0 | ✅ |
| 闲聊过滤+重复消息防护 | v3.0 | ✅ |
| 模型分级调度（v4-flash/v4-pro） | v3.0 | ✅ |
| Agent上下文精简（3000→500字） | v3.0 | ✅ |
| Token智能管控 | v3.0 | ✅ |
| 配置外置化（config.json） | v3.1 | ✅ |
| 上下文记忆机制（多轮对话） | v3.1 | ✅ |
| 任务实时状态推送（处理中卡片） | v3.1 | ✅ |
| RAG知识库扩充（37→109条） | v3.1 | ✅ |
| 飞书消息卡片美化（3种卡片） | v3.1 | ✅ |
| Webhook服务器（含自检） | v3.1 | ✅ [今日修复] |
| GUI管理面板（Tkinter） | v3.1 | ✅ [今日修复] |

---

## 四、今日修复的问题记录

| # | 问题 | 根因 | 修复文件 |
|---|------|------|---------|
| 1 | Webhook启动崩溃(Exit Code 1) | `import run_feishu_poll`触发模块级RAG+Agent全量初始化，零异常捕获 | feishu_webhook.py 重写 |
| 2 | Webhook端口硬编码8080 | 构造函数忽略config.json中8090配置 | feishu_webhook.py:__init__ |
| 3 | router.route()参数不兼容 | v3.1新增message_id参数未传递 | feishu_webhook.py:_handle_message |
| 4 | GUI导入崩溃风险 | 模块级import触发全部初始化 | gui_manager.py 重写 |
| 5 | GUI服务管理空壳 | 启动/停止按钮无实现代码 | gui_manager.py:ServiceManager |
| 6 | 旧版进程残留+消息死循环 | last_msg_id只记最后一条 | 所有修复在旧项目中已完成 |

---

## 五、WorkBuddy 自主运行指引

### 5.1 日常启动
```cmd
cd C:\Users\丁溱烁\WorkBuddy\2026-05-21-task-5\wechat-claude-demo

:: 方式1：轮询模式（推荐，最稳定）
C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe -u run_feishu_poll.py

:: 方式2：批处理（崩溃自动重启）
start_poll.bat

:: 方式3：Webhook模式（需公网IP或ngrok）
C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe feishu_webhook.py

:: 方式4：GUI面板（需桌面环境）
C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe gui_manager.py
```

### 5.2 常规调整（WorkBuddy可直接操作）
- **修改飞书群**：编辑 `config.json` → `feishu.chat_id`
- **更换模型**：编辑 `config.json` → `claude.default_model` / `claude.complex_model`
- **调整轮询间隔**：编辑 `config.json` → `polling.interval`
- **扩充知识库**：编辑 `instruction_kb.json`，重启后自动同步向量库
- **新增Agent别名**：编辑 `run_feishu_poll.py` → `AGENT_ALIASES` 字典
- **调整上下文记忆**：编辑 `config.json` → `conversation.max_history` / `max_age_minutes`

### 5.3 日常维护
- **查看日志**：`feishu_poll.log`（轮询）/ `webhook.log`（Webhook）
- **日志轮转**：自动（RotatingFileHandler，5×5MB），无需手动清理
- **向量库同步**：修改 `instruction_kb.json` 后重启自动重建
- **Agent更新**：在 `~/.claude/agents/` 添加.md文件后重启自动加载
- **端口占用**：`netstat -ano | findstr :8090` → `taskkill //PID <PID> //F`

---

## 六、Claude 升级规则

### Claude负责（WorkBuddy遇到以下问题时调用Claude）

| 级别 | 问题类型 | 示例 |
|------|---------|------|
| **P0** | 进程崩溃/无法启动 | Python traceback、DLL缺失、依赖错误 |
| **P1** | 飞书API报错 | Token失效、权限变更、API返回非0 code |
| **P1** | ClaudeCode调用失败 | subprocess异常、CLI路径变更、模型不可用 |
| **P1** | 功能逻辑BUG | 消息路由错误、Agent匹配失败、RAG误转换 |
| **P2** | 性能/资源异常 | Token暴涨、内存泄漏、日志爆炸 |
| **P2** | 环境适配问题 | Python/Node版本升级、Windows更新导致兼容问题 |
| **P3** | 架构变更需求 | 新增通信协议、替换消息通道、改变模型后端 |

### WorkBuddy自主完成（不需要Claude）
- 飞书配置调整（APP_ID/SECRET/CHAT_ID）
- 知识库内容扩充（instruction_kb.json）
- Agent别名补充（AGENT_ALIASES字典）
- 启动/停止/重启服务
- 日志查看与日常监控
- 参数微调（轮询间隔、超时时间、模型选择）
- GUI面板操作

### 调用Claude的方式
遇到上述P0-P3问题时，将**完整错误日志+复现步骤**发给Claude，Claude会：
1. 读取错误日志定位根因
2. 读取相关源码分析逻辑
3. 输出修复方案或直接修改代码
4. 重新测试验证

---

## 七、系统架构速览

```
手机飞书 ──→ 飞书开放平台API ──→ [轮询/Webhook监听]
                                      │
                              SmartRouter 自然语言路由
                              ├─ 闲聊过滤
                              ├─ 意图分类(5类)
                              ├─ Agent自动匹配(226角色+131别名)
                              └─ RAG语义增强(109条+ChromaDB)
                                      │
                              ClaudeCode CLI 执行
                              ├─ 模型分级(flash默认/pro复杂)
                              ├─ Agent上下文精简注入
                              └─ 多轮对话记忆
                                      │
                              智能分段 ──→ 飞书卡片回复
```

---

## 八、Python环境

```
可执行文件：C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe
版本：Python 3.11
关键依赖：requests, chromadb, sentence-transformers
安装命令：pip install requests chromadb sentence-transformers
Claude CLI：%APPDATA%\npm\claude.cmd (v2.1.145, 通过npm安装)
```

---

> **交付完成** | WorkBuddy可直接接手运行 | Claude待命处理P0-P3级疑难问题
