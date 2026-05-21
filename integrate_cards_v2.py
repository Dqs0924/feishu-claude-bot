#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动化修改 run_feishu_poll.py：
  将 _handle_activate 和 _handle_status 改为调用卡片模块
  避开特殊字符匹配问题，直接字符串操作
"""

import re, os

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_feishu_poll.py")

with open(TARGET, "r", encoding="utf-8") as f:
    content = f.read()

# ── 修改1：_handle_activate 方法 ─────────────────────
# 在 return f"已激活角色... 之前插入卡片发送代码
old_active = '                    return f"已激活角色：{info[\'name\']}（{info[\'domain\']}）\\n{info[\'description\']}", True'
new_active = (
    '                    # 尝试发送激活确认卡片\n'
    '                    if fc and message_id:\n'
    '                        try:\n'
    '                            fc.send_agent_activated(message_id, info["name"], info["domain"], info["description"])\n'
    '                            return None, True\n'
    '                        except Exception as e:\n'
    '                            log.warning(f"[Card] 激活卡片失败：{e}")\n'
    '                    # 降级为纯文本\n'
    '                    return f"已激活角色：{info[\'name\']}（{info[\'domain\']}）\\n{info[\'description\']}", True'
)

if old_active in content:
    content = content.replace(old_active, new_active, 1)
    print("[OK] _handle_activate 已插入卡片代码（info 分支）")
else:
    print("[跳过] 未找到 _handle_activate 中的 info 分支 return")

# 处理第二个 return f"已激活角色...（search 分支）
old_active2 = '                return f"已激活角色：{info[\'name\']}（{info[\'domain\']}）\\n{info[\'description\']}", True'
if old_active2 in content:
    # 只替换第一个（已经替换过了），现在替换第二个
    idx = content.find(old_active2)
    if idx > 0:
        # 检查是否已经插入了卡片代码
        prev = content[max(0, idx-500):idx]
        if 'send_agent_activated' not in prev:
            new_active2 = (
                '                # 尝试发送激活确认卡片\n'
                '                if fc and message_id:\n'
                '                    try:\n'
                '                        fc.send_agent_activated(message_id, info["name"], info["domain"], info["description"])\n'
                '                        return None, True\n'
                '                    except Exception as e:\n'
                '                        log.warning(f"[Card] 激活卡片失败：{e}")\n'
                '                # 降级为纯文本\n'
                '                return f"已激活角色：{info[\'name\']}（{info[\'domain\']}）\\n{info[\'description\']}", True'
            )
            content = content.replace(old_active2, new_active2, 1)
            print("[OK] _handle_activate 已插入卡片代码（search 分支）")
        else:
            print("[跳过] _handle_activate search 分支已有卡片代码")
    else:
        print("[跳过] 未找到 _handle_activate search 分支")

# ── 修改2：_handle_status 方法 ───────────────────────
# 在 return self.agents.status(), True 之前插入卡片发送
old_status = '        return self.agents.status(), True'
new_status = (
    '        # 尝试发送状态卡片\n'
    '        if fc and message_id:\n'
    '            try:\n'
    '                status_text = self.agents.status()\n'
    '                fc.send_status(message_id, status_text)\n'
    '                return None, True\n'
    '            except Exception as e:\n'
    '                log.warning(f"[Card] 状态卡片失败：{e}")\n'
    '        # 降级为纯文本\n'
    '        return self.agents.status(), True'
)

if old_status in content:
    content = content.replace(old_status, new_status, 1)
    print("[OK] _handle_status 已插入卡片代码")
else:
    print("[跳过] 未找到 _handle_status return")

# ── 修改3：SmartRouter.route 传入 message_id ─────────────
# _handle_activate 调用时传入 message_id
old_route_act = '                return self._handle_activate(text), True'
if old_route_act in content:
    content = content.replace(old_route_act, '                return self._handle_activate(text, message_id), True', 1)
    print("[OK] route: _handle_activate 已传入 message_id")
else:
    print("[跳过] 未找到 route 中的 _handle_activate 调用")

# _handle_status 调用时传入 message_id
old_route_stat = '            return self._handle_status(), True'
if old_route_stat in content:
    content = content.replace(old_route_stat, '            return self._handle_status(message_id), True', 1)
    print("[OK] route: _handle_status 已传入 message_id")
else:
    print("[跳过] 未找到 route 中的 _handle_status 调用")

# ── 修改4：_handle_task 传入 message_id 给 call_claude ──
# （可选，当前已完成状态推送卡片化，此步略过）

# 写回文件
with open(TARGET, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n[完成] 文件已更新：{TARGET}")
print("[注意] 请运行语法检查：python -m py_compile run_feishu_poll.py")
