# 🤖 Gemini Multi-Agent Swarm (HITL)

这是一个基于 **Google Gemini API** 和 **LangGraph** 构建的高级多智能体（Multi-Agent）协作系统。本平台通过模块化解耦、资源调度和语义记忆，实现了工业级的“规划-执行-反馈”闭环，并深度集成了 **人机协作 (Human-in-the-Loop, HITL)** 机制。

## ✨ 核心特性

* **动态任务调度 (Supervisor Mode)**：由 `OrchestratorAgent` 充当核心大脑，基于项目状态实时做出单步决策，灵活决定下一个执行 Agent。
* **人机协作循环 (HITL)**：在执行代码编写或数据分析等关键任务前，系统会自动进入中断状态，支持人工审批、修改指令或提供实时反馈。
* **多专业智能体团队 (Crews)**：
    * **Coding Crew**：具备 Python AST 语法自动检查与自愈能力，包含 Coder 和严格的 Reviewer。
    * **Data Crew**：数据科学家与商业分析师协作，确保技术报告具备实际的可执行商业价值。
    * **Content Crew**：创意作家与主编配合，打磨富有感染力且结构严谨的文字内容。
* **自动 API Key 轮询 (Key Rotation)**：内置 `GeminiKeyRotator`，支持多个 API Key 轮换与自动重试，有效应对 API 限速和故障。
* **语义记忆库 (RAG Ready)**：集成 Pinecone 向量数据库，支持跨任务的上下文存储与精准检索。
* **双端交互支持**：
    * **CLI 模式**：交互式命令行工具，支持图片输入和实时状态干预。
    * **Web 模式**：基于 FastAPI 和 SSE (Server-Sent Events) 的流式后端，配合响应式控制台。

## 📂 项目结构

```text
├── agents/
│   ├── orchestrator/    # 任务分解与动态规划核心
│   ├── crews/           # 专业 Agent 小组 (Coding, Data, Content)
│   └── agents.py        # 研究员 (Researcher) 等单点 Agent 定义
├── core/
│   ├── rotator.py       # API Key 轮询管理器
│   ├── models.py        # 统一的 Pydantic 数据模型与 Artifacts 定义
│   └── api_models.py    # API 接口数据结构
├── tools/
│   ├── search.py        # 具备自动降级策略的搜索工具
│   └── memory.py        # 基于 Pinecone 的向量记忆库
├── workflow/
│   ├── graph.py         # 基于 LangGraph 的状态机主图构建
│   └── engine.py        # 异步流式执行引擎
├── api_server.py        # FastAPI SSE 后端服务器
└── main.py              # CLI 交互式启动入口
```

## 🚀 快速启动

### 1. 环境准备
推荐使用 Python 3.11 环境：
```bash
pip install -r requirements.txt
```
*主要依赖包括：`langgraph`, `google-genai`, `fastapi`, `pydantic`, `pinecone-client`, `sse-starlette`。*

### 2. 配置环境变量
在项目根目录创建 `.env` 文件：
```env
# Gemini API Keys，多个 Key 用逗号分隔
GEMINI_API_KEYS="key1,key2,key3"

# Pinecone (RAG) 配置
PINECONE_API_KEY="您的API_KEY"
PINECONE_ENVIRONMENT="您的环境名称"
VECTOR_INDEX_NAME="agent-memory-index"
```

### 3. 运行平台
* **交互式 CLI 模式**：
    ```bash
    python main.py
    ```
* **Web API 服务**：
    ```bash
    python api_server.py
    ```
    启动后访问 `http://localhost:8000/static/index.html` 进入 HITL 控制台。

## 🛠️ 工作流逻辑

1.  **状态初始化**：系统创建 `ProjectState`，包含用户输入、图片数据及对话历史。
2.  **Orchestrator 规划**：调度器分析当前 Artifacts 和历史，决定下一步执行的 Agent 及指令。
3.  **Crew 内循环迭代**：如 Coding Crew 内部会进行“编写-审查-修复”的循环，直至通过或达到最大迭代次数。
4.  **人机协作中断**：在进入关键 Crew 节点前，系统会触发 `interrupt_before`，等待用户审批或修改状态。
5.  **结果交付**：任务完成后生成结构化的研究报告、代码包或分析文档。

---
*基于 Gemini 2.5 Flash 驱动的多 Agent 系统*
