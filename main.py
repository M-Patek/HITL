import os
import random
import sys # 导入 sys 模块用于退出
from typing import List
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


def test_platform_workflow():
    """
    测试 LangGraph 集成后的多 Agent 协作流程，并模拟人机协作循环。
    """
    print("\n--- 正在初始化 Agent 平台 ---")
    
    memory_tool = None # 预定义，确保清理步骤可以访问
    final_project_state_2 = None # 预定义，确保清理步骤可以访问 task_id
    
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
        initial_project_state = ProjectState(
            task_id=f"TASK_{random.randint(1000, 9999)}",
            user_input=initial_task,
            full_chat_history=[
                {"role": "user", "parts": [{"text": initial_task}]}
            ]
        )
        initial_graph_state = {"project_state": initial_project_state}
        
        print(f"✨ 平台启动 (动态调度) | 任务ID: {initial_project_state.task_id} | 任务：{initial_task[:50]}...")
        print("===========================================================")

        # 5. 运行 Agent 流程 (第一轮：自主规划与执行)
        print("\n--- 运行第一阶段：自主规划与执行 (Orchestrator -> Agent 团队) ---")
        
        final_state = None
        # 添加变量来存储最新的有效 project_state
        last_valid_project_state = initial_project_state
        
        for step in app.stream(initial_graph_state):
            final_state = step
            if "__end__" in step:
                print(f"--- 流程结束于: {list(step.keys())[0]} ---")
            else:
                 node_name = list(step.keys())[0]
                 print(f"--- 流程当前节点: {node_name} ---")
                 # 如果节点有 project_state，则更新 last_valid_project_state
                 if 'project_state' in step[node_name]:
                     last_valid_project_state = step[node_name]['project_state']
            
        
        # 6. 安全地获取最终项目状态
        final_project_state = last_valid_project_state
        print(f"\n--- 第一轮流程结束。使用的最终状态 ID: {final_project_state.task_id} ---")
        
        # 7. 注入用户反馈（提示用户）
        print("\n===========================================================")
        print(f"✅ 任务完成。最终报告 (部分):\n{final_project_state.final_report[:500]}...")
        print("\n--- 人机协作 (Human-in-the-Loop) 循环 ---")
        
        user_feedback = input("🚨 是否需要修正或补充？请输入反馈（或直接按 Enter 结束）：\n>>> ")
        
        if user_feedback.strip():
            print("===========================================================")
            print("🚨 发现用户反馈！流程中断，重定向到 Orchestrator 进行重规划...")
            print("===========================================================")
            
            # 注入新的状态，带有用户反馈
            new_graph_state = {"project_state": final_project_state} # 从上一次的有效状态开始
            new_graph_state['project_state'].user_feedback_queue = user_feedback
            
            # 8. 运行流程 (第二轮：由路由发现反馈 -> Orchestrator 重规划 -> Agent 修正)
            
            final_state_generator_2 = app.stream(new_graph_state)
            
            final_state_2 = None
            last_valid_project_state_2 = final_project_state # 继承第一轮的有效状态
            
            for step in final_state_generator_2:
                final_state_2 = step
                if "__end__" in step:
                    print(f"--- 流程结束于: {list(step.keys())[0]} ---")
                else:
                    node_name = list(step.keys())[0]
                    print(f"--- 流程当前节点: {node_name} ---")
                    # 如果节点有 project_state，则更新 last_valid_project_state
                    if 'project_state' in step[node_name]:
                        last_valid_project_state_2 = step[node_name]['project_state']
            
            final_project_state_2 = last_valid_project_state_2 # 使用最后一次成功更新的状态
            
            print("\n===========================================================")
            print("🚀 第二轮流程结束 | 最终状态检查")
            print("===========================================================")
            print(f"✅ 重规划流程完成。最终报告 (更新后，部分):\n{final_project_state_2.final_report[:500]}...")
            print("请检查控制台，观察 Orchestrator 如何重定向以响应您的反馈。")
        else:
            final_project_state_2 = final_project_state
            print("\n===========================================================")
            print("🎉 用户选择结束流程。最终结果已生成。")
            print("===========================================================")

    except ValueError as e:
        print(f"❌ 启动错误：{e}")
        
    finally:
        # =======================================================
        # 9. RAG 内存清理阶段 (任务生命周期结束) - 无论成功与否，都尝试清理
        # =======================================================
        if memory_tool and final_project_state_2:
             print("\n===========================================================")
             print(f"🧹 清理阶段：删除任务 {final_project_state_2.task_id} 相关的 RAG 记忆")
             print("===========================================================")
             memory_tool.delete_task_memory(final_project_state_2.task_id)


if __name__ == "__main__":
    test_platform_workflow()
