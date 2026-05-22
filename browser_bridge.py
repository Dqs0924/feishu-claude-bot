#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Browser Bridge — 通过 CDP 协议控制已登录的 Edge 浏览器
========================================================
前置条件: Edge 已启动并开启调试端口 9222
         (双击 start-edge-debug.bat 或手动启动)

核心能力:
  list_tabs()                    → 列出所有标签页
  navigate(url, tab_index)      → 导航到 URL
  screenshot(selector)          → 截图当前页
  snapshot(max_depth)           → 获取页面 DOM 可访问性树
  click(selector)               → 点击元素
  fill(selector, text)          → 填入文本
  evaluate(js)                  → 执行 JavaScript
  switch_tab(index)             → 切换标签页
  get_current_url()             → 获取当前 URL
  parse_and_execute(instruction)→ 自然语言→CDP 操作（Claude 辅助）

实现方式:
  优先使用 Playwright connect_over_cdp（高级 API）
  降级使用 raw CDP WebSocket（零额外依赖）
"""

import json
import time
import base64
import logging
import urllib.request
from typing import Optional
from pathlib import Path

log = logging.getLogger("browser")

CDP_URL = "http://127.0.0.1:9222"
OUTBOX_DIR = Path(__file__).parent / "outbox" / "screenshots"

# ── 原始 CDP 客户端（无 Playwright 依赖）─────────────────

class _CdpClient:
    """轻量 CDP WebSocket 客户端"""

    def __init__(self, ws_url: str):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=10)
        self._id = 0

    def send(self, method: str, params: dict = None) -> dict:
        self._id += 1
        msg = json.dumps({"id": self._id, "method": method, "params": params or {}})
        self.ws.send(msg)
        resp = self.ws.recv()
        return json.loads(resp)

    def close(self):
        self.ws.close()


class _BrowserBackend:
    """统一后端：Playwright 优先，CDP 降级"""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._mode = None  # 'playwright' | 'cdp'

    def connect(self) -> bool:
        """连接到 Edge 浏览器"""
        # 尝试 Playwright
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(CDP_URL)
            self._mode = 'playwright'
            log.info("[Browser] Playwright 连接成功")
            return True
        except Exception as e:
            log.warning("[Browser] Playwright 不可用 (%s)，降级 raw CDP", e)
            self._mode = 'cdp'
            return self._check_cdp()

    def _check_cdp(self) -> bool:
        try:
            resp = urllib.request.urlopen(f"{CDP_URL}/json", timeout=5)
            pages = json.loads(resp.read())
            return len(pages) > 0
        except Exception:
            return False

    @property
    def mode(self) -> str:
        return self._mode

    # ── 统一 API ──────────────────────────────

    def list_tabs(self) -> list[dict]:
        """列出所有标签页"""
        if self._mode == 'playwright':
            pages = []
            for i, ctx in enumerate(self._browser.contexts):
                for page in ctx.pages:
                    pages.append({"index": len(pages), "title": page.title(), "url": page.url})
            return pages
        else:
            resp = urllib.request.urlopen(f"{CDP_URL}/json", timeout=5)
            all_pages = json.loads(resp.read())
            return [
                {"index": i, "title": p.get("title", ""), "url": p.get("url", ""),
                 "ws_url": p.get("webSocketDebuggerUrl", "")}
                for i, p in enumerate(all_pages) if p.get("type") == "page"
            ]

    def navigate(self, url: str, tab_index: int = 0) -> dict:
        """导航到指定 URL"""
        if self._mode == 'playwright':
            page = self._get_page(tab_index)
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            return {"ok": True, "url": page.url, "title": page.title()}
        else:
            ws_url = self._get_ws_url(tab_index)
            cdp = _CdpClient(ws_url)
            cdp.send("Page.enable")
            result = cdp.send("Page.navigate", {"url": url})
            time.sleep(1)
            cdp.close()
            return {"ok": True, "url": url}

    def screenshot(self, selector: str = None, tab_index: int = None) -> bytes:
        """截图当前页（或指定元素），返回 PNG bytes"""
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        if self._mode == 'playwright':
            page = self._get_page(tab_index)
            if selector:
                el = page.locator(selector).first
                return el.screenshot()
            return page.screenshot(full_page=False)
        else:
            ws_url = self._get_ws_url(tab_index)
            cdp = _CdpClient(ws_url)
            cdp.send("Page.enable")
            result = cdp.send("Page.captureScreenshot", {"format": "png"})
            cdp.close()
            return base64.b64decode(result.get("result", {}).get("data", ""))

    def snapshot(self, max_depth: int = 3, tab_index: int = None) -> str:
        """获取页面可访问性快照（结构化文本）"""
        if self._mode == 'playwright':
            page = self._get_page(tab_index)
            try:
                # Playwright accessibility snapshot
                snapshot = page.accessibility.snapshot()
                return self._format_a11y(snapshot, max_depth)
            except Exception:
                # 降级：获取 body 文本
                return page.evaluate("() => document.body?.innerText || ''")[:3000]
        else:
            ws_url = self._get_ws_url(tab_index)
            cdp = _CdpClient(ws_url)
            cdp.send("Accessibility.enable")
            result = cdp.send("Accessibility.getFullAXTree", {"max_depth": max_depth})
            cdp.close()
            return self._format_a11y(result.get("result", {}).get("nodes", []), max_depth)

    def click(self, selector: str, tab_index: int = None) -> dict:
        """点击元素（支持 text=, #id, .class, 文本内容）"""
        if self._mode == 'playwright':
            page = self._get_page(tab_index)
            page.locator(selector).first.click(timeout=5000)
            return {"ok": True, "selector": selector}
        else:
            ws_url = self._get_ws_url(tab_index)
            cdp = _CdpClient(ws_url)
            cdp.send("Runtime.enable")
            cdp.send("DOM.enable")
            # 用 JS 点击（最通用的方式）
            js = f"document.querySelector('{selector}')?.click() || [...document.querySelectorAll('*')].find(el => el.textContent?.trim() === '{selector}')?.click()"
            cdp.send("Runtime.evaluate", {"expression": js})
            cdp.close()
            return {"ok": True, "selector": selector}

    def fill(self, selector: str, text: str, tab_index: int = None) -> dict:
        """填入文本到输入框"""
        if self._mode == 'playwright':
            page = self._get_page(tab_index)
            page.locator(selector).first.fill(text, timeout=5000)
            return {"ok": True, "selector": selector, "text": text}
        else:
            ws_url = self._get_ws_url(tab_index)
            cdp = _CdpClient(ws_url)
            cdp.send("Runtime.enable")
            js = f"const el = document.querySelector('{selector}'); if(el) {{ el.value = '{text}'; el.dispatchEvent(new Event('input')); }}"
            cdp.send("Runtime.evaluate", {"expression": js})
            cdp.close()
            return {"ok": True, "selector": selector, "text": text}

    def evaluate(self, js: str, tab_index: int = None) -> str:
        """执行 JS 并返回结果"""
        if self._mode == 'playwright':
            page = self._get_page(tab_index)
            result = page.evaluate(js)
            return str(result)[:3000]
        else:
            ws_url = self._get_ws_url(tab_index)
            cdp = _CdpClient(ws_url)
            cdp.send("Runtime.enable")
            result = cdp.send("Runtime.evaluate", {"expression": js, "returnByValue": True})
            cdp.close()
            return str(result.get("result", {}).get("result", {}).get("value", ""))[:3000]

    def get_current_url(self, tab_index: int = None) -> str:
        if self._mode == 'playwright':
            return self._get_page(tab_index).url
        return ""

    # ── 内部 ─────────────────────────────────

    def _get_page(self, tab_index: int = None):
        """获取当前活跃的 page 对象"""
        for ctx in self._browser.contexts:
            pages = ctx.pages
            if pages:
                if tab_index is not None and tab_index < len(pages):
                    return pages[tab_index]
                return pages[-1]
        raise RuntimeError("没有可用的浏览器页面")

    def _get_ws_url(self, tab_index: int = None) -> str:
        resp = urllib.request.urlopen(f"{CDP_URL}/json", timeout=5)
        pages = [p for p in json.loads(resp.read()) if p.get("type") == "page"]
        if tab_index is not None and tab_index < len(pages):
            return pages[tab_index]["webSocketDebuggerUrl"]
        return pages[-1]["webSocketDebuggerUrl"] if pages else ""

    def _format_a11y(self, nodes, max_depth: int, depth: int = 0) -> str:
        if depth > max_depth:
            return ""
        if isinstance(nodes, dict):
            nodes = [nodes]
        lines = []
        for node in (nodes or []):
            role = node.get("role", "?")
            name = node.get("name", "")
            if name:
                lines.append(f"{'  ' * depth}[{role}] {name}")
            children = node.get("children", [])
            if children:
                lines.append(self._format_a11y(children, max_depth, depth + 1))
        return "\n".join(lines)

    def close(self):
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass


# ── 全局单例 ──────────────────────────────────────

_backend: Optional[_BrowserBackend] = None


def get_browser() -> _BrowserBackend:
    global _backend
    if _backend is None:
        _backend = _BrowserBackend()
        _backend.connect()
    return _backend


# ── 便捷函数（供 SmartRouter 调用）────────────────

def list_tabs() -> list[dict]:
    b = get_browser()
    return b.list_tabs()


def navigate_and_screenshot(url: str, instruction: str = "") -> str:
    """
    导航到 URL 并截图，返回截图文件路径
    这是最常用的"远程浏览"场景
    """
    b = get_browser()
    b.navigate(url)
    time.sleep(1.5)  # 等待页面加载

    png_bytes = b.screenshot()
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"browse_{ts}.png"
    filepath = OUTBOX_DIR / filename
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

    with open(filepath, "wb") as f:
        f.write(png_bytes)

    url_current = b.get_current_url()
    title = b.evaluate("document.title")[:100]
    return str(filepath), url_current, title


def execute_actions(actions: list[dict]) -> list[dict]:
    """
    执行一组浏览器操作

    actions = [
        {"action": "navigate", "url": "https://..."},
        {"action": "fill", "selector": "#kw", "text": "Python"},
        {"action": "click", "selector": "#su"},
        {"action": "screenshot"},
    ]
    返回每个操作的结果
    """
    b = get_browser()
    results = []
    for act in actions:
        action = act.get("action", "")
        try:
            if action == "navigate":
                results.append(b.navigate(act["url"]))
            elif action == "fill":
                results.append(b.fill(act["selector"], act.get("text", "")))
            elif action == "click":
                results.append(b.click(act["selector"]))
            elif action == "screenshot":
                png = b.screenshot(act.get("selector"))
                results.append({"ok": True, "screenshot_len": len(png)})
            elif action == "snapshot":
                text = b.snapshot(act.get("max_depth", 3))
                results.append({"ok": True, "snapshot": text[:2000]})
            elif action == "evaluate":
                text = b.evaluate(act.get("js", ""))
                results.append({"ok": True, "result": text})
            elif action == "wait":
                time.sleep(float(act.get("seconds", 1)))
                results.append({"ok": True})
            else:
                results.append({"ok": False, "error": f"未知操作: {action}"})
        except Exception as e:
            results.append({"ok": False, "error": str(e)[:200], "action": action})
    return results


def quick_screenshot(max_chars: int = 0) -> bytes:
    """快速截图当前页"""
    b = get_browser()
    return b.screenshot()


# ══════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys, io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=== Browser Bridge 自检 ===")
    b = get_browser()
    print(f"Mode: {b.mode}")
    print()

    print("--- 标签页 ---")
    for t in b.list_tabs():
        print(f"  [{t['index']}] {t['title'][:60]}")
        print(f"      {t['url'][:80]}")

    print()
    print("--- 当前页快照 ---")
    snap = b.snapshot(max_depth=2)
    print(snap[:500] if snap else "(empty)")

    print()
    print("--- 截图测试 ---")
    try:
        png = b.screenshot()
        filepath = OUTBOX_DIR / "test_screenshot.png"
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(png)
        print(f"Screenshot saved: {filepath} ({len(png)} bytes)")
    except Exception as e:
        print(f"FAIL: {e}")

    b.close()
    print("\n自检完成。")
