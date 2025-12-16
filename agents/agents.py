from typing import List, Optional, Dict, Any, TypedDict
from core.rotator import GeminiKeyRotator
from core.models import ProjectState, ExecutionPlan, ExecutionStep, BaseModel
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# LangGraph State 需要
class AgentGraphState(TypedDict):
    project_state: ProjectState


# =======================================================
# 1. Orchestrator Agent (调度器)
# =======================================================

class OrchestratorAgent:
    """
    负责任务分解、动态规划、错误回溯和人机协作中断。
    它使用 JSON 模式输出结构化的 ExecutionPlan。
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = "gemini-2.5-flash" 
        
    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        print(f"\n⚙️ OrchestratorAgent 启动: 制定或修正计划...")
        
        # 1. 构造 Prompt
        context_str = f"原始用户输入: {current_state.user_input}\n"
        # 调度器只看摘要和状态，不需要全部历史
        context_str += f"已完成的研究摘要: {current_state.research_summary[:100]}...\n" if current_state.research_summary else "无研究摘要。\n"
        context_str += f"已完成的最终报告: {current_state.final_report[:100]}...\n" if current_state.final_report else "无最终报告。\n"

        if current_state.user_feedback_queue:
            context_str += f"🚨 紧急用户反馈: {current_state.user_feedback_queue}\n"
            planning_goal = "你必须立即将此反馈整合到项目中，并生成一个新的、最短的执行计划来解决问题。"
        else:
            planning_goal = "请根据当前项目状态，生成下一步最优的执行计划。"
        
        prompt = f"""
        你是一名高级项目调度员。你的任务是分析当前的项目状态，并严格以 JSON 格式输出下一步的执行计划。
        
        项目状态：{context_str}
        你的目标：{planning_goal}
        
        可用的 Agent 包括: 
        - 'researcher' (收集数据，更新知识库)
        - 'analyst' (分析数据，提炼洞察)
        - 'coding_crew' (内部高级编程子团队)
        
        请严格根据 ExecutionPlan Pydantic 模型输出 JSON 计划。如果你认为项目已经完成，设置 is_complete=True 并且 next_steps 为空。
        """
        
        # 2. 调用模型生成 JSON 计划
        try:
            response_text = self.rotator.call_gemini_with_rotation(
                model_name=self.model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=ExecutionPlan
            )
            
            if response_text:
                plan_data = ExecutionPlan.model_validate_json(response_text)
                
                # 存储 JSON 结构为字典列表，方便 LangGraph 使用
                current_state.execution_plan = [step.model_dump() for step in plan_data.next_steps]
                current_state.user_feedback_queue = None # 清空队列
                
                print(f"✅ OrchestratorAgent 计划生成成功。下一步将执行 {len(plan_data.next_steps)} 步。")
            else:
                current_state.execution_plan = []
                print("❌ 调度器 Agent API 调用失败，无法生成计划。")

        except (Exception) as e:
            print(f"❌ 调度器 Agent JSON 解析/运行失败: {e}")
            current_state.execution_plan = []

        return {"project_state": current_state}


# =======================================================
# 2. Researcher Agent (研究员)
# =======================================================

class ResearcherAgent:
    """
    模拟研究员 Agent 的行为。职责是利用工具（Google Search）收集信息。
    """
    def __init__(self, rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool, system_instruction: str):
        self.rotator = rotator
        self.memory_tool = memory_tool 
        self.search_tool = search_tool
        self.system_instruction = system_instruction
        self.model = "gemini-2.5-flash"

    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        
        if not current_state.execution_plan: return state
            
        current_instruction = current_state.execution_plan[0]['instruction']
        print(f"\n🔬 ResearcherAgent 开始工作... (指令: {current_instruction[:50]}...)")
        
        # 1. 使用工具执行任务
        # 使用当前指令作为搜索查询，确保搜索的焦点性
        search_results = self.search_tool.search(current_instruction) 
        
        # 2. 构造 Prompt (包含搜索结果)
        prompt_with_context = f"""
        请严格根据以下指令执行任务，并返回详细的总结内容。
        [指令]: {current_instruction}
        [外部搜索结果]: {search_results}
        请利用这些结果生成一份精炼的研究摘要。
        """
        
        contents = current_state.full_chat_history + [
            {"role": "user", "parts": [{"text": prompt_with_context}]}
        ]
        
        research_result = self.rotator.call_gemini_with_rotation(
            model_name=self.model,
            contents=contents,
            system_instruction=self.system_instruction
        )
        
        if research_result:
            # 存储到向量数据库 (模拟)
            self.memory_tool.store_output(
                task_id=current_state.task_id, 
                content=research_result, 
                agent_role="Researcher"
            )
            
            current_state.research_summary = research_result 
            print("✅ ResearcherAgent 工作完成，产出已存储到语义记忆库 (已更新摘要)。")
            current_state.full_chat_history.append({"role": "model", "parts": [{"text": research_result}]})
        else:
            print("❌ ResearcherAgent 失败，未更新状态。")

        current_state.execution_plan.pop(0)
        return {"project_state": current_state}


# =======================================================
# 3. Analyst Agent (分析师)
# =======================================================

class AnalystAgent:
    """
    模拟分析师 Agent 的行为。职责是读取研究数据，并进行提炼和分析。
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = "gemini-2.5-flash"

    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        
        if not current_state.execution_plan: return state
            
        current_instruction = current_state.execution_plan[0]['instruction']
        print(f"\n🧠 AnalystAgent 开始工作... (指令: {current_instruction[:50]}...)")
        
        # 1. 构造 Prompt (使用所有上下文)
        # 生产环境中：这里应该调用 memory_tool.retrieve_context() 获取知识
        
        contents = current_state.full_chat_history + [
            {"role": "user", "parts": [
                {"text": f"请严格根据指令和历史研究摘要，撰写一份专业的分析报告：{current_instruction}"}
            ]}
        ]
        
        analysis_result = self.rotator.call_gemini_with_rotation(
            model_name=self.model,
            contents=contents,
            system_instruction=self.system_instruction
        )
        
        if analysis_result:
            current_state.final_report = analysis_result
            print("✅ AnalystAgent 工作完成，已更新 final_report。")
            current_state.full_chat_history.append({"role": "model", "parts": [{"text": analysis_result}]})
        else:
            print("❌ AnalystAgent 失败，未更新状态。")

        current_state.execution_plan.pop(0)
        return {"project_state": current_state}


# =======================================================
# 4. CodingCrewAgent (子团队封装) - NEW!
# =======================================================

class CodingCrewAgent:
    """
    [分层架构节点]
    这是一个特殊的 Agent，它内部封装了一个 CrewAI 或 AutoGen 的子团队。
    它作为一个单一节点嵌入 LangGraph，负责处理复杂的编程、重构和审查闭环任务。
    """
    def __init__(self, rotator: GeminiKeyRotator):
        self.rotator = rotator
        # 在这里，实际项目中你可以初始化 CrewAI 的 Agents
        # from crewai import Agent, Task, Crew
        # self.coder = Agent(role='Senior Coder', goal='Write code', ...)
        # self.reviewer = Agent(role='Code Reviewer', goal='Review code', ...)

    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        
        if not current_state.execution_plan: return state
            
        # 获取指令，这通常是一个复杂的编程任务
        current_instruction = current_state.execution_plan[0]['instruction']
        print(f"\n🛠️ CodingCrewAgent (子团队) 启动... (任务: {current_instruction[:50]}...)")
        print("👥 正在召集内部 Crew (Coder & Reviewer)...")

        # =======================================================
        # 这里是 CrewAI / AutoGen 的内部运行逻辑 (模拟)
        # =======================================================
        # 实际代码示例:
        # task = Task(description=current_instruction, agent=self.coder)
        # crew = Crew(agents=[self.coder, self.reviewer], tasks=[task])
        # result = crew.kickoff()
        
        # 模拟 CrewAI 的输出
        simulated_code_output = f"""
# --- Generated by CrewAI Sub-team ---
# Task: {current_instruction}
# Status: Reviewed & Approved

def mission_critical_function():
    print("This code was generated by a specialized sub-team.")
    return True
"""
        
        # 将结果存入 Shared State
        current_state.code_blocks["crew_output"] = simulated_code_output
        
        # 也可以选择更新 final_report 或者追加到 chat history
        report_update = f"Coding Crew 已完成任务。生成的代码已通过内部审查。\n代码预览:\n{simulated_code_output}"
        current_state.full_chat_history.append({"role": "model", "parts": [{"text": report_update}]})
        
        print("✅ CodingCrewAgent 子团队任务完成！结果已合并。")

        # 移除已完成的计划步骤
        current_state.execution_plan.pop(0)
        return {"project_state": current_state}
