from typing import TypedDict, List, Dict, Any, Optional
from core.rotator import GeminiKeyRotator
from core.models import ProjectState, ResearchArtifact
from config.keys import GEMINI_MODEL_NAME
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# =======================================================
# 主图状态定义
# =======================================================

class AgentGraphState(TypedDict):
    project_state: ProjectState

# =======================================================
# Researcher Agent (Async Updated)
# =======================================================

class ResearcherAgent:
    """
    单节点 Agent，负责调用搜索工具并生成结构化研究报告。
    """
    def __init__(self, rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool, system_instruction: str):
        self.rotator = rotator
        self.memory_tool = memory_tool 
        self.search_tool = search_tool
        self.system_instruction = system_instruction

    async def run(self, state: AgentGraphState) -> Dict[str, Any]:
        """
        [Update] 改为 async 方法以配合异步 Search Tool
        """
        current_state = state["project_state"]
        
        instruction = "Conduct research based on user input."
        if current_state.next_step and "instruction" in current_state.next_step:
            instruction = current_state.next_step["instruction"]
            
        print(f"\n🔬 [Researcher] 开始搜索: {instruction[:30]}...")
        
        try:
            # 1. 执行异步搜索
            search_results = await self.search_tool.search(instruction)
            
            # 2. 总结结果
            prompt = f"""
            Based on the search results below, generate a structured ResearchArtifact.
            
            Search Results:
            {search_results}
            
            User Instruction:
            {instruction}
            """
            
            # 使用配置中的模型名称
            response_text = self.rotator.call_gemini_with_rotation(
                model_name=GEMINI_MODEL_NAME,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=ResearchArtifact
            )
            
            if response_text:
                artifact = ResearchArtifact.model_validate_json(response_text)
                current_state.artifacts["research"] = artifact.model_dump()
                current_state.research_summary = artifact.summary
                self.memory_tool.store_output(current_state.task_id, artifact.summary, "Researcher")
                
                display_text = f"[Researcher Output]\nSummary: {artifact.summary}\nKey Facts: {len(artifact.key_facts)} items."
                current_state.full_chat_history.append({"role": "model", "parts": [{"text": display_text}]})
                print("✅ [Researcher] 任务完成 (Artifact Saved).")
            else:
                raise ValueError("Researcher API 返回为空")
            
        except Exception as e:
            error_msg = f"Researcher Failed: {str(e)}"
            print(f"❌ {error_msg}")
            current_state.last_error = error_msg
            current_state.user_feedback_queue = f"Researcher failed: {str(e)}"
            
        return {"project_state": current_state}
