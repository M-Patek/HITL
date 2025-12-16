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
        context_str += f"已完成的研究摘要: {current_state.research_summary[:100]}...\n" if current_state.research_summary else "无研究摘要。\n"
        context_str += f"已完成的最终报告: {current_state.final_report[:100]}...\n" if current_state.final_report else "无最终报告。\n"

        if current_state.user_feedback_queue:
            context_str += f"🚨 紧急用户反馈: {current_state.user_feedback_queue}\n"
            planning_goal = "你必须立即将此反馈整合到项目中，并生成一个新的、最短的执行计划来解决问题。"
        else:
            planning_goal = "请根据当前项目状态，生成下一步最优的执行计划。"
        
        # 提示词中只暴露三大 Crew 和 Researcher
        prompt = f"""
        你是一名高级项目调度员。你的任务是分析当前的项目状态，并严格以 JSON 格式输出下一步的执行计划。
        
        项目状态：{context_str}
        你的目标：{planning_goal}
        
        可用的 Agent 包括: 
        - 'researcher': (单兵) 负责搜索外部信息，更新知识库。
        - 'coding_crew': (战队) 负责代码编写、审查和重构。
        - 'data_crew': (战队) 负责数据分析、建模和商业洞察提炼。
        - 'content_crew': (战队) 负责创意写作、文案编辑和翻译。
        
        请严格根据 ExecutionPlan Pydantic 模型输出 JSON 计划。如果你认为项目已经完成，设置 is_complete=True 并且 next_steps 为空。
        """
        
        try:
            response_text = self.rotator.call_gemini_with_rotation(
                model_name=self.model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=ExecutionPlan
            )
            
            if response_text:
                plan_data = ExecutionPlan.model_validate_json(response_text)
                current_state.execution_plan = [step.model_dump() for step in plan_data.next_steps]
                current_state.user_feedback_queue = None
                print(f"✅ OrchestratorAgent 计划生成成功。下一步将执行 {len(plan_data.next_steps)} 步。")
            else:
                current_state.execution_plan = []
                print("❌ 调度器 Agent API 调用失败，无法生成计划。")

        except (Exception) as e:
            print(f"❌ 调度器 Agent JSON 解析/运行失败: {e}")
            current_state.execution_plan = []

        return {"project_state": current_state}


# =======================================================
# 2. Researcher Agent (研究员 - 保持独立)
# =======================================================
# Researcher 需要调用工具，保持独立比较方便
class ResearcherAgent:
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
        
        search_results = self.search_tool.search(current_instruction) 
        
        prompt_with_context = f"""
        [指令]: {current_instruction}
        [外部搜索结果]: {search_results}
        请利用这些结果生成一份精炼的研究摘要。
        """
        contents = current_state.full_chat_history + [{"role": "user", "parts": [{"text": prompt_with_context}]}]
        
        research_result = self.rotator.call_gemini_with_rotation(
            model_name=self.model,
            contents=contents,
            system_instruction=self.system_instruction
        )
        
        if research_result:
            self.memory_tool.store_output(task_id=current_state.task_id, content=research_result, agent_role="Researcher")
            current_state.research_summary = research_result 
            print("✅ ResearcherAgent 工作完成，产出已存储到语义记忆库。")
            current_state.full_chat_history.append({"role": "model", "parts": [{"text": research_result}]})
        
        current_state.execution_plan.pop(0)
        return {"project_state": current_state}


# =======================================================
# 3. SimulatedCrewAgent (通用战队类) - [NEW & UPDATED]
# =======================================================

class SimulatedCrewAgent:
    """
    通用 Crew 代理类，用于实例化不同的战队 (Coding, Data, Content)。
    它利用专门的 Multi-Persona Prompt 来模拟团队协作。
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str, crew_name: str, output_target: str = "report"):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = "gemini-2.5-flash"
        self.crew_name = crew_name
        self.output_target = output_target # 'report' or 'code'

    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        if not current_state.execution_plan: return state
            
        current_instruction = current_state.execution_plan[0]['instruction']
        print(f"\n⚔️ {self.crew_name} 启动... (任务: {current_instruction[:50]}...)")
        print(f"👥 正在召集内部成员进行协作...")

        # 注入上下文
        prompt_with_context = f"""
        [任务指令]: {current_instruction}
        
        请作为 {self.crew_name} 开始内部协作。
        参考资料(研究摘要): {current_state.research_summary[:800] if current_state.research_summary else "无"}
        """
        
        contents = current_state.full_chat_history + [{"role": "user", "parts": [{"text": prompt_with_context}]}]
        
        crew_result = self.rotator.call_gemini_with_rotation(
            model_name=self.model,
            contents=contents,
            system_instruction=self.system_instruction
        )
        
        if crew_result:
            # 根据战队类型更新不同的状态字段
            if self.output_target == "code":
                current_state.code_blocks[self.crew_name] = crew_result
            else:
                current_state.final_report = crew_result # 数据和内容战队通常更新报告

            current_state.full_chat_history.append({"role": "model", "parts": [{"text": crew_result}]})
            print(f"✅ {self.crew_name} 任务完成！结果已合并。")
        else:
            print(f"❌ {self.crew_name} 执行失败。")

        current_state.execution_plan.pop(0)
        return {"project_state": current_state}
