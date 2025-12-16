import sys
import random
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入配置
from config.keys import GEMINI_API_KEYS, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME

# 导入核心模块
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# 导入工作流构建器
from workflow.graph import build_agent_workflow

def get_user_input() -> str:
    """交互式获取用户输入"""
    print("\n" + "="*50)
    print("🤖 Gemini Multi-Agent Swarm System")
    print("="*50)
    print("Please enter your complex task (e.g., 'Research AI trends and write a blog post'):")
    task = input(">>> ").strip()
    if not task:
        print("❌ Empty input. Exiting.")
        sys.exit(0)
    return task

async def main():
    # 1. 基础检查
    if not GEMINI_API_KEYS:
        print("❌ Error: GEMINI_API_KEYS not found in .env")
        return

    # 2. 初始化工具链
    print("\n🔧 Initializing Toolchain...")
    rotator = GeminiKeyRotator(GEMINI_API_KEYS)
    memory = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
    search = GoogleSearchTool()

    # 3. 构建图 (Agent Workflow)
    print("🕸️ Building Agent Graph...")
    app = build_agent_workflow(rotator, memory, search)

    # 4. 准备初始状态
    initial_task = get_user_input()
    project_state = ProjectState(
        task_id=f"TASK-{random.randint(1000, 9999)}",
        user_input=initial_task,
        full_chat_history=[{"role": "user", "parts": [{"text": initial_task}]}]
    )
    
    # 5. 运行图
    print(f"\n🚀 Starting Workflow for Task: {project_state.task_id}")
    
    # 将 Pydantic 对象包装进 TypedDict
    initial_graph_state = {"project_state": project_state}

    try:
        # LangGraph 的 .ainvoke() 或 .stream()
        # 注意：因为内部包含了 async 的子图调用，这里建议使用 async for
        async for step in app.astream(initial_graph_state):
            for node_name, node_state in step.items():
                print(f"--- Node Finished: {node_name} ---")
                # 实时更新本地状态显示（可选）
                if 'project_state' in node_state:
                    final_report = node_state['project_state'].final_report
                    if final_report:
                        print(f"📄 [Partial Output]: {final_report[:100]}...")

        print("\n✅ Workflow Completed.")
        
    except Exception as e:
        print(f"\n💥 Runtime Error: {e}")
        # 在这里可以添加人工兜底逻辑

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
