# Gemini Multi-Agent Swarm (HITL + LangGraph)

[![Powered by Gemini](https://img.shields.io/badge/Powered%20by-Gemini%202.5-blue?style=flat-square)](https://deepmind.google/technologies/gemini/)
[![LangGraph](https://img.shields.io/badge/Framework-LangGraph-orange?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-green?style=flat-square)](https://fastapi.tiangolo.com/)

> 本项目定位于**人机协同（Human-in-the-Loop）**智能体系统，集成了 Docker 沙箱代码执行、联网搜索、语义缓存以及基于状态机的自我修正机制。

## 📖 项目简介

这是一个基于 **Google Gemini** 和 **LangGraph** 构建的高级多智能体协同系统。与传统的线性 Chain 不同，本系统采用 **Orchestrator-Workers（指挥官-工种）** 拓扑结构。


核心大脑 `OrchestratorAgent` 负责动态规划任务，并将任务分发给专业的 **Crews（小队）**（如编程小队、数据小队、研究小队）。系统内置了**推测性执行**机制，能预判用户需求并提前预热 Docker 容器或预加载搜索结果，从而极大地降低延迟。

## ✨ 核心特性

### 1. 🧠 动态指挥与路由 (Orchestrator Pattern)
- **ReAct + Router**: `OrchestratorAgent` 根据当前上下文动态决定是调用工具、分发任务给子小队，还是直接结束任务。
- **智能分级 (Smart Routing)**: 内置 `GeminiKeyRotator`，根据任务复杂度（Simple vs Complex）自动在 **Gemini Flash** 和 **Gemini Pro** 之间切换，平衡响应速度与推理能力。

### 2. ⚡️ 推测性执行 (Speculative Execution)
- **沙箱预热**: 当 Orchestrator 预测到后续可能需要编程任务时，会在后台异步预热 Docker 容器（`sandbox.warm_up()`）。
- **预取搜索**: 在规划阶段若发现潜在知识缺口，系统会并行触发 `speculative_search_queries`，在 Agent 真正执行前将搜索结果存入状态机缓存。

### 3. 🤝 人机协同 (HITL & Interrupts)
- **关键节点阻断**: 在执行高风险或长耗时操作（如 `coding_crew`）前，LangGraph 状态机通过 `interrupt_before` 机制自动挂起。
- **实时干预**: 用户可以通过 CLI 或 Web 界面审查计划，选择 `[A]pprove`（批准）、`[F]eedback`（修改指令）或补充新图片，系统将携带反馈恢复（Resume）执行。

### 4. 🛠 专业化分工 (Crew Architecture)
- **Coding Crew**: 独立的状态机子图，负责代码生成、在隔离的 Docker 环境中运行并根据错误反馈进行自我修正。
- **Researcher Agent**: 集成 Google Search 和 Vector Memory (Pinecone) 的专业搜索员，负责获取实时信息与长期记忆检索。
- **Data/Content Crews**: 专用于复杂数据分析与高质量内容创作的闭环工作流。

### 5. 🌐 全栈架构支持
- **CLI 模式**: 交互式终端（`main.py`），支持多模态输入（文本+图片路径）及实时状态干预。
- **Web API**: 基于 FastAPI + SSE (Server-Sent Events) 实现的异步后端，支持全链路 Trace ID 追踪与系统状态自检。

---

## 📂 项目结构

```text
HITL-System/
├── agents/
│   ├── orchestrator/      # 大脑：负责决策分发和推测性预热逻辑
│   ├── crews/             # 专业小队 (Sub-graphs)
│   │   ├── coding_crew/   # 编程小队：含代码生成、评审与反思
│   │   ├── data_crew/     # 数据分析小队
│   │   └── content_crew/  # 内容创作小队
│   └── agents.py          # 基础 Agent 角色定义
├── core/
│   ├── rotator.py         # 模型轮询、负载均衡与智能路由
│   ├── models.py          # 统一的 Pydantic 状态与数据模型
│   ├── logger_setup.py    # 分布式日志与 Trace 上下文管理
│   └── api_models.py      # API 请求与响应模型
├── workflow/
│   ├── graph.py           # LangGraph 主工作流图构建
│   └── engine.py          # 工作流异步执行引擎
├── tools/
│   ├── sandbox.py         # Docker 代码沙箱执行接口
│   ├── search.py          # 联网搜索工具集成
│   ├── memory.py          # Pinecone 向量数据库存储
│   └── registry.py        # 工具统一注册与描述表
├── api_server.py          # FastAPI 服务端，支持流式 SSE
├── main.py                # CLI 交互入口
└── requirements.txt       # 核心依赖清单
```

---

## 🚀 快速开始

### 1. 环境准备
确保已安装 Python 3.10+，并启动 Docker 服务。

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
在 `.env` 文件中配置您的 API 密钥：

```ini
GEMINI_API_KEYS=["your_key_1", "your_key_2"]
PINECONE_API_KEY=your_key
VECTOR_INDEX_NAME=gemini-memory
# ... 其他配置
```

### 3. 运行项目

**命令行模式：**
```bash
python main.py
```

**Web API 模式：**
```bash
python api_server.py
```

---

## 🧠 技术栈细节

| 组件 | 技术选型 | 用途 |
| :--- | :--- | :--- |
| **LLM** | Gemini 2.5 Pro / Flash | 核心推理引擎 |
| **Orchestration** | LangGraph | 状态机管理与 HITL 中断 |
| **Backend** | FastAPI + SSE | 异步流式输出接口 |
| **Sandbox** | Docker | 安全的代码执行环境 |
| **Memory** | Pinecone | 语义检索与长期记忆 |

---
