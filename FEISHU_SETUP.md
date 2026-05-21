# 飞书机器人接入指南

## 第一步：创建飞书自建应用

1. 打开 👉 https://open.feishu.cn/app
2. 点击「创建企业自建应用」
3. 填写应用名称（如：`AI编程助手`），上传图标，点击「创建」
4. 创建成功后，进入应用详情页，记录：
   - **App ID**（形如：cli_xxxxx）
   - **App Secret**（点击「查看」后复制）

---

## 第二步：启用机器人能力

1. 在应用详情页，点击「添加应用能力」
2. 找到「机器人」，点击「添加」
3. 确认添加成功

---

## 第三步：配置权限

1. 左侧菜单 →「权限管理」
2. 搜索并开通以下权限（需点击「开通权限」）：
   - `im:message`（接收消息）
   - `im:message:send`（发送消息）
   - `im:message.p2p:readonly`（获取私聊消息）
   - `im:chat`（获取群信息，可选）
3. 开通后点击「发布版本」，等待管理员审核（个人创建的应用自动通过）

---

## 第四步：配置事件订阅（接收消息用）

### 方式 A：Webhook 模式（推荐，实时性好）

1. 左侧菜单 →「事件订阅」
2. 在「请求网址」处填写你的服务器 URL，格式：
   ```
   http://你的服务器IP:8080/feishu-webhook
   ```
3. 本地调试可以用 **ngrok** 暴露端口：
   ```bash
   # 安装 ngrok：https://ngrok.com/download
   ngrok http 8080
   # 把生成的 https://xxxx.ngrok-free.app 填到飞书后台
   ```
4. 点击「添加事件」，勾选：
   - `im.message.receive_v1`（接收消息）
5. 点击「保存」

### 方式 B：轮询模式（无需服务器，适合快速测试）

1. 不需要配置事件订阅
2. 在飞书里找到你的机器人，发送一条消息，复制 URL 中的 `oc_xxxxx`（这是 chat_id）
3. 在 `run_demo.py` 里填入这个 chat_id

---

## 第五步：发布应用

1. 左侧菜单 →「版本管理与发布」
2. 点击「创建版本」，填写版本号和更新说明
3. 点击「发布」
4. 发布后，在「应用管理」→「可用范围」里，确保「所有员工」可见（个人版直接可用）

---

## 第六步：获取凭证并配置

将 App ID 和 App Secret 填入以下任一位置：

### 方式 1：环境变量（推荐）
```bash
export FEISHU_APP_ID="cli_你的App_ID"
export FEISHU_APP_SECRET="你的App_Secret"
python run_demo.py --platform feishu --mode webhook
```

### 方式 2：直接修改代码
编辑 `feishu_listener.py` 顶部：
```python
APP_ID     = "cli_你的App_ID"
APP_SECRET = "你的App_Secret"
```

---

## 第七步：测试

1. 在飞书里找到你的机器人（搜索应用名称）
2. 发送：`/run 用 Python 写一个快速排序函数`
3. 正常情况会收到回复 ✅

---

## 常见问题

### Q：事件订阅 URL 验证失败？
A：确保 `feishu_listener.py` 的 Webhook 服务器正在运行，端口已放行防火墙。

### Q：发送消息提示「没有权限」？
A：检查「权限管理」里 `im:message:send` 是否已开通并发布版本。

### Q：机器人收不到消息？
A：检查「事件订阅」里 `im.message.receive_v1` 事件是否已订阅，且 Webhook URL 可访问。

---

## 下一步

配置完成后，编辑 `run_demo.py`，在 main 函数里添加飞书模式支持，然后运行：
```bash
python run_demo.py --platform feishu --mode webhook
```
