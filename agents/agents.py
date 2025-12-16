from typing import TypedDict, List, Dict, Any, Optional
from core.rotator import GeminiKeyRotator
from core.models import ProjectState, ResearchArtifact
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
    单节点 Agent，负责调用搜索工具并生成结构化研究报告 (ResearchArtifact)。
    """
    def __init__(self, rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool, system_instruction: str):
        self.rotator = rotator
        self.memory_tool = memory_tool 
        self.search_tool = search_tool
        self.system_instruction = system_instruction

    def run(self, state: AgentGraphState) -> Dict[str, Any]:
        current_state = state["project_state"]
        
        # [Updated] 适配 Supervisor 模式：从 next_step 获取指令
        instruction = "Conduct research based on user input."
        if current_state.next_step and "instruction" in current_state.next_step:
            instruction = current_state.next_step["instruction"]
            
        print(f"\n🔬 [Researcher] 开始搜索: {instruction[:30]}...")
        
        try:
            # 1. 执行搜索
            search_results = self.search_tool.search(instruction)
            
            # 2. 总结结果 (请求结构化输出)
            prompt = f"""
            Based on the search results below, generate a structured ResearchArtifact.
            
            Search Results:
            {search_results}
            
            User Instruction:
            {instruction}
            """
            
            # [Updated] 使用 Schema 强制输出 JSON
            response_text = self.rotator.call_gemini_with_rotation(
                model_name="gemini-2.5-flash",
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=ResearchArtifact
            )
            
            if response_text:
                # 3. 解析并存储 Artifact
                artifact = ResearchArtifact.model_validate_json(response_text)
                
                # 存入 artifacts 仓库
                current_state.artifacts["research"] = artifact.model_dump()
                
                # 兼容旧字段
                current_state.research_summary = artifact.summary
                
                # 存入记忆库
                self.memory_tool.store_output(current_state.task_id, artifact.summary, "Researcher")
                
                # 记录历史
                display_text = f"[Researcher Output]\nSummary: {artifact.summary}\nKey Facts: {len(artifact.key_facts)} items."
                current_state.full_chat_history.append({"role": "model", "parts": [{"text": display_text}]})
                
                print("✅ [Researcher] 任务完成 (Artifact Saved).")
            else:
                raise ValueError("Researcher API 返回为空")
            
        except Exception as e:
            error_msg = f"Researcher Failed: {str(e)}"
            print(f"❌ {error_msg}")
            current_state.last_error = error_msg
            # 寻求人工介入或重规划
            current_state.user_feedback_queue = f"Researcher failed: {str(e)}"
            
        return {"project_state": current_state}
