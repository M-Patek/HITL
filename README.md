# 🤖 Gemini Multi-Agent Swarm (SWARM 3.0)

这是一个基于 **Google Gemini 2.5 系列 API** 和 **LangGraph** 构建的工业级多智能体协作系统。本系统不仅实现了“规划-执行-反馈”的闭环，更通过独创的**分层任务树 (Hierarchical Task Tree)** 和 **RAPTOR 语义压缩**技术，解决了复杂长任务中的上下文爆炸与逻辑漂移问题。

## ✨ 核心前沿特性

### 🌲 分层任务树 (Hierarchical Task Tree)
系统不再采用扁平的对话流，而是将任务解析为递归的树状结构：
* **项目级 (Root)**：全局目标与战略规划。
* **子树级 (Sub-tree)**：专业智能体小组（Crew）的阶段性任务，完成后自动执行语义回归总结。
* **子叶级 (Leaf)**：具体的执行动作（如 Coder 编写、Reviewer 审查），任务细节在子树内部消化，不污染主图上下文。

### 🧠 动态上下文与 RAPTOR 压缩
* **语义剪枝**：当子树任务完成后，系统自动触发 RAPTOR 递归总结，将冗长的调试细节压缩为高维语义节点，确保主控 (Orchestrator) 决策永远基于最精华的信息。
* **按需加载**：Orchestrator 根据当前任务深度，动态从 `MemoryTree` 中提取关联上下文，实现极致的 Token 利用率。

### ⚡ 性能与成本极致平衡
* **模型分层路由 (Tiered Routing)**：自动识别任务复杂度。简单总结由 **Gemini 1.5 Flash** 处理，复杂代码由 **Gemini 1.5 Pro** 负责。
* **预测性预热 (Speculative Execution)**：系统会预判下一步动作，异步预热 Docker 沙箱或预加载搜索结果，大幅降低首字延迟。

### 🎨 Canvas 画布级交互
* **双栏协作界面**：左侧展示流式思考过程，右侧“画布区”动态渲染生成的代码、HTML 预览及高清晰度图表。
* **版本控制与溯源**：支持 Artifacts 的版本回溯，每一个产物都与具体的 `TaskNode` 和 `Trace ID` 绑定。

## 📂 项目结构

```text
├── agents/
│   ├── orchestrator/    # 具备 ReAct 逻辑的动态调度核心
│   ├── planner/         # 全局战略计划制定者
│   ├── crews/           # 专业 Agent 小组 (Coding, Data, Content)
│   └── agents.py        # 具备搜索增强能力的单点 Agent
├── core/
│   ├── protocol.py      # 标准化协作协议 (MCP 兼容)
│   ├── models.py        # 树状任务模型与 Pydantic 数据定义
│   └── rotator.py       # 支持模型分级的 API 轮询管理器
├── tools/
│   ├── registry.py      # 工具标准化注册中心
│   ├── sandbox.py       # 视觉增强型 Docker 安全沙箱
│   └── memory.py        # 支持 RAPTOR 树状检索的向量记忆库
├── workflow/
│   ├── graph.py         # 基于任务树回归的 LangGraph 主图
│   └── engine.py        # 异步流式执行与预测性预热引擎
└── static/              # Canvas 2.0 响应式前端交互系统
```

## 🚀 快速启动

1.  **配置环境**：安装 `requirements.txt` 中的依赖。
2.  **设置密钥**：在 `.env` 中配置多级 Gemini API Keys。
3.  **启动后端**：运行 `python api_server.py`。
4.  **开启画布**：访问 `http://localhost:8000/static/index.html` 进入 SWARM 工作站。
