🤖 Gemini 动态多 Agent 协作平台

这是一个基于 Gemini API 和 LangGraph 构建的生产级多 Agent 协作系统。本平台实现了高度的 模块化解耦、资源调度、语义记忆 和 人机协作 (Human-in-the-Loop, HITL) 循环。

✨ 核心特性

本平台旨在克服传统单 Agent 的局限性，通过专业 Agent 团队的协作来处理复杂的、多步骤的项目任务：

动态调度与智能回溯： 使用 OrchestratorAgent 自主规划任务流程（LangGraph 骨架），并能在出现错误或收到用户反馈时，自动进行流程中断和重定向修正。

API 轮询与高可用性： 实现了 GeminiKeyRotator，自动管理和轮换多个 API Key，确保在高并发和限速下的系统稳定性。

语义记忆库 (RAG Ready)： 预留了 VectorMemoryTool 接口，用于集成向量数据库（如 Pinecone），解决 Agent 协作中的上下文长度爆炸问题，实现精准记忆检索。

专业 Agent 团队： 平台包含 ResearcherAgent (集成外部搜索)、AnalystAgent 等专业 Agent，并通过 模块化 实现了职责彻底分离。

人机协作循环 (HITL)： 用户可以随时通过 user_feedback_queue 介入流程，强制 Agent 团队进行重规划和修正。

⚙️ 架构概览

本项目采用解耦架构，方便维护和扩展：

config/: 存储 API Keys 和外部环境配置。

core/: 存放 API 轮询逻辑和共享数据结构。

tools/: 封装外部服务（如搜索、向量记忆）的接口。

agents/: 定义所有专业 Agent 的业务逻辑。

workflow/: 实现 LangGraph 的核心图结构和动态路由。

main.py: 应用启动入口和测试逻辑。

🚀 快速启动

1. 环境准备 (使用 Conda)

# 创建并激活环境
conda create --name gemini-agent-env python=3.11 -y
conda activate gemini-agent-env

# 安装核心依赖
pip install langgraph google-genai pydantic pinecone-client tiktoken


2. 配置 Key

编辑 config/keys.py 文件，替换以下占位符为您真实的 Key：

GEMINI_API_KEYS：您的 Gemini API Key 列表。

PINECONE_API_KEY, PINECONE_ENVIRONMENT：您的向量数据库配置（可选，但推荐）。

3. 运行平台

确保您在项目根目录下，运行 main.py 启动测试流程：

python main.py


项目将自动开始 调度 -> 执行 -> 重规划 的动态协作过程。
