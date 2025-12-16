from typing import TypedDict, List, Dict, Any, Optional
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
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
# 2. Researcher Agent (研究员)
#    Orchestrator 已移动至 agents/orchestrator/
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

    def run(self, state: AgentGraphState) -> Dict[str, Any]:
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
