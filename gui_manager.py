#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书 → Claude Code 管理面板 v1.1
基于 Tkinter 的本地可视化管理系统

v1.1 修复：
  - 延迟导入 run_feishu_poll，避免启动崩溃
  - 直接从 config.json 读取配置
  - 子进程管理轮询/Webhook 服务启停
  - 实时日志从文件读取（不依赖内存状态）
  - 配置保存即时生效
"""

import os
import sys
import json
import time
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")
LOG_FILE    = os.path.join(PROJECT_DIR, "feishu_poll.log")
WEBHOOK_LOG = os.path.join(PROJECT_DIR, "webhook.log")
PYTHON_EXE  = sys.executable
POLL_SCRIPT = os.path.join(PROJECT_DIR, "run_feishu_poll.py")

# ── 延迟导入 ─────────────────────────────────────────
_rfp = None

def _get_rfp():
    global _rfp
    if _rfp is not None:
        return _rfp
    try:
        import run_feishu_poll as mod
        _rfp = mod
        return _rfp
    except Exception as e:
        messagebox.showerror("导入错误", f"无法导入核心模块：{e}")
        raise

# ── 配置管理 ─────────────────────────────────────────
class ConfigManager:
    def __init__(self):
        self.config = {}
        self.load()

    def load(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception:
            self.config = {}

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return False

    def get(self, section, key, default=None):
        return self.config.get(section, {}).get(key, default)

    def set(self, section, key, value):
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value

# ── 日志查看器 ───────────────────────────────────────
class LogViewer:
    def __init__(self, text_widget, log_path=None):
        self.text_widget = text_widget
        self.log_path = log_path or LOG_FILE
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._watch, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _watch(self):
        last_size = 0
        while self.running:
            try:
                if os.path.exists(self.log_path):
                    sz = os.path.getsize(self.log_path)
                    if sz > last_size:
                        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(last_size)
                            new = f.read()
                            if new:
                                self.text_widget.insert(tk.END, new)
                                self.text_widget.see(tk.END)
                        last_size = sz
            except Exception:
                pass
            time.sleep(1)

    def refresh(self):
        try:
            if os.path.exists(self.log_path):
                with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                    self.text_widget.delete(1.0, tk.END)
                    self.text_widget.insert(tk.END, f.read())
                    self.text_widget.see(tk.END)
        except Exception as e:
            messagebox.showerror("刷新失败", str(e))

# ── 服务管理器 ───────────────────────────────────────
class ServiceManager:
    def __init__(self):
        self.poll_process = None
        self.webhook_process = None

    def start_poll(self):
        if self.poll_process and self.poll_process.poll() is None:
            return True, "轮询服务已在运行"
        try:
            self.poll_process = subprocess.Popen(
                [PYTHON_EXE, "-u", POLL_SCRIPT],
                cwd=PROJECT_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, f"轮询服务已启动 (PID: {self.poll_process.pid})"
        except Exception as e:
            return False, f"启动失败：{e}"

    def stop_poll(self):
        if self.poll_process and self.poll_process.poll() is None:
            self.poll_process.terminate()
            try:
                self.poll_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.poll_process.kill()
            return True, "轮询服务已停止"
        return True, "轮询服务未在运行"

    def start_webhook(self):
        script = os.path.join(PROJECT_DIR, "feishu_webhook.py")
        if not os.path.exists(script):
            return False, "feishu_webhook.py 不存在"
        if self.webhook_process and self.webhook_process.poll() is None:
            return True, "Webhook 服务已在运行"
        try:
            self.webhook_process = subprocess.Popen(
                [PYTHON_EXE, "-u", script],
                cwd=PROJECT_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, f"Webhook 已启动 (PID: {self.webhook_process.pid})"
        except Exception as e:
            return False, f"启动失败：{e}"

    def stop_webhook(self):
        if self.webhook_process and self.webhook_process.poll() is None:
            self.webhook_process.terminate()
            return True, "Webhook 已停止"
        return True, "Webhook 未在运行"

    def get_status(self):
        poll_running = self.poll_process is not None and self.poll_process.poll() is None
        webhook_running = self.webhook_process is not None and self.webhook_process.poll() is None
        return {
            "轮询服务": "运行中" if poll_running else "已停止",
            "Webhook服务": "运行中" if webhook_running else "已停止",
        }

# ── 管理面板主类 ─────────────────────────────────────
class ManagementPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("飞书 → Claude Code 管理面板 v1.1")
        self.root.geometry("920x640")
        self.root.minsize(800, 500)

        self.cfg = ConfigManager()
        self.svc = ServiceManager()
        self.log_viewer = None

        self._build_ui()
        self._load_config_to_ui()

    # ── UI 构建 ──────────────────────────────────
    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._tab_feishu()
        self._tab_webhook()
        self._tab_model()
        self._tab_log()
        self._tab_status()
        self._bottom_bar()

    def _tab_feishu(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="飞书配置")
        rows = [
            ("App ID:", "feishu_app_id"),
            ("App Secret:", "feishu_app_secret", "*"),
            ("Chat ID:", "feishu_chat_id"),
            ("Base URL:", "feishu_base_url"),
        ]
        for i, r in enumerate(rows):
            ttk.Label(f, text=r[0]).grid(row=i, column=0, sticky=tk.W, padx=10, pady=6)
            show = r[2] if len(r) > 2 else ""
            setattr(self, r[1], ttk.Entry(f, width=50, show=show))
            getattr(self, r[1]).grid(row=i, column=1, padx=10, pady=6)
        ttk.Button(f, text="保存配置", command=self._save_feishu).grid(row=4, column=0, columnspan=2, pady=15)

    def _tab_webhook(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="Webhook")
        self.webhook_enabled = tk.BooleanVar()
        ttk.Checkbutton(f, text="启用 Webhook 模式", variable=self.webhook_enabled).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=6)

        entries = [
            ("监听地址:", "webhook_host", 20),
            ("监听端口:", "webhook_port", 10),
            ("Verify Token:", "webhook_verify_token", 50),
            ("Encrypt Key:", "webhook_encrypt_key", 50),
        ]
        for i, (label, attr, w) in enumerate(entries, 1):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky=tk.W, padx=10, pady=6)
            show = "*" if "key" in attr.lower() or "secret" in attr.lower() else ""
            setattr(self, attr, ttk.Entry(f, width=w, show=show))
            getattr(self, attr).grid(row=i, column=1, sticky=tk.W, padx=10, pady=6)
        ttk.Button(f, text="保存配置", command=self._save_webhook).grid(row=5, column=0, columnspan=2, pady=15)

    def _tab_model(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="模型配置")
        ttk.Label(f, text="Claude CLI 路径:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=6)
        self.model_cli = ttk.Entry(f, width=40)
        self.model_cli.grid(row=0, column=1, padx=10, pady=6)
        ttk.Button(f, text="浏览", command=self._browse_cli).grid(row=0, column=2, padx=5)

        ttk.Label(f, text="默认模型:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=6)
        self.model_default = ttk.Combobox(f, width=18, values=["haiku", "sonnet", "opus"])
        self.model_default.grid(row=1, column=1, sticky=tk.W, padx=10, pady=6)

        ttk.Label(f, text="复杂任务模型:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=6)
        self.model_complex = ttk.Combobox(f, width=18, values=["haiku", "sonnet", "opus"])
        self.model_complex.grid(row=2, column=1, sticky=tk.W, padx=10, pady=6)

        ttk.Label(f, text="超时(秒):").grid(row=3, column=0, sticky=tk.W, padx=10, pady=6)
        self.model_timeout = ttk.Entry(f, width=8)
        self.model_timeout.grid(row=3, column=1, sticky=tk.W, padx=10, pady=6)

        ttk.Button(f, text="保存配置", command=self._save_model).grid(row=4, column=0, columnspan=2, pady=15)

    def _tab_log(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="日志查看")
        self.log_text = scrolledtext.ScrolledText(f, width=100, height=30, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(bf, text="开始监控", command=self._log_start).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="停止监控", command=self._log_stop).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="清空显示", command=lambda: self.log_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="刷新", command=self._log_refresh).pack(side=tk.LEFT, padx=3)

        self.log_viewer = LogViewer(self.log_text)

    def _tab_status(self):
        f = ttk.Frame(self.notebook)
        self.notebook.add(f, text="状态监控")
        self.status_vars = {}
        labels = ["轮询服务", "Webhook服务", "当前Agent", "可用角色数", "RAG状态", "最近消息"]
        for i, lbl in enumerate(labels):
            ttk.Label(f, text=f"{lbl}:").grid(row=i, column=0, sticky=tk.W, padx=10, pady=6)
            var = tk.StringVar(value="—")
            self.status_vars[lbl] = var
            ttk.Label(f, textvariable=var, foreground="blue").grid(row=i, column=1, sticky=tk.W, padx=10, pady=6)

        ttk.Button(f, text="刷新状态", command=self._refresh_status).grid(row=len(labels), column=0, columnspan=2, pady=15)
        self._refresh_status()

    def _bottom_bar(self):
        f = ttk.Frame(self.root)
        f.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(f, text="启动轮询", command=self._start_poll).pack(side=tk.LEFT, padx=4)
        ttk.Button(f, text="停止轮询", command=self._stop_poll).pack(side=tk.LEFT, padx=4)
        ttk.Button(f, text="启动Webhook", command=self._start_webhook).pack(side=tk.LEFT, padx=4)
        ttk.Button(f, text="停止Webhook", command=self._stop_webhook).pack(side=tk.LEFT, padx=4)
        ttk.Button(f, text="保存全部配置", command=self._save_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(f, text="退出", command=self.root.quit).pack(side=tk.RIGHT, padx=4)

    # ── 配置加载/保存 ────────────────────────────
    def _load_config_to_ui(self):
        c = self.cfg
        self.feishu_app_id.insert(0, c.get("feishu", "app_id", ""))
        self.feishu_app_secret.insert(0, c.get("feishu", "app_secret", ""))
        self.feishu_chat_id.insert(0, c.get("feishu", "chat_id", ""))
        self.feishu_base_url.insert(0, c.get("feishu", "base_url", ""))

        self.webhook_enabled.set(c.get("webhook", "enabled", False))
        self.webhook_host.insert(0, c.get("webhook", "host", "0.0.0.0"))
        self.webhook_port.insert(0, str(c.get("webhook", "port", 8080)))
        self.webhook_verify_token.insert(0, c.get("webhook", "verify_token", ""))
        self.webhook_encrypt_key.insert(0, c.get("webhook", "encrypt_key", ""))

        cli_candidates = c.get("claude", "cli_candidates", ["claude"])
        self.model_cli.insert(0, cli_candidates[0] if isinstance(cli_candidates, list) else "claude")
        self.model_default.set(c.get("claude", "default_model", "haiku"))
        self.model_complex.set(c.get("claude", "complex_model", "opus"))
        self.model_timeout.insert(0, str(c.get("claude", "timeout", 300)))

    def _save_feishu(self):
        c = self.cfg
        c.set("feishu", "app_id", self.feishu_app_id.get())
        c.set("feishu", "app_secret", self.feishu_app_secret.get())
        c.set("feishu", "chat_id", self.feishu_chat_id.get())
        c.set("feishu", "base_url", self.feishu_base_url.get())
        c.save() and messagebox.showinfo("完成", "飞书配置已保存")

    def _save_webhook(self):
        c = self.cfg
        c.set("webhook", "enabled", self.webhook_enabled.get())
        c.set("webhook", "host", self.webhook_host.get())
        c.set("webhook", "port", int(self.webhook_port.get() or "8080"))
        c.set("webhook", "verify_token", self.webhook_verify_token.get())
        c.set("webhook", "encrypt_key", self.webhook_encrypt_key.get())
        c.save() and messagebox.showinfo("完成", "Webhook 配置已保存")

    def _save_model(self):
        c = self.cfg
        cli = self.model_cli.get()
        c.set("claude", "cli_candidates", [cli, "claude"])
        c.set("claude", "default_model", self.model_default.get())
        c.set("claude", "complex_model", self.model_complex.get())
        c.set("claude", "timeout", int(self.model_timeout.get() or "300"))
        c.save() and messagebox.showinfo("完成", "模型配置已保存")

    def _save_all(self):
        self._save_feishu()
        self._save_webhook()
        self._save_model()

    # ── 日志 ────────────────────────────────────
    def _log_start(self):
        self.log_viewer.start()
    def _log_stop(self):
        self.log_viewer.stop()
    def _log_refresh(self):
        self.log_viewer.refresh()

    # ── 状态 ────────────────────────────────────
    def _refresh_status(self):
        svc_status = self.svc.get_status()
        for lbl, var in self.status_vars.items():
            if lbl in svc_status:
                var.set(svc_status[lbl])
        try:
            rfp = _get_rfp()
            am = rfp.AgentManager()
            self.status_vars.get("可用角色数", tk.StringVar()).set(str(len(am.agents)))
            self.status_vars.get("RAG状态", tk.StringVar()).set("启用" if rfp.RAG_AVAILABLE else "未安装")
            active = am.active_agent
            name = am.agents[active]["name"] if active and active in am.agents else "无"
            self.status_vars.get("当前Agent", tk.StringVar()).set(name)
        except Exception:
            pass

    # ── 服务启停 ────────────────────────────────
    def _start_poll(self):
        ok, msg = self.svc.start_poll()
        messagebox.showinfo("轮询服务", msg)
        self._refresh_status()

    def _stop_poll(self):
        ok, msg = self.svc.stop_poll()
        messagebox.showinfo("轮询服务", msg)
        self._refresh_status()

    def _start_webhook(self):
        ok, msg = self.svc.start_webhook()
        messagebox.showinfo("Webhook 服务", msg)
        self._refresh_status()

    def _stop_webhook(self):
        ok, msg = self.svc.stop_webhook()
        messagebox.showinfo("Webhook 服务", msg)
        self._refresh_status()

    # ── 辅助 ────────────────────────────────────
    def _browse_cli(self):
        fn = filedialog.askopenfilename(title="选择 Claude CLI", filetypes=[("可执行文件", "*.exe *.cmd"), ("所有文件", "*.*")])
        if fn:
            self.model_cli.delete(0, tk.END)
            self.model_cli.insert(0, fn)

# ── 主函数 ───────────────────────────────────────────
def main():
    try:
        root = tk.Tk()
        app = ManagementPanel(root)
        root.mainloop()
    except Exception as e:
        # 尝试用 messagebox 显示，如果 Tk 都起不来就打印
        try:
            messagebox.showerror("启动失败", f"GUI 面板启动失败：\n{e}")
        except Exception:
            print(f"GUI 启动失败：{e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
