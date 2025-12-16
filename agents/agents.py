from typing import TypedDict, List, Dict, Any, Optional
from core.rotator import GeminiKeyRotator
from core.models import ProjectState, ExecutionPlan
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# =======================================================
# 主图状态定义
# =======================================================

class AgentGraphState(TypedDict):
    """
    LangGraph 主图流转的状态。
    包含一个核心的 project_state 对象。
    """
    project_state: ProjectState


# =======================================================
# 1. Orchestrator Agent (调度器)
# =======================================================

class OrchestratorAgent:
    """
    负责任务分解、动态规划和错误处理的核心大脑。
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = "gemini-2.5-flash" 
        
    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        print(f"\n⚙️ [Orchestrator] 正在分析项目状态...")
        
        # 构建上下文
        context_str = f"Task: {current_state.user_input}\n"
        if current_state.research_summary:
            context_str += f"Research Summary: {current_state.research_summary[:200]}...\n"
        if current_state.last_error:
            context_str += f"Last Error: {current_state.last_error}\n"
        
        # 简化版 Prompt 逻辑 (实际使用时可注入更多细节)
        prompt = f"""
        基于以下状态生成 JSON 执行计划: 
        {context_str}
        
        可用 Agent: 
        - 'researcher': 获取外部信息
        - 'coding_crew': 编写和审查代码 (Subgraph)
        - 'data_crew': 数据分析和商业洞察 (Subgraph)
        - 'content_crew': 创意写作和编辑 (Subgraph)
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
                
                # 重置错误和反馈状态
                current_state.user_feedback_queue = None
                current_state.last_error = None
                
                print(f"✅ [Orchestrator] 计划已更新: 下一步执行 {len(plan_data.next_steps)} 个步骤。")
            else:
                raise ValueError("Orchestrator API 返回为空")

        except Exception as e:
            print(f"❌ [Orchestrator] 规划失败: {e}")
            current_state.last_error = str(e)
            # 在严重错误时清空计划，防止死循环
            current_state.execution_plan = []

        return {"project_state": current_state}


# =======================================================
# 2. Researcher Agent (研究员)
# =======================================================

class ResearcherAgent:
    """
    单节点 Agent，负责调用搜索工具并总结结果。
    """
    def __init__(self, rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool, system_instruction: str):
        self.rotator = rotator
        self.memory_tool = memory_tool 
        self.search_tool = search_tool
        self.system_instruction = system_instruction

    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        if not current_state.execution_plan: 
            return state
        
        instruction = current_state.execution_plan[0]['instruction']
        print(f"\n🔬 [Researcher] 开始搜索: {instruction[:30]}...")
        
        try:
            # 1. 执行搜索
            search_results = self.search_tool.search(instruction)
            
            # 2. 总结结果
            prompt = f"基于以下搜索结果回答问题或总结信息：\n{search_results}\n\n用户指令：{instruction}"
            
            summary = self.rotator.call_gemini_with_rotation(
                model_name="gemini-2.5-flash",
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=self.system_instruction
            )
            
            if summary:
                current_state.research_summary = summary
                # 存入记忆库
                self.memory_tool.store_output(current_state.task_id, summary, "Researcher")
                
                # 记录历史并移除当前任务
                current_state.full_chat_history.append({"role": "model", "parts": [{"text": f"[Researcher]: {summary}"}]})
                current_state.execution_plan.pop(0)
                print("✅ [Researcher] 任务完成。")
            else:
                raise ValueError("Researcher API 返回为空")
            
        except Exception as e:
            error_msg = f"Researcher Failed: {str(e)}"
            print(f"❌ {error_msg}")
            current_state.last_error = error_msg
            current_state.user_feedback_queue = "Researcher failed, please replan."
            
        return {"project_state": current_state}
