# Windows 后台服务部署指南

让 `run_feishu_poll.py` 持久运行，开机自启。

---

## 方案 A：Windows 任务计划程序（推荐，零依赖）

### 1. 创建启动脚本

项目目录已包含 `start_poll.bat`（内置崩溃自动重启循环），直接使用即可。

```bat
@echo off
chcp 65001 > nul
set "PROJECT_DIR=C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo"
cd /d "%PROJECT_DIR%"
set "PYTHON=C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe"
"%PYTHON%" -u run_feishu_poll.py
:: 退出后 5 秒自动重启
```

### 2. 添加任务计划

```powershell
# 以管理员身份运行 PowerShell
$action = New-ScheduledTaskAction -Execute "C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo\start_poll.bat"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "丁溱烁" -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "FeishuClaudeBot" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "飞书→Claude Code 轮询机器人"
```

### 3. 管理命令

```powershell
# 立即启动
Start-ScheduledTask -TaskName "FeishuClaudeBot"

# 停止
Stop-ScheduledTask -TaskName "FeishuClaudeBot"

# 查看状态
Get-ScheduledTask -TaskName "FeishuClaudeBot"

# 删除
Unregister-ScheduledTask -TaskName "FeishuClaudeBot" -Confirm:$false
```

---

## 方案 B：NSSM（Non-Sucking Service Manager）

### 1. 安装 NSSM

```powershell
# 下载 nssm.exe → 放到 C:\Windows\ 或项目目录
# https://nssm.cc/download
```

### 2. 创建服务

```powershell
nssm install FeishuClaudeBot
```

弹出窗口填写：

| 字段 | 值 |
|------|-----|
| Application | `C:\Users\丁溱烁\AppData\Local\Programs\Python\Python311\python.exe` |
| Arguments | `run_feishu_poll.py` |
| Startup directory | `C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo` |

### 3. 管理命令

```powershell
nssm start FeishuClaudeBot   # 启动
nssm stop FeishuClaudeBot    # 停止
nssm restart FeishuClaudeBot # 重启
nssm status FeishuClaudeBot  # 状态
nssm remove FeishuClaudeBot  # 删除
```

---

## 日志查看

```powershell
# 实时跟踪
Get-Content C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo\feishu_poll.log -Wait

# 查看最近 50 行
Get-Content C:\Users\丁溱烁\WorkBuddy\2026-05-20-task-4\wechat-claude-demo\feishu_poll.log -Tail 50
```

---

## 注意事项

- 任务计划方案开机即启动，无需登录用户
- 飞书 Token 有效期 2 小时，脚本自动续期
- 崩溃自动重启（`RestartCount 999` = 最多重启 999 次）
- 日志自动轮转（RotatingFileHandler，5 文件 × 5MB），无需手动清理
- Agent 角色首次加载需扫描 184 个 .md 文件，启动约需 1 秒
- RAG 向量模式首次启动需下载 all-MiniLM-L6-v2 模型（~90MB），后续即时加载

## 支持指令说明

| 指令 | 功能 |
|------|------|
| `/run <指令>` | 使用当前激活的 Agent 角色执行任务 |
| `/activate <角色名>` | 切换 Agent 角色（如 Code Reviewer、Backend Architect） |
| `/agent <角色名> <指令>` | 一次性使用指定角色执行 |
| `/list agents` | 查看全部 184 个可用角色（按领域分组） |
| `/status` | 查看当前运行状态和已激活角色 |
