import os
import random
import sys 
from typing import List, Dict, Any, Optional, Tuple
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv 

# 在导入配置之前，加载环境变量
load_dotenv()

# 从所有模块导入依赖
from config.keys import GEMINI_API_KEYS, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from workflow.graph import build_agent_workflow, AgentGraphState


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
    运行 LangGraph 流程的一个完整迭代。
    """
    last_valid_project_state = current_state['project_state']
    
    try:
        # LangGraph 流式运行
        for step in app.stream(current_state):
            final_state = step
            
            if "__end__" in step:
                print(f"--- 流程结束于: {list(step.keys())[0]} ---")
                return last_valid_project_state, True 
            
            node_name = list(step.keys())[0]
            print(f"--- 流程当前节点: {node_name} ---")
            
            if 'project_state' in step[node_name]:
                last_valid_project_state = step[node_name]['project_state']
                
        return last_valid_project_state, False
        
    except Exception as e:
        # 这里捕捉的是 Graph 内部抛出的未处理异常
        print(f"❌ 流程运行中发生未捕获异常: {e}")
        # 将异常传递出去，或者在这里返回状态供主循环处理
        raise e 


def test_platform_workflow():
    """
    测试 LangGraph 集成后的多 Agent 协作流程，并实现交互式人机协作循环。
    """
    print("\n--- 正在初始化 Agent 平台 ---")
    
    memory_tool = None 
    current_project_state = None 

    if not GEMINI_API_KEYS:
         raise ValueError("致命错误：未在 .env 中配置 GEMINI_API_KEYS。")

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
        
        # 5. 交互式主循环
        while not is_complete:
            try:
                print("\n--- 启动新一轮 Agent 流程 (Orchestrator 将首先检查状态) ---")
                
                # 运行迭代
                current_state_dict = {"project_state": current_project_state}
                new_project_state, iteration_complete = run_workflow_iteration(app, current_state_dict)
                
                # 更新状态
                if new_project_state:
                    current_project_state = new_project_state
                
                is_complete = iteration_complete
                
                # 检查是否有自动回退产生的错误
                if current_project_state.last_error and not is_complete:
                    print(f"\n⚠️ 警告：系统检测到内部错误: {current_project_state.last_error}")
                    print("🔄 正在触发 Orchestrator 自我修复流程...")
                    continue # 直接进入下一轮，让 Orchestrator 处理反馈

                if is_complete:
                    break

                if current_project_state.execution_plan:
                    print(f"🔄 流程自动继续：还有 {len(current_project_state.execution_plan)} 步待执行。")
                    continue 

                # 正常的人机协作点
                print("\n===========================================================")
                print("🚀 Agent 团队已完成当前计划序列。")
                if current_project_state.final_report:
                     print(f"✅ 当前产出报告 (部分):\n{current_project_state.final_report[:500]}...")

                print("\n--- 人机协作 (Human-in-the-Loop) 介入点 ---")
                user_feedback = input("🚨 请输入反馈（输入 'q' 退出，或输入指令）：\n>>> ")
                
                if user_feedback.lower() in ["exit", "q", ""]:
                    is_complete = True
                    break
                    
                current_project_state.user_feedback_queue = user_feedback
                print("🚨 反馈已注入，重定向到 Orchestrator...")

            except KeyboardInterrupt:
                print("\n\n🛑 用户强制中断流程。")
                choice = input("👉 您希望：(1) 退出程序 (2) 恢复并手动输入新指令？ [1/2]: ")
                if choice == "2":
                    manual_fix = input("请输入修正指令以恢复 Orchestrator: ")
                    current_project_state.user_feedback_queue = f"用户手动恢复: {manual_fix}"
                    continue
                else:
                    break
            except Exception as e:
                # [Level 2] 人工兜底机制
                print(f"\n\n💥 严重系统错误 (Crash): {e}")
                print("🛡️ 触发人工兜底保护机制...")
                choice = input("👉 您希望：(1) 尝试保留当前状态并重试 (2) 放弃并退出？ [1/2]: ")
                
                if choice == "1":
                    print("🚑 正在尝试恢复状态并请求 Orchestrator 介入...")
                    # 注入系统级错误反馈，尝试让大脑接管
                    current_project_state.user_feedback_queue = f"SYSTEM CRASH RECOVERY: Previous attempt failed with {str(e)}. Please replan."
                    current_project_state.execution_plan = [] # 清空可能导致 crash 的旧计划
                    continue
                else:
                    break

        # 6. 最终状态总结
        final_project_state = current_project_state
        print(f"\n--- 最终流程结束。使用的最终状态 ID: {final_project_state.task_id} ---")
        
        if final_project_state.final_report:
            print(final_project_state.final_report)

        # 7. 人工审核 RAG 记忆清理
        if memory_tool and final_project_state:
             print("\n===========================================================")
             print(f"🧹 记忆库清理审核：任务ID {final_project_state.task_id}")
             print("===========================================================")
             
             confirm = input("🚨 主人喵，是否要删除该任务在 RAG 记忆库中的所有记录？(输入 'y' 确认删除) \n>>> ")
             if confirm.lower() == 'y':
                 memory_tool.delete_task_memory(final_project_state.task_id)
                 print("✅ 已遵照主人指令，记忆已清除喵！")
             else:
                 print("🛡️ 用户选择保留：RAG 记忆未被删除。")

    except ValueError as e:
        print(f"❌ 启动错误：{e}")
        
    finally:
        pass

if __name__ == "__main__":
    test_platform_workflow()
