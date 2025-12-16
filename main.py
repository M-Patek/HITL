import os
import random
import sys # 导入 sys 模块用于退出
from typing import List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv # 导入 load_dotenv

# 在导入配置之前，加载环境变量
load_dotenv()

# 从所有模块导入依赖
from config.keys import GEMINI_API_KEYS, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from workflow.graph import build_agent_workflow, AgentGraphState


# =======================================================
# 1. 平台启动与测试
# =======================================================

def get_user_initial_task() -> str:
    """从控制台获取用户的初始任务。"""
    print("\n===========================================================")
    print("🤖 Gemini Agent 协作平台 - 任务输入")
    print("===========================================================")
    print("请输入您的初始任务（例如：研究并总结最新的AI芯片发展趋势，然后编写一个Python数据分析脚本）：")
    initial_task = input(">>> ")
    print("===========================================================")
    
    if not initial_task.strip():
        print("❌ 任务输入为空。程序退出。")
        sys.exit(1)
        
    return initial_task.strip()

def run_workflow_iteration(app: StateGraph, current_state: AgentGraphState) -> Tuple[Optional[ProjectState], bool]:
    """
    运行 LangGraph 流程的一个完整迭代，直到任务完成或需要重新规划。
    返回最新的 ProjectState 和任务是否完成的布尔值。
    """
    last_valid_project_state = current_state['project_state']
    
    try:
        # LangGraph 流式运行
        for step in app.stream(current_state):
            final_state = step
            
            if "__end__" in step:
                print(f"--- 流程结束于: {list(step.keys())[0]} ---")
                return last_valid_project_state, True # 任务完成
            
            node_name = list(step.keys())[0]
            print(f"--- 流程当前节点: {node_name} ---")
            
            # 始终更新最近一次的有效状态
            if 'project_state' in step[node_name]:
                last_valid_project_state = step[node_name]['project_state']
                
                # 检查 Orchestrator 是否已经完成了当前计划的执行
                # 如果当前节点是 Orchestrator，并且它没有启动新的 next_steps，但也没有设置 END，
                # 或者如果有用户反馈队列，流程将在路由中中断，这里不需要特殊处理，只需确保状态更新。

        # 如果循环结束但没有命中 __end__ (通常发生在强制中断或错误后)
        return last_valid_project_state, False
        
    except Exception as e:
        print(f"❌ 流程运行中发生错误: {e}")
        return last_valid_project_state, False


def test_platform_workflow():
    """
    测试 LangGraph 集成后的多 Agent 协作流程，并实现交互式人机协作循环。
    """
    print("\n--- 正在初始化 Agent 平台 ---")
    
    memory_tool = None # 预定义，确保清理步骤可以访问
    
    # 检查是否有有效的 Gemini Key，如果没有，则抛出错误
    if not GEMINI_API_KEYS:
         raise ValueError("致命错误：未在 .env 中配置 GEMINI_API_KEYS。请检查您的 .env 文件。")

    try:
        # 1. 实例化核心工具和资源
        rotator = GeminiKeyRotator(GEMINI_API_KEYS)
        memory_tool = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
        search_tool_instance = GoogleSearchTool()

        # 2. 获取用户任务
        initial_task = get_user_initial_task()
        
        # 3. 构建 Agent Workflow
        app = build_agent_workflow(rotator, memory_tool, search_tool_instance) 
        
        # 4. 初始化项目状态
        current_project_state = ProjectState(
            task_id=f"TASK_{random.randint(1000, 9999)}",
            user_input=initial_task,
            full_chat_history=[
                {"role": "user", "parts": [{"text": initial_task}]}
            ]
        )
        
        print(f"✨ 平台启动 (动态调度) | 任务ID: {current_project_state.task_id} | 任务：{initial_task[:50]}...")
        print("===========================================================")

        is_complete = False
        
        # 5. 交互式主循环：直到任务完成或用户手动退出
        while not is_complete:
            
            print("\n--- 启动新一轮 Agent 流程 (Orchestrator 将首先检查状态) ---")
            
            # 运行一个完整的迭代（直到 Orchestrator 再次被调用或任务结束）
            current_state_dict = {"project_state": current_project_state}
            current_project_state, is_complete = run_workflow_iteration(app, current_state_dict)
            
            # 如果任务已完成，跳出循环
            if is_complete:
                break

            # 如果流程被 Orchestrator 路由回 Orchestrator (例如，规划错误或未完成)，继续循环
            if current_project_state.execution_plan:
                print(f"🔄 流程自动继续：还有 {len(current_project_state.execution_plan)} 步待执行。")
                continue # 重新开始下一轮迭代

            # 流程已暂停 (Orchestrator完成了当前计划，等待新的任务/反馈)
            print("\n===========================================================")
            print("🚀 Agent 团队已完成当前计划序列。")
            if current_project_state.final_report:
                 print(f"✅ 当前产出报告 (部分):\n{current_project_state.final_report[:500]}...")

            print("\n--- 人机协作 (Human-in-the-Loop) 介入点 ---")
            user_feedback = input("🚨 是否需要修正、指正设计或添加新任务？请输入反馈（或直接按 Enter/Exit 完成）：\n>>> ")
            
            if user_feedback.lower() in ["exit", "q", ""]:
                is_complete = True
                print("\n🎉 用户选择结束流程。最终结果已生成。")
                break
                
            # 注入用户反馈，强制 Orchestrator 重新规划
            current_project_state.user_feedback_queue = user_feedback
            print("\n===========================================================")
            print("🚨 发现用户反馈！流程中断，重定向到 Orchestrator 进行重规划...")
            print("===========================================================")

        # 6. 最终状态总结
        final_project_state = current_project_state
        print(f"\n--- 最终流程结束。使用的最终状态 ID: {final_project_state.task_id} ---")
        
        # ... 最终报告输出 ...
        if final_project_state.final_report:
            print("\n===========================================================")
            print("📜 最终交付物")
            print("===========================================================")
            print(final_project_state.final_report)
        else:
             print("📜 最终交付物: 无最终报告产出。")

    except ValueError as e:
        print(f"❌ 启动错误：{e}")
        
    finally:
        # =======================================================
        # 7. RAG 内存清理阶段 (任务生命周期结束) - 无论成功与否，都尝试清理
        # =======================================================
        if memory_tool and current_project_state:
             print("\n===========================================================")
             print(f"🧹 清理阶段：删除任务 {current_project_state.task_id} 相关的 RAG 记忆")
             print("===========================================================")
             memory_tool.delete_task_memory(current_project_state.task_id)


if __name__ == "__main__":
    from typing import Tuple # 仅在 main 中需要导入 Tuple
    test_platform_workflow()
