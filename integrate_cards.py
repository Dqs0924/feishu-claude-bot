#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 message_id 传入各 handler，并在合适位置调用卡片模块"""

import re, os

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_feishu_poll.py")

with open(TARGET, "r", encoding="utf-8") as f:
    content = f.read()

# ── 1. _handle_activate 加 message_id 参数 ───────────
old = "    def _handle_activate(self, text):"
new = "    def _handle_activate(self, text, message_id=None):"
if old in content:
    content = content.replace(old, new, 1)
    print("[1] _handle_activate 已加 message_id 参数")
else:
    print("[跳过] _handle_activate 签名已修改或不存在")

# ── 2. _handle_status 加 message_id 参数 ──────────────
old = "    def _handle_status(self):"
new = "    def _handle_status(self, message_id=None):"
if old in content:
    content = content.replace(old, new, 1)
    print("[2] _handle_status 已加 message_id 参数")
else:
    print("[跳过] _handle_status 签名已修改或不存在")

# ── 3. _handle_list 加 message_id 参数 ─────────────────
old = "    def _handle_list(self):"
new = "    def _handle_list(self, message_id=None):"
if old in content:
    content = content.replace(old, new, 1)
    print("[3] _handle_list 已加 message_id 参数")
else:
    print("[跳过] _handle_list 签名已修改或不存在")

# ── 4. route() 调用 handler 时传入 message_id ─────────
# 找到所有 self._handle_xxx( 调用，加入 message_id 参数
# 先处理 _handle_activate
old = "                return self._handle_activate(text), True"
new = "                return self._handle_activate(text, message_id)"
if old in content:
    content = content.replace(old, new, 1)
    print("[4] route: _handle_activate 已传 message_id")
else:
    print("[跳过] route 中 _handle_activate 调用已修改")

# _handle_status
old = "            return self._handle_status(), True"
new = "            return self._handle_status(message_id), True"
if old in content:
    content = content.replace(old, new, 1)
    print("[5] route: _handle_status 已传 message_id")
else:
    print("[跳过] route 中 _handle_status 调用已修改")

# _handle_list
old = "            return self._handle_list(), True"
new = "            return self._handle_list(message_id), True"
if old in content:
    content = content.replace(old, new, 1)
    print("[6] route: _handle_list 已传 message_id")
else:
    print("[跳过] route 中 _handle_list 调用已修改")

# ── 5. 在 _handle_activate 中发卡片 ───────────────────
# 在第一个 return 之前插入卡片发送代码
# 找到方法体中第一个 return
pattern = r'(    def _handle_activate\(self, text, message_id=None\):.*?)(\n        return f"已激活角色)'
# 用更安全的方式：直接字符串替换

_activate_old_return_1 = '                    return f"已激活角色：{info[\'name\']}（{info[\'domain\']}）\\n{info[\'description\']}", True'
_activate_new_return_1 = (
    '                    # 发送激活确认卡片\n'
    '                    if fc and message_id:\n'
    '                        try:\n'
    '                            fc.send_agent_activated(message_id, info["name"], info["domain"], info["description"])\n'
    '                            return None, True\n'
    '                        except Exception as e:\n'
    '                            log.warning(f"[Card] 激活卡片失败：{e}")\n'
    '                    return f"已激活角色：{info[\'name\']}（{info[\'domain\']}）\\n{info[\'description\']}", True'
)

# 因为字符串中有很多特殊字符，直接用字面量替换
# 用 repr 找精确字符串
idx = content.find('                    return f"已激活角色')
if idx > 0:
    # 找到这行的结束位置
    end_idx = content.find('\n', idx)
    old_line = content[idx:end_idx]
    print(f"[调试] 找到激活 return 行：{repr(old_line[:80])}")
else:
    print("[跳过] 未找到 _handle_activate 中的 return 行")

# ── 更直接的方式：用 sed 风格的行替换 ─────────────────
# 把整个文件按行分割，逐行处理
lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # 在 _handle_activate 中，把纯文本 return 改为先尝试发卡片
    if '    def _handle_activate(self, text, message_id=None):' in line:
        new_lines.append(line)
        i += 1
        # 跳过方法体，直到找到第一个 return
        depth = 1
        while i < len(lines):
            line2 = lines[i]
            new_lines.append(line2)
            
            # 如果是 return f"已激活角色： 并且下一行是 , True
            if 'return f"已激活角色' in line2:
                # 把这个 return 替换为一个卡片发送块
                indent = '                    '  # 18 spaces
                new_lines.pop()  # 移除刚才加的 return 行
                new_lines.append(indent + '# 发送激活确认卡片')
                new_lines.append(indent + 'if fc and message_id:')
                new_lines.append(indent + '    try:')
                new_lines.append(indent + '        fc.send_agent_activated(message_id, info["name"], info["domain"], info["description"])')
                new_lines.append(indent + '        return None, True')
                new_lines.append(indent + '    except Exception as e:')
                new_lines.append(indent + '        log.warning(f"[Card] 激活卡片失败：{e}")')
                new_lines.append(indent + '# 降级为纯文本')
                new_lines.append(indent + 'return f"已激活角色：{info[\'name\']}（{info[\'domain\']}）\\n{info[\'description\']}", True')
                i += 1  # 跳过原来的 return 行
                break
            i += 1
        continue
    
    new_lines.append(line)
    i += 1

new_content = '\n'.join(new_lines)

# 写回文件
with open(TARGET, "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"\n[完成] 文件已更新：{TARGET}")
print(f"[完成] 建议运行：python -m py_compile {TARGET}")
