import os
import random
from typing import List
from langgraph.graph import StateGraph, END

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

def test_platform_workflow():
    """
    测试 LangGraph 集成后的多 Agent 协作流程，并模拟人机协作循环。
    """
    print("\n--- 正在初始化 Agent 平台 ---")
    
    memory_tool = None # 预定义，确保清理步骤可以访问
    final_project_state_2 = None # 预定义，确保清理步骤可以访问 task_id
    
    try:
        # 1. 实例化核心工具和资源
        rotator = GeminiKeyRotator(GEMINI_API_KEYS)
        memory_tool = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
        search_tool_instance = GoogleSearchTool()

        # 2. 构建 Agent Workflow
        # 注意: build_agent_workflow 现在会尝试加载 prompts/ 文件夹下的 Prompt 文件
        app = build_agent_workflow(rotator, memory_tool, search_tool_instance) 
        
        # 3. 初始化项目状态
        initial_task = "请研究 2024 年 Q3 季度全球电动汽车市场的主要增长趋势和领导者，并总结关键数据。"
        
        initial_project_state = ProjectState(
            task_id=f"TASK_{random.randint(1000, 9999)}",
            user_input=initial_task,
            full_chat_history=[
                {"role": "user", "parts": [{"text": initial_task}]}
            ]
        )
        initial_graph_state = {"project_state": initial_project_state}
        
        print("\n===========================================================")
        print(f"✨ 平台启动 (动态调度) | 任务ID: {initial_project_state.task_id}")
        print("===========================================================")

        # 4. 运行 Agent 流程 (第一轮：自主规划与执行)
        print("\n--- 运行第一阶段：自主规划与执行 (Orchestrator -> Researcher -> Analyst) ---")
        
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
            
        
        # 5. 安全地获取最终项目状态
        # 无论流程如何结束，使用最后一次成功更新的状态
        final_project_state = last_valid_project_state
        print(f"\n--- 第一轮流程结束。使用的最终状态 ID: {final_project_state.task_id} ---")
        
        # 6. 注入用户反馈 (模拟人机介入)
        
        # 模拟：流程结束后，用户检查了报告并发现问题
        if final_project_state.final_report:
            print("\n===========================================================")
            print("🚨 模拟用户介入：注入反馈进行重规划...")
            print("===========================================================")
            
            # 注入新的状态，带有用户反馈
            new_graph_state = {"project_state": final_project_state} # 从上一次的有效状态开始
            # 用户反馈要求回溯到研究阶段，补充数据
            new_graph_state['project_state'].user_feedback_queue = "研究中遗漏了中国比亚迪的欧洲扩张数据，请补充！然后重新分析报告。"
            
            # 7. 运行流程 (第二轮：由路由发现反馈 -> Orchestrator 重规划 -> Agent 修正)
            
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
            print(f"✅ 重规划流程完成。最终报告的长度变化: {len(final_project_state_2.final_report) if final_project_state_2.final_report else 0} 字符。")
            print(f"新研究摘要 (部分): {final_project_state_2.research_summary[:200] if final_project_state_2.research_summary else '无摘要'}...")
            print("请检查控制台，观察 Orchestrator 如何从 Orchestrator -> Researcher -> Analyst 进行重定向。")
        else:
            print("❌ 协作失败，无法注入用户反馈。可能第一轮运行就失败了。")
            final_project_state_2 = final_project_state # 如果第二轮未运行，使用第一轮的状态进行清理

    except ValueError as e:
        print(f"❌ 启动错误：{e}")
        
    finally:
        # =======================================================
        # 8. RAG 内存清理阶段 (任务生命周期结束) - 无论成功与否，都尝试清理
        # =======================================================
        if memory_tool and final_project_state_2:
             print("\n===========================================================")
             print(f"🧹 清理阶段：删除任务 {final_project_state_2.task_id} 相关的 RAG 记忆")
             print("===========================================================")
             memory_tool.delete_task_memory(final_project_state_2.task_id)


if __name__ == "__main__":
    test_platform_workflow()
