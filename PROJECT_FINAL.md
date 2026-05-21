# 飞书→ClaudeCode 远程智能调度系统 — 最终交付文档

> 版本：v3.1 | 日期：2026-05-21 | 状态：✅ 生产就绪

---

## 一、项目全量状态汇总

### 1.1 已完成功能（100%）

| 功能 | 说明 |
|------|------|
| 飞书消息轮询 | 2s间隔轮询，`ByCreateTimeDesc`排序，`seen_ids`防重复 |
| 自然语言自由输入 | 零指令格式，口语化表达直接触发（v3.0） |
| 智能意图识别 | 5类自动分流：编程任务/角色激活/角色列表/状态查询/闲聊过滤 |
| RAG语义增强 | ChromaDB向量检索 + 规则双模式，109条知识库 |
| ClaudeCode执行 | 真实CLI调用，`--dangerously-skip-permissions` |
| Agent角色调度 | 226个角色，184个已索引，131条中英文别名 |
| 模型分级 | v4-flash默认（低成本）/ v4-pro复杂任务（自动触发） |
| Agent上下文精简 | 3000→500字智能提取（Critical Rules优先） |
| 智能分段回传 | 段落边界切割，代码块保持，`[1/N]`编号 |
| 飞书卡片美化 | 处理中卡片/完成卡片/降级纯文本，3种模式 |
| 配置外置化 | `config.json`统一管理飞书/模型/Webhook/RAG参数 |
| 上下文记忆 | 多轮对话，max_history=20，max_age=30min |
| Webhook服务器 | 预初始化模式，飞书验证秒回（<1s） |
| GUI管理面板 | Tkinter可视化，配置/日志/服务管理（需桌面环境） |
| 日志轮转 | RotatingFileHandler 5×5MB，不占满磁盘 |
| 崩溃自动重启 | `start_poll.bat` 内置重启循环（5s间隔） |
| 消息防重复 | `seen_ids`集合，已处理消息永久跳过 |

### 1.2 已验证通过的模块

| 模块 | 验证结果 | 验证方式 |
|------|---------|---------|
| 飞书Token获取 | ✅ | API返回 code=0 |
| 消息轮询 | ✅ | 获取到群聊消息 |
| 消息回复 | ✅ | reply API返回 code=0 |
| SmartRouter路由 | ✅ | 5类意图全部分类正确 |
| Agent加载/搜索/激活 | ✅ | 184角色，中英文模糊匹配 |
| RAG向量检索 | ✅ | ChromaDB + all-MiniLM-L6-v2 |
| Claude CLI调用 | ✅ | 多次返回正确结果(165-940字符) |
| 智能分段 | ✅ | 长文本正确分块 |
| Webhook本地 | ✅ | URL验证返回challenge |
| Webhook公网(ngrok) | ✅ | `{"challenge":"xxx"}` 正确响应 |
| 飞书平台事件订阅 | ✅ | 已验证通过 |
| GUI模块导入 | ✅ | Tkinter可用，类实例化正常 |

### 1.3 已稳定运行的服务

| 服务 | 端口 | 状态 | 启动命令 |
|------|------|------|---------|
| Webhook服务器 | 8090 | 🟢 常驻 | `python start_webhook.py` |
| ngrok隧道 | — | 🟢 常驻 | `ngrok http 8090` |
| 轮询服务 | — | 🔵 按需 | `python -u run_feishu_poll.py` |

### 1.4 核心配置

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `C:\Users\丁溱烁\WorkBuddy\2026-05-21-task-5\wechat-claude-demo\` |
| 飞书App ID | `cli_xxxxxxxxxxxxx` |
| 目标群聊 | `oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| Webhook公网URL | `https://shining-barge-denote.ngrok-free.dev/webhook` |
| 飞书事件订阅 | ✅ 已验证通过 |
| 默认AI模型 | deepseek-v4-flash（复杂任务自动切换v4-pro） |
| Python | `C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe` |
| Agent库 | `C:\Users\丁溱烁\.claude\agents\`（226角色） |
| Skills库 | `C:\Users\丁溱烁\.claude\skills\`（8模块） |

---

## 二、未完成/需持续维护项

### 2.1 无需技术开发

| 项目 | 说明 |
|------|------|
| RAG知识库扩充 | 编辑 `instruction_kb.json`，重启自动同步向量库 |
| Agent别名补充 | 编辑 `run_feishu_poll.py` 中 `AGENT_ALIASES` 字典 |
| 飞书卡片样式微调 | 编辑 `feishu_cards.py`，改颜色/文案/布局 |

### 2.2 仅需日常维护

| 项目 | 频率 | 操作 |
|------|------|------|
| 日志查看 | 按需 | `tail -f feishu_poll.log` 或 `tail -f webhook.log` |
| 服务状态检查 | 按需 | GUI面板 → 状态监控 → 刷新 |
| 端口占用检查 | 异常时 | `netstat -ano | findstr :8090` |
| Agent库更新 | 偶尔 | 往 `~/.claude/agents/` 添加.md → 重启 |

### 2.3 WorkBuddy可处理的轻量任务

- 修改飞书群（`config.json` → `feishu.chat_id`）
- 调整轮询间隔（`config.json` → `polling.interval`）
- 更换AI模型（`config.json` → `claude.default_model`）
- 启动/停止/重启服务
- GUI面板日常操作
- 飞书卡片文案调整

---

## 三、分工边界

### WorkBuddy 全权负责

```
✅ 服务启停（python start_webhook.py / start_poll.bat）
✅ 日志查看与日常监控
✅ 配置修改（config.json）
✅ 知识库扩充（instruction_kb.json）
✅ 飞书卡片样式微调（feishu_cards.py）
✅ Agent别名补充（AGENT_ALIASES字典）
✅ 常规功能测试（发飞书消息验证）
✅ GUI面板操作
✅ 运行参数微调（间隔/超时/模型）
```

### Claude 仅负责

```
🔴 进程崩溃无法启动（Python traceback / 依赖缺失）
🔴 飞书API报错（Token失效 / 权限变更 / code非0）
🔴 ClaudeCode调用失败（subprocess异常 / CLI路径变更）
🔴 功能逻辑BUG（消息路由错误 / Agent匹配失败）
🔴 性能异常（Token暴涨 / 内存泄漏 / 日志爆炸）
🔴 环境适配（Python/Node升级 / Windows更新兼容）
🔴 架构变更（新增通信协议 / 替换消息通道）
```

---

## 四、标准启动流程

### 4.1 启动 ngrok

```cmd
cd C:\Users\丁溱烁\WorkBuddy\2026-05-21-task-5\wechat-claude-demo
.\ngrok.exe http 8090
```

预期看到：
```
Forwarding  https://shining-barge-denote.ngrok-free.dev -> http://localhost:8090
```

### 4.2 启动 Webhook 服务器

```cmd
cd C:\Users\丁溱烁\WorkBuddy\2026-05-21-task-5\wechat-claude-demo
C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe start_webhook.py
```

预期输出：
```
[1/4] 导入 run_feishu_poll...
[2/4] 加载 AgentManager (184角色)...
[3/4] 初始化 RAG 引擎...
[4/4] 创建 SmartRouter...
[就绪] http://0.0.0.0:8090/webhook
```

### 4.3 验证在线状态

```cmd
:: 本地验证
curl -X POST http://127.0.0.1:8090/webhook -H "Content-Type: application/json" -d "{\"type\":\"url_verification\",\"challenge\":\"test\"}"

:: 公网验证
curl -X POST https://shining-barge-denote.ngrok-free.dev/webhook -H "Content-Type: application/json" -H "ngrok-skip-browser-warning: true" -d "{\"type\":\"url_verification\",\"challenge\":\"test\"}"
```

正常返回：`{"challenge": "test"}`

### 4.4 飞书测试指令

在飞书群聊中发送任意自然语言：
```
帮我写个Python冒泡排序
切换到代码审查模式
现在有哪些可用的角色
现在什么状态
```

---
> 文档结束 | 可直接交付使用
