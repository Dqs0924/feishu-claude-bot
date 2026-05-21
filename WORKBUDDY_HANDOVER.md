# WorkBuddy 对接提示词

> 直接复制以下内容发送给 WorkBuddy 即可

---

## 项目接管提示词

```
你现在接管以下项目，开始日常运维：

项目路径：C:\Users\丁溱烁\WorkBuddy\2026-05-21-task-5\wechat-claude-demo\

## 你的职责

1. 启动并保持服务在线
   - 启动 Webhook：python start_webhook.py（预初始化，飞书验证秒回）
   - 启动 ngrok：.\ngrok.exe http 8090
   - 验证在线：curl -X POST http://127.0.0.1:8090/webhook -H "Content-Type: application/json" -d "{\"type\":\"url_verification\",\"challenge\":\"test\"}" → 返回 {"challenge":"test"} 即正常

2. 日常运维
   - 查看日志：tail -f webhook.log 或 feishu_poll.log
   - 检查状态：netstat -ano | findstr :8090（端口监听即正常）
   - 服务挂了：重新执行启动命令即可

3. 配置调整（直接改文件，无需写代码）
   - 飞书参数：编辑 config.json → feishu 节
   - 模型切换：编辑 config.json → claude 节（default_model: haiku/sonnet/opus）
   - 知识库扩充：编辑 instruction_kb.json，添加 {"oral":"口语","standard":"标准指令","desc":"描述"}，重启自动生效
   - 轮询间隔：编辑 config.json → polling.interval

4. 测试验证
   - 在飞书群发 "帮我写个快速排序" 看有没有回复
   - 发 "现在有哪些角色" 看是否列出Agent
   - 发 "切换到代码审查" 看是否激活角色

## 什么时候找我（Claude）

只有以下情况才需要联系我：
- Python报错 traceback（进程崩溃）
- 飞书API返回错误（code非0）
- ClaudeCode调用失败
- 功能完全不通（不是配置问题）
- Token消耗异常暴涨
- 环境变化导致不兼容

常规的启动/停止/配置修改/日志查看/测试验证你都自己搞定。

## 快速参考

- 完整文档：PROJECT_FINAL.md
- 项目结构：PROJECT_OVERVIEW.md  
- 部署指南：startup-guide.md
- 所有配置文件路径都在 PROJECT_FINAL.md 第一章

开始吧，先检查服务是否在线。
```

---

## 服务健康检查清单（WorkBuddy 每日）

| 检查项 | 命令 | 预期结果 |
|--------|------|---------|
| Webhook端口 | `netstat -ano \| findstr :8090` | LISTENING |
| ngrok进程 | `tasklist \| findstr ngrok` | ngrok.exe |
| 本地验证 | `curl -X POST http://127.0.0.1:8090/webhook -H "Content-Type: application/json" -d "{\"type\":\"url_verification\",\"challenge\":\"health\"}"` | `{"challenge":"health"}` |
| 公网验证 | `curl -X POST https://shining-barge-denote.ngrok-free.dev/webhook -H "Content-Type: application/json" -H "ngrok-skip-browser-warning: true" -d "{\"type\":\"url_verification\",\"challenge\":\"health\"}"` | `{"challenge":"health"}` |

---

> 以上内容直接复制给 WorkBuddy 即可开始对接
