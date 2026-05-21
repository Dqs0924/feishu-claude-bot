#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块3（新）：RAG 检索增强模块
功能：将口语指令转换为标准指令（/run ...）

两种模式：
  1. 规则模式（默认）：用 difflib 相似度匹配，无重依赖，适合轻量验证
  2. 向量模式（可选）：用 Chroma + 嵌入模型，需安装 chromadb / sentence-transformers

知识库存放：instruction_kb.json（自动创建）
"""

import os
import json
import difflib
from typing import Optional

KB_FILE = os.path.join(os.path.dirname(__file__), "instruction_kb.json")


def _load_kb():
    """加载知识库（JSON 文件）"""
    if not os.path.exists(KB_FILE):
        # 返回默认空结构
        return {"instructions": [], "version": 1}
    with open(KB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_kb(kb):
    """保存知识库到 JSON 文件"""
    with open(KB_FILE, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)


class RAGEngine:
    """
    RAG 引擎，自动选择模式：
      - 向量模式（优先）：Chroma + all-MiniLM-L6-v2，语义匹配
      - 规则模式（兜底）：difflib 字符串相似度，零依赖
    """

    def __init__(self, use_vector: bool = True):
        self.kb = _load_kb()
        count = len(self.kb.get("instructions", []))
        print(f"[RAG] 知识库已加载，共 {count} 条指令")
        if count == 0:
            self._load_defaults()
            count = len(self.kb.get("instructions", []))

        self.vector_ready = False
        if use_vector:
            try:
                self.init_vector_mode()
            except Exception as e:
                print(f"[RAG] 向量模式初始化失败，回退到规则模式：{e}")

    def _load_defaults(self):
        """加载默认指令库"""
        defaults = [
            ("输出hello world",     "输出 Hello World，用中文解释",                    "基础输出"),
            ("输出你好世界",          "输出 你好，世界！",                              "基础输出"),
            ("写个排序",             "用 Python 写一个快速排序函数，包含详细注释和测试",  "排序算法"),
            ("用Python写快速排序",    "用 Python 写一个快速排序函数，包含详细注释和测试",  "排序算法"),
            ("帮我看看代码有啥错",   "检查当前项目代码，列出所有语法错误和逻辑警告",      "代码审查"),
            ("检查代码",             "检查当前项目代码，列出所有语法错误和逻辑警告",      "代码审查"),
            ("写一个斐波那契",        "用 Python 写一个斐波那契数列函数",                "基础算法"),
            ("帮我生成一个网页",       "用 HTML/CSS/JS 生成一个完整的个人主页",           "Web开发"),
            ("翻译这段文字",          "将以下文字翻译成英文",                           "翻译"),
            ("解释一下",             "用简洁的中文解释以下概念",                        "知识问答"),
            ("执行命令",             "运行以下命令并返回结果",                          "系统命令"),
            ("创建一个文件",          "创建文件并写入指定内容",                          "文件操作"),
        ]
        for oral, standard, desc in defaults:
            self.add_instruction(oral, standard, desc)
        print(f"[RAG] 默认指令库已加载（{len(defaults)} 条）")

    # ── 对外部调用 ───────────────────────────────────────────────
    def add_instruction(self, oral_cmd: str, standard_cmd: str, desc: str = ""):
        """添加一条指令到知识库"""
        self.kb.setdefault("instructions", []).append({
            "oral": oral_cmd,
            "standard": standard_cmd,
            "desc": desc,
        })
        _save_kb(self.kb)
        print(f"[RAG] 已添加：{oral_cmd}  →  {standard_cmd}")

    def parse(self, user_input: str, threshold: float = 0.5) -> str:
        """
        解析用户口语指令，返回标准指令
        优先使用向量模式，不可用时回退到规则模式
        """
        result, _ = self.parse_with_distance(user_input, threshold)
        return result

    def parse_with_distance(self, user_input: str, threshold: float = 0.5):
        """
        解析并返回 (标准指令, 向量距离)
        距离=None 表示规则模式或无匹配
        """
        if self.vector_ready:
            return self._parse_vector_with_distance(user_input)
        return self._parse_rule(user_input, threshold), None

    def _parse_rule(self, user_input: str, threshold: float = 0.5) -> str:
        """规则模式：difflib 字符串相似度匹配"""
        instructions = self.kb.get("instructions", [])
        if not instructions:
            return user_input

        oral_cmds = [item["oral"] for item in instructions]
        matches = difflib.get_close_matches(
            user_input, oral_cmds, n=1, cutoff=threshold
        )

        if matches:
            matched_oral = matches[0]
            for item in instructions:
                if item["oral"] == matched_oral:
                    print(f"[RAG 规则] {user_input} → {item['standard']}")
                    return item["standard"]

        print(f"[RAG 规则] 未匹配 → 原始输入")
        return user_input

    def _parse_vector(self, user_input: str, top_k: int = 1, max_distance: float = 0.30) -> str:
        """向量模式：Chroma + embedding 语义检索（高精度阈值，防误匹配）"""
        result, _ = self._parse_vector_with_distance(user_input, top_k, max_distance)
        return result

    def _parse_vector_with_distance(self, user_input: str, top_k: int = 1, max_distance: float = 0.30):
        """向量模式 + 返回距离信息"""
        try:
            query_emb = self.embed_model.encode([user_input]).tolist()
            results = self.collection.query(
                query_embeddings=query_emb,
                n_results=top_k,
            )
            if results and results.get("metadatas") and results["metadatas"][0]:
                matched = results["metadatas"][0][0]
                distance = results.get("distances", [[0]])[0][0]
                if distance <= max_distance:
                    print(f"[RAG 向量] {user_input} → {matched['standard']} (距离={distance:.3f})")
                    return matched["standard"], distance
                else:
                    print(f"[RAG 向量] 距离过大({distance:.3f}>{max_distance})，使用原始输入")
        except Exception as e:
            print(f"[RAG 向量] 检索异常，回退规则模式：{e}")

        print(f"[RAG 向量] 未匹配 → 原始输入")
        return user_input, None

    # ── 向量模式（可选，需安装依赖）────────────────────────────
    def parse_vector(self, user_input: str, top_k: int = 1) -> str:
        """
        向量模式解析（需先调用 init_vector_mode() 初始化）
        使用 Chroma + all-MiniLM-L6-v2 做语义检索
        """
        if not hasattr(self, "vector_ready") or not self.vector_ready:
            raise RuntimeError(
                "向量模式未初始化。请先执行：\n"
                "  pip install chromadb sentence-transformers\n"
                "  rag.init_vector_mode()"
            )

        # 生成查询向量
        query_emb = self.embed_model.encode([user_input])[0].tolist()

        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
        )

        if results and results.get("metadatas"):
            matched = results["metadatas"][0][0]
            print(f"[RAG 向量] 匹配到：{matched['oral']} → {matched['standard']}")
            return matched["standard"]

        print(f"[RAG 向量] 未匹配到，使用原始输入：「{user_input}」")
        return user_input

    def init_vector_mode(self):
        """
        初始化向量模式（需安装 chromadb + sentence-transformers）
        自动使用 HF 镜像解决国内下载问题
        """
        # 国内 HF 镜像加速
        if "HF_ENDPOINT" not in os.environ:
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "向量模式依赖未安装。请执行：\n"
                "  pip install chromadb sentence-transformers"
            )

        print("[RAG] 正在初始化向量模式...")
        # 初始化 Chroma 客户端（本地持久化）
        db_path = os.path.join(os.path.dirname(__file__), "rag_db")
        client = chromadb.PersistentClient(path=db_path)
        self.collection = client.get_or_create_collection(
            name="instruction_kb_vec",
            metadata={"hnsw:space": "cosine"},
        )

        # 加载嵌入模型（本地）
        self.embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[RAG] 嵌入模型加载完成（all-MiniLM-L6-v2）")

        # 将知识库中的指令同步到向量库
        self._sync_to_vector_db()
        self.vector_ready = True
        print("[RAG] 向量模式初始化完成")

    def _sync_to_vector_db(self):
        """将 JSON 知识库同步到 Chroma 向量库"""
        instructions = self.kb.get("instructions", [])
        if not instructions:
            return

        # 避免重复插入：清空后重新插入
        try:
            self.collection.delete(ids=[item["oral"] for item in instructions if item.get("oral")])
        except Exception:
            pass

        documents = []
        metadatas = []
        ids = []
        for item in instructions:
            ids.append(item["oral"])
            documents.append(item["oral"])
            metadatas.append({
                "oral": item["oral"],
                "standard": item["standard"],
                "desc": item.get("desc", ""),
            })

        embeddings = self.embed_model.encode(documents).tolist()
        self.collection.add(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        print(f"[RAG] 向量库已同步，共 {len(ids)} 条")


# ── 独立测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    rag = RAGEngine()

    # 测试规则模式
    test_cases = [
        "输出hello world",
        "我想用Python写个排序",
        "帮我看看代码有啥问题",
        "随便写个啥",
    ]

    print("\n── 规则模式测试 ──")
    for case in test_cases:
        result = rag.parse(case)
        print(f"  输入：{case}")
        print(f"  输出：{result}\n")

    # 测试向量模式（如已安装依赖）
    try:
        rag.init_vector_mode()
        print("\n── 向量模式测试 ──")
        for case in test_cases:
            result = rag.parse_vector(case)
            print(f"  输入：{case}")
            print(f"  输出：{result}\n")
    except RuntimeError as e:
        print(f"\n[提示] 向量模式未安装：{e}")
