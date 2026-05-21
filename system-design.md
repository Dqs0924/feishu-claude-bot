# 基于飞书与 Claude Code 的远程智能编程协作系统

**系统设计文档 · 结课论文版**

---

## 摘要

本项目设计了一套基于飞书（Feishu）与 Claude Code 大语言模型的远程智能编程协作系统。用户通过手机飞书发送自然语言指令，系统自动完成指令解析、任务调度、代码生成与结果回传，实现"手机发指令，PC 自动编程"的远程协作体验。系统采用五层架构设计，引入 RAG（检索增强生成）技术提升指令理解准确率，遵循"CLI 优先、GUI 渐进"的开发路线，分四个阶段迭代完成。本系统可作为个人远程开发工具使用，具备进一步封装为独立软件产品的潜力。

**关键词：** 远程编程、大语言模型、飞书机器人、RAG、Claude Code

---

## 第一章 引言

### 1.1 研究背景

随着大语言模型（LLM）在代码生成领域的能力不断提升，开发者越来越依赖 AI 辅助编程工具来提升工作效率。Claude Code 作为 Anthropic 公司推出的 AI 编程助手，支持通过命令行接口（CLI）进行非交互式代码生成，具备强大的上下文理解能力和代码质量。

然而，现有 AI 编程工具主要以桌面端应用或 IDE 插件形式存在，开发者必须坐在电脑前才能使用。在实际开发场景中，开发者常有"不在电脑旁但需要快速验证一个想法"、"睡前突然想到一个算法思路想要试试"等需求，缺乏一种轻量、低门槛的远程触发方式。

飞书作为中国用户覆盖率最高的即时通讯工具，几乎全天候在线，是理想的远程指令入口。若能通过飞书发送自然语言指令，触发远程 PC 上的 Claude Code 自动执行编程任务并回传结果，将极大提升开发者的工作灵活性。

### 1.2 研究目标

本课题旨在设计并实现一套**基于飞书与 Claude Code 的远程智能编程协作系统**，达成以下目标：

1. **远程可达**：用户通过手机飞书即可触发 PC 端的 AI 编程任务，无需远程桌面或 SSH；
2. **自然语言交互**：用户使用日常语言描述需求，系统自动解析并转化为标准编程指令；
3. **端到端闭环**：指令发送 → 理解解析 → 代码生成 → 结果回传，全流程自动化；
4. **可扩展性**：系统架构支持后续扩展为独立软件产品，具备图形界面和插件生态。

### 1.3 本文结构

本文共分为六章：第一章引言，介绍研究背景与目标；第二章相关技术综述；第三章系统架构设计，详述五层架构；第四章核心模块设计，包括消息监听、RAG 增强、Claude Code 调用与结果回传；第五章开发与迭代计划；第六章总结与展望。

---

## 第二章 相关技术综述

### 2.1 Claude Code 与 AI 编程助手

Claude Code 是 Anthropic 推出的面向开发者的 AI 编程工具，支持通过 CLI 进行非交互式调用：

```bash
claude -p "用 Python 实现快速排序" --dangerously-skip-permissions
```

该方式适合程序化调用，输出为标准文本，便于结果解析与转发。其优势在于：
- 支持超长上下文（200K token），可理解完整项目代码库；
- 生成代码质量高，注释详尽；
- CLI 接口稳定，适合自动化集成。

### 2.2 飞书机器人技术

飞书开放平台提供官方 REST API，支持通过自建应用（Self-built App）实现机器人消息监听与主动发送，无需 Hook 或注入，稳定性高。

**两种消息接收方式**：

1. **Webhook 模式（推荐）**：飞书主动推送事件到指定 URL，实时性好，适合有公网 IP 或内网穿透的场景；
2. **轮询模式（简单）**：程序定期调用 API 拉取消息，无需配置 Webhook，适合快速测试。

**核心 API**：
- `POST /auth/v3/tenant_access_token/internal`：获取租户访问令牌；
- `POST /im/v1/messages?receive_id_type=chat_id`：发送文本消息；
- `POST /im/v1/messages/{message_id}/reply`：回复指定消息；
- `GET /im/v1/messages?container_id={chat_id}`：轮询拉取消息（轮询模式）。

**权限要求**（需在飞书开放平台后台开通）：
| 权限标识 | 说明 |
|---------|------|
| `im:message` / `im:message:send_as_bot` | 接收和发送消息 |
| `im:message.p2p_msg` | 接收私聊消息 |
| `im:message.group_msg` | 接收群聊消息 |
| `im:chat` 或 `im:chat:readonly` | 获取群聊列表（轮询模式需要） |

飞书开放平台文档完善、API 稳定，是企业级消息集成的首选方案。

### 2.3 RAG（检索增强生成）

RAG（Retrieval-Augmented Generation）是一种将检索与生成相结合的技术。在本系统中，RAG 的作用是：

**问题**：用户通过飞书发送的指令通常是口语化的，例如"帮我写个快排"，而 Claude Code 更擅长处理标准化指令，例如"用 Python 实现一个快速排序函数，包含详细注释"。

**方案**：构建本地知识库，将常见口语指令与标准指令进行映射。当用户发送口语指令时，系统通过向量检索或规则匹配，找到最匹配的标准指令，再传给 Claude Code 执行。

**实现方式**：
- **规则模式**（轻量）：基于 `difflib` 的字符串相似度匹配，无需额外依赖；
- **向量模式**（精准）：基于 Chroma + `all-MiniLM-L6-v2` 向量数据库，支持语义相似度检索。

### 2.4 技术选型总结

| 技术组件 | 选型方案 | 理由 |
|---------|---------|------|
| 消息监听 | 飞书开放平台 API (Python) | 官方 API、无需 Hook、稳定可靠 |
| AI 代码生成 | Claude Code CLI | 上下文大、代码质量高、CLI 友好 |
| 指令增强 | RAG (Chroma + all-MiniLM-L6-v2) | 轻量、本地化、无需联网 |
| 开发语言 | Python 3.11+ | 生态丰富、快速原型 |
| 后续 GUI | Electron / Tauri | 跨平台、可封装为独立软件 |

---

## 第三章 系统架构设计

### 3.1 总体架构（五层架构）

系统采用自底向上的五层架构设计，层间通过定义良好的接口进行通信，保证模块解耦与可替换性。

```
┌───────────┐
│                     Layer 5: 结果回传层                          │
│               Result Callback Layer                                │
│  将 Claude Code 执行结果通过飞书发送给用户（手机端）               │
└──────────────────────────┬──────────────────────────────────────┘
                             │ 执行结果（文本 / 文件）
┌──────────────────────────┴──────────────────────────────────────┐
│                     Layer 4: Claude Code 执行层                  │
│               Claude Code Execution Layer                         │
│  调用 claude -p "<instruction>" 执行 AI 代码生成               │
└──────────────────────────┬──────────────────────────────────────┘
                             │ 标准化指令
┌──────────────────────────┴──────────────────────────────────────┐
│                     Layer 3: RAG 智能调度层                     │
│               RAG Intelligent Scheduling Layer                   │
│  将口语化指令转化为标准化指令（规则匹配 / 向量检索）             │
└──────────────────────────┬──────────────────────────────────────┘
                             │ 原始指令（可能口语化）
┌──────────────────────────┴──────────────────────────────────────┐
│                     Layer 2: PC 消息监听层                      │
│               PC Message Listening Layer                         │
│  通过 飞书开放平台 监听飞书消息，过滤 /run 前缀指令              │
└──────────────────────────┬──────────────────────────────────────┘
                             │ 飞书消息流
┌──────────────────────────┴──────────────────────────────────────┐
│                     Layer 1: 移动端交互层                       │
│               Mobile Interaction Layer                           │
│  用户通过手机飞书发送指令（格式：/run <自然语言描述>）           │
└───────────┘
```

### 3.2 各层详细设计

#### Layer 1：移动端交互层

**功能**：用户通过手机飞书向"飞书机器人"或指定联系人发送指令。

**指令格式**：
```
/run 用 Python 写一个快速排序函数
/run 帮我写一个 React 的计数器组件
/run 解释一下快速排序的时间复杂度
```

**设计考量**：
- 以 `/run` 作为指令前缀，便于系统过滤普通聊天消息；
- 支持自然语言描述，降低使用门槛；
- 后续可扩展为 `@机器人 /run ...` 的群聊模式。

#### Layer 2：PC 消息监听层

**功能**：运行在 PC 端的飞书监听模块（`feishu_listener.py`），通过飞书开放平台 API 监听消息。

**核心流程**：
1. 初始化飞书监听模块，通过飞书开放平台 API 获取 tenant_access_token；
2. 启动 Webhook 服务器或轮询任务，实时接收飞书消息；
3. 过滤：仅处理文本消息，且内容以 `/run` 开头；
4. 提取指令内容，传递给上层（RAG 调度层）；
5. 若指令格式错误，直接通过飞书返回使用提示。

**关键技术**：
- 飞书开放平台 API（`feishu_listener.py`）：`get_token()` 获取令牌、`start_webhook()` 启动 Webhook、`poll_messages()` 轮询模式；
- 飞书开放平台 API 稳定，无需考虑客户端版本兼容性问题。

#### Layer 3：RAG 智能调度层

**功能**：将用户的口语化指令转化为 Claude Code 更易理解的标准化指令。

**两种工作模式**：

| 模式 | 技术实现 | 优点 | 缺点 |
|------|---------|------|------|
| 规则模式 | `difflib.get_close_matches` | 零依赖、响应快 | 只能处理已知指令 |
| 向量模式 | Chroma + all-MiniLM-L6-v2 | 支持语义理解、可扩展 | 需要安装依赖 |

**知识库结构**（`instruction_kb.json`）：
```json
{
  "用Python写一个快速排序": "用 Python 写一个快速排序函数，包含详细注释和时间复杂度分析",
  "写一个React计数器": "用 React + TypeScript 写一个计数器组件，包含加、减、重置功能，使用 Hooks",
  ...
}
```

**处理流程**：
```
用户输入："帮我写个快排"
    ↓
规则模式：difflib 相似度匹配
    ↓ 命中："用Python写一个快速排序" (score=0.85)
    ↓
输出标准化指令："用 Python 写一个快速排序函数，包含详细注释和时间复杂度分析"
```

#### Layer 4：Claude Code 执行层

**功能**：接收标准化指令，调用 Claude Code CLI 执行，获取生成结果。

**调用方式**：
```python
result = subprocess.run(
    ["claude", "-p", instruction, "--dangerously-skip-permissions"],
    capture_output=True, text=True, timeout=120
)
```

**关键设计**：
- `--dangerously-skip-permissions`：跳过交互式权限确认，适合自动化调用；
- `timeout=120`：防止单次任务耗时过长；
- 输出裁剪：Claude Code 输出可能较长，截取前 2000 字符通过飞书发送，完整结果写入文件。

#### Layer 5：结果回传层

**功能**：将 Claude Code 的执行结果回传给用户手机端。

**回传方式**：
1. **文本消息**：结果较短时（< 5000 字符），直接通过飞书发送；
2. **文件消息**：结果较长时，写入 `outbox/result_YYYYMMDD_HHMMSS.txt`，发送文件；
3. **格式化输出**：结果前附加指令摘要，便于用户在手机上快速浏览。

**容错设计**：
- 若飞书发送失败（如对方已退出登录），结果写入本地文件，等待下次连接；
- 支持"结果重发"指令：`/run 重发上一次结果`。

### 3.3 层间接口定义

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|---------|------|
| 飞书消息 → 监听层 | L1 → L2 | `{sender_open_id, content, msg_type}` | 飞书开放平台 消息对象 |
| 监听层 → RAG 层 | L2 → L3 | `{raw_instruction: str}` | 去掉 `/run` 前缀的原始指令 |
| RAG 层 → 执行层 | L3 → L4 | `{normalized_instruction: str}` | 标准化后的指令 |
| 执行层 → 回传层 | L4 → L5 | `{success: bool, output: str, error: str}` | 执行结果 |
| 回传层 → 飞书 | L5 → L1 | `send_text(target_wxid, content)` | 飞书开放平台 发送接口 |

---

## 第四章 核心模块详细设计

### 4.1 消息监听模块（`feishu_listener.py`）

```python
class FeishuListener:
    def __init__(self, on_instruction: Callable[[str, str], None]):
        """
        on_instruction(instruction, sender_open_id):
            收到有效指令时的回调函数
        """
        self.on_instruction = on_instruction
        self.on_instruction = on_instruction

    def start(self):
        self.listener.start()  # 启动飞书消息监听（Webhook 或轮询模式）

    def _on_feishu_message(self, msg):
        if msg.get("msg_type") != "text":
            return
        content = json.loads(msg.get("content", "{}")).get("text", "")
        if not content.startswith("/run"):
            return
        instruction = content[4:].strip()
        self.on_instruction(instruction, msg.get("sender_id", {}).get("open_id", ""))
```

**降级方案**：当 飞书开放平台 不可用（如飞书本不兼容）时，自动降级为模拟模式——从 `inbox/*.txt` 读取指令文件，模拟消息触发。

### 4.2 RAG 增强模块（`rag_module.py`）

```python
class RAGEngine:
    def __init__(self, kb_path="instruction_kb.json"):
        self.kb = self._load_kb(kb_path)
        self.embed_model = None  # 延迟加载

    def parse(self, user_input: str, threshold=0.5) -> str:
        """规则模式：基于 difflib 的相似度匹配"""
        matches = difflib.get_close_matches(
            user_input, self.kb.keys(), n=1, cutoff=threshold
        )
        if matches:
            return self.kb[matches[0]]
        return user_input  # 未匹配则原样返回

    def parse_vector(self, user_input: str) -> str:
        """向量模式：语义相似度检索"""
        if not self.embed_model:
            self._init_vector_mode()
        # ... Chroma 向量检索逻辑
```

### 4.3 Claude Code 调用模块（`call_claude.py`）

```python
def call_claude(instruction: str, timeout: int = 120) -> tuple[bool, str, str]:
    """
    调用 Claude Code CLI 执行指令
    返回: (success, output, error)
    """
    cmd = [
        _find_claude(),           # 自动查找 claude 可执行文件
        "-p", instruction,
        "--dangerously-skip-permissions"
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, shell=False
    )
    if result.returncode == 0:
        return True, result.stdout[:2000], ""  # 裁剪过长输出
    return False, "", result.stderr
```

### 4.4 结果回传模块（`feishu_callback.py`）

```python
def simulate_feishu_send(result_text: str, instruction: str) -> str:
    """模拟飞书发送（实际部署时调用 飞书开放平台 的 send_text）"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"result_{timestamp}.txt"
    filepath = os.path.join(OUTBOX_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(format_result(instruction, result_text))

    return filepath  # 返回文件路径，供飞书发送
```

---

## 第五章 开发与迭代计划

### 5.1 开发路线总览

系统遵循 **"CLI 优先、GUI 渐进"** 的开发路线，先通过命令行界面验证核心功能闭环，再逐步引入图形界面，最终封装为独立软件产品。

```
Phase 1: CLI Demo（核心闭环验证）     ← 当前阶段
    ↓
Phase 2: 功能增强（RAG 向量模式、多轮对话、错误处理完善）
    ↓
Phase 3: GUI 原型（Electron/Tauri 图形界面）
    ↓
Phase 4: 产品化（打包分发、自动更新、插件机制）
```

### 5.2 四阶段详细计划

#### Phase 1：核心闭环验证（2 周）

**目标**：实现"发送指令 → 接收指令 → 调用 Claude → 回传结果"的完整闭环。

| 任务 | 描述 | 验收标准 |
|------|------|----------|
| 1.1 飞书消息监听 | 集成 飞书开放平台，监听 `/run` 指令 | 能接收到手机发送的 `/run` 消息 |
| 1.2 Claude CLI 调用 | 验证 `claude -p` 非交互式调用 | 能成功调用并返回结果 |
| 1.3 结果回传 | 将结果通过飞书发送回手机 | 手机能收到执行结果 |
| 1.4 RAG 规则模式 | 实现基于 `difflib` 的指令标准化 | 口语指令能被正确转化 |

**交付物**：可运行的 Python Demo、使用文档。

#### Phase 2：功能增强（3 周）

**目标**：提升系统稳定性与智能化水平。

| 任务 | 描述 |
|------|------|
| 2.1 RAG 向量模式 | 集成 Chroma + all-MiniLM-L6-v2，支持语义理解 |
| 2.2 多轮对话支持 | 支持"接着上一次的修改"、"加个注释"等上下文指令 |
| 2.3 错误处理完善 | 网络异常、Claude API 限流、飞书断连的自动恢复 |
| 2.4 配置管理 | 支持配置文件（YAML/JSON）管理飞书账号、Claude 模型选择等 |

**交付物**：功能完备的 Python 应用、单元测试。

#### Phase 3：GUI 原型（4 周）

**目标**：开发图形界面，提升易用性，为产品化做准备。

| 任务 | 描述 |
|------|------|
| 3.1 UI 设计 | 设计主窗口（连接状态、指令历史、结果预览） |
| 3.2 Electron 实现 | 使用 Electron + React 实现跨平台 GUI |
| 3.3 实时日志 | GUI 中实时显示系统运行日志 |
| 3.4 一键启动 | 图形界面中一键启动/停止飞书监听 |

**交付物**：可安装的 GUI 应用（Windows `.exe`）。

#### Phase 4：产品化（4 周）

**目标**：封装为独立软件产品，支持分发与持续迭代。

| 任务 | 描述 |
|------|------|
| 4.1 打包分发 | 使用 `electron-builder` 或 `tauri` 打包为安装包 |
| 4.2 自动更新 | 集成自动更新机制（检查版本、下载、安装） |
| 4.3 插件机制 | 支持第三方插件扩展（新的指令解析器、新的 LLM 后端等） |
| 4.4 文档完善 | 用户手册、开发者文档、API 文档 |

**交付物**：可公开发布的软件产品（GitHub Release / 官网下载）。

### 5.3 CLI 优先的设计理由

1. **快速验证核心假设**：CLI 可以在 1-2 周内完成核心闭环，快速验证"飞书 + Claude Code"方案的可行性；
2. **降低技术风险**：GUI 涉及界面设计、事件循环、跨线程通信等复杂问题，延后处理可避免早期过度设计；
3. **迭代反馈**：CLI 阶段可以收集用户（自己）的真实使用反馈，指导后续 GUI 的功能优先级；
4. **便于调试**：CLI 日志输出直观，便于排查飞书注入失败、Claude API 异常等问题。

---

## 第六章 系统评估与展望

### 6.1 可行性评估

**技术可行性**：✅ 高
- 飞书开放平台 和 Claude Code CLI 均为成熟技术，社区有充足参考资料；
- Python 生态完善，RAG 相关库（Chroma、sentence-transformers）开箱即用；
- Demo 阶段已验证核心闭环（模拟模式）。

**使用可行性**：✅ 高
- 用户无需学习新工具，使用习惯的飞书即可；
- 指令格式简单（`/run <描述>`），学习成本低。

**维护可行性**：⚠️ 中
- 飞书开放平台更新频繁，飞书开放平台 需跟进适配；
- 飞书开放平台 API 无需版本锁定，但需注意 API 权限申请和审核。

### 6.2 局限性分析

1. **飞书本依赖**：目前仅支持飞书 3.9.x，4.x 版本暂不支持；
2. **Claude API 费用**：Claude Code 调用需消耗 API Token，高频使用存在成本；
3. **结果长度限制**：飞书单条消息有长度限制（约 5000 字符），超长结果需分段发送或发送文件；
4. **安全性**：飞书账号需保持登录状态，存在账号安全风险（建议使用飞书机器人）。

### 6.3 未来展望

1. **多平台支持**：除飞书外，支持 Telegram、Discord、Slack 等消息平台；
2. **多模型支持**：除 Claude 外，集成 GPT-4、Gemini、本地 LLM（Ollama）等；
3. **项目上下文管理**：支持用户上传完整项目代码库，Claude Code 在完整上下文下生成代码；
4. **协作模式**：支持多人共享一个 Claude Code 实例，适合小团队使用；
5. **移动端 App**：开发独立的移动端 App，不依赖飞书，功能更完整。

---

## 结论

本文设计并实现了一套基于飞书与 Claude Code 的远程智能编程协作系统。系统采用五层架构设计，通过 飞书开放平台 实现飞书消息监听，通过 RAG 技术提升指令理解准确率，通过 Claude Code CLI 实现 AI 代码生成。系统遵循"CLI 优先、GUI 渐进"的开发路线，分四个阶段迭代完成，当前已完成核心闭环验证（Demo 阶段）。

本系统的创新点在于：
1. **低门槛远程触发**：利用飞书作为入口，用户无需安装额外 App；
2. **RAG 增强的指令理解**：通过规则 + 向量两种模式，将口语化指令转化为标准化指令；
3. **可渐进的产品化路线**：从 CLI Demo 到独立软件产品，每一步都有明确的交付物和验收标准。

本系统可作为个人远程开发工具使用，具备进一步封装为独立软件产品的潜力，为 AI 编程工具的远程化、移动化提供了一种可行的技术方案。

---

## 参考文献

[1] Anthropic. Claude Code Documentation. https://docs.anthropic.com/claude-code
[2] lich0821. 飞书开放平台: Feishu PC Hook Framework. https://github.com/lich0821/飞书开放平台
[3] Lewis, P. et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS 2020.
[4] Chroma. Open-source Embedding Database. https://www.trychroma.com/
[5] sentence-transformers. All MiniLM L6 v2 Model. https://www.sbert.net/
[6] Anthropic. Claude API Pricing. https://www.anthropic.com/pricing

---

*文档版本：v1.0 | 日期：2026-05-20 | 作者：丁溱烁*
