#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话管理器 — 飞书 chat_id ↔ Claude 持久进程映射
=================================================
职责：
  • get_or_create() —— 为每个飞书会话分配/复用 ClaudeSession
  • drain_all() —— 轮询循环中调用，收集所有会话的待发送输出
  • 空闲超时回收 —— 10 分钟内无交互自动 kill 进程
  • 优雅关闭 —— 程序退出时清理所有子进程

依赖：call_claude.ClaudeSession

使用方式（最小接入）:
    mgr = SessionManager(timeout_seconds=600)
    session = mgr.get_or_create(chat_id)
    session.write(instruction)
    for (sid, kind, data) in mgr.drain_all():
        if kind == 'data':
            send_to_feishu(chat_id, data)
        elif kind == 'approval':
            trigger_approval(chat_id, data)
"""

import time
import threading
import logging

import call_claude

log = logging.getLogger("session.manager")


class SessionManager:
    """飞书会话 → Claude 进程 的映射管理器（线程安全）"""

    def __init__(self, timeout_seconds: int = 600):
        """
        :param timeout_seconds: 空闲超时秒数（默认 10 分钟），超时自动回收进程
        """
        self._sessions: dict[str, call_claude.ClaudeSession] = {}
        self._last_active: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timeout = timeout_seconds
        self._reaper_running = False
        self._start_reaper()

    # ── 核心 API ────────────────────────────────────

    def get_or_create(self, chat_id: str) -> call_claude.ClaudeSession:
        """获取或创建飞书会话对应的 Claude 进程

        如果会话不存在或进程已死亡，创建新实例（但不自动 spawn）。
        调用此方法会刷新空闲计时。
        """
        with self._lock:
            session = self._sessions.get(chat_id)
            if session is None or not session.is_running:
                session = call_claude.ClaudeSession(chat_id)
                self._sessions[chat_id] = session
            self._last_active[chat_id] = time.time()
            return session

    def spawn(self, chat_id: str, instruction: str, model: str = None) -> bool:
        """为指定会话启动 Claude 执行（如果已有进程在跑则先 kill）"""
        session = self.get_or_create(chat_id)
        if session.is_running:
            session.kill()
        return session.spawn(instruction, model)

    def drain_all(self) -> list:
        """一次调用收集所有活跃会话的待发送输出（供轮询循环使用）

        返回: [(chat_id, kind, data), ...]
          kind: 'data' | 'approval' | 'exit'
        """
        results = []
        with self._lock:
            dead = []
            for chat_id, session in self._sessions.items():
                if not session.is_running:
                    dead.append(chat_id)
                    continue
                for kind, data in session.drain_output():
                    results.append((chat_id, kind, data))
                    if kind == 'exit':
                        dead.append(chat_id)
            for chat_id in dead:
                self._sessions.pop(chat_id, None)
                self._last_active.pop(chat_id, None)
        return results

    def write(self, chat_id: str, text: str, model: str = None) -> bool:
        """向指定会话启动 Claude 执行（等价于 spawn）"""
        return self.spawn(chat_id, text, model)

    def touch(self, chat_id: str):
        """手动刷新会话活动时间（防止被回收）"""
        with self._lock:
            self._last_active[chat_id] = time.time()

    def kill_session(self, chat_id: str):
        """主动终止指定会话"""
        with self._lock:
            session = self._sessions.pop(chat_id, None)
            if session:
                session.kill()
            self._last_active.pop(chat_id, None)

    def shutdown(self):
        """终止所有会话（程序退出前调用）"""
        self._reaper_running = False
        with self._lock:
            for chat_id, session in list(self._sessions.items()):
                session.kill()
            self._sessions.clear()
            self._last_active.clear()
        log.info("[SessionManager] 全部会话已关闭")

    @property
    def active_count(self) -> int:
        with self._lock:
            return len([s for s in self._sessions.values() if s.is_running])

    # ── 内部 ─────────────────────────────────────────

    def _start_reaper(self):
        """后台线程：定期回收空闲超时的会话进程"""
        self._reaper_running = True

        def reap():
            while self._reaper_running:
                time.sleep(30)  # 每 30 秒检查一次
                now = time.time()
                with self._lock:
                    dead = [
                        chat_id
                        for chat_id, t in self._last_active.items()
                        if now - t > self._timeout
                    ]
                    for chat_id in dead:
                        session = self._sessions.pop(chat_id, None)
                        if session:
                            session.kill()
                        self._last_active.pop(chat_id, None)
                        log.info("[SessionManager] 空闲回收：%s (%.0f分钟无活动)",
                                 chat_id[:12], (now - t) / 60)

        t = threading.Thread(target=reap, daemon=True, name="session-reaper")
        t.start()
