#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 管理面板启动测试脚本
启动 GUI 并自动关闭，验证其能否正常渲染
"""
import sys
import os
import threading
import time

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

print("=" * 60)
print("  GUI 管理面板启动测试")
print("=" * 60)

# Step1: 导入 GUI 模块
print("\n[1/4] 导入 GUI 模块...")
try:
    import gui_manager as gm
    print("  ✅ gui_manager 模块导入成功")
except Exception as e:
    print(f"  ❌ 导入失败：{e}")
    sys.exit(1)

# Step2: 创建主窗口
print("\n[2/4] 创建主窗口...")
try:
    root = gm.tk.Tk()
    app = gm.ManagementPanel(root)
    print("  ✅ 主窗口创建成功")
except Exception as e:
    print(f"  ❌ 窗口创建失败：{e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step3: 检查窗口属性
print("\n[3/4] 检查窗口属性...")
try:
    title = root.title()
    geometry = root.geometry()
    print(f"  窗口标题：{title}")
    print(f"  窗口大小：{geometry}")
    print("  ✅ 窗口属性正常")
except Exception as e:
    print(f"  ❌ 窗口属性检查失败：{e}")
    sys.exit(1)

# Step4: 自动关闭
print("\n[4/4] 3秒后自动关闭...")
root.after(3000, root.destroy)
root.mainloop()

print("\n" + "=" * 60)
print("  ✅ GUI 管理面板测试通过！")
print("=" * 60)
