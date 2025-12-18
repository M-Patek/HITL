from typing import Dict, Any, Literal, List, Optional
import json
from pydantic import BaseModel, Field

from core.rotator import GeminiKeyRotator
from core.models import ProjectState, TaskStatus
from config.keys import GEMINI_MODEL_NAME
from tools.registry import ToolRegistry

# --- Output Models ---

class ToolCallSpec(BaseModel):
    tool_name: str
    tool_params: Dict[str, Any]

class SupervisorDecision(BaseModel):
    """
    [ReAct + Speculative] Orchestrator 的结构化决策输出
    """
    thought: str = Field(..., description="思考过程 (Chain of Thought)")
    action_type: Literal["delegate_to_crew", "call_tool", "ask_human", "finish_task"]
    
    delegate_target: Optional[Literal["researcher", "coding_crew", "data_crew", "content_crew"]] = None
    tool_call: Optional[ToolCallSpec] = None
    human_question: Optional[str] = None
    
    # [Speculative Warming] 预测性资源加载
    speculative_search_queries: Optional[List[str]] = Field(
        default=None, 
        description="如果你预判后续步骤需要大量背景知识，在此列出 1-3 个搜索关键词，系统将后台静默预加载。"
    )
    
    instruction: str = Field(..., description="具体的执行指令或总结")

class ComplexityCheck(BaseModel):
    reasoning: str
    complexity: Literal["simple", "complex"]

class OrchestratorAgent:
    """
    [SWARM 3.0] ReAct Orchestrator with Speculative Warming
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = GEMINI_MODEL_NAME

    def _perform_context_handshake(self, state: ProjectState) -> str:
        active_node = state.get_active_node()
        if not active_node: return ""
        # (复用之前的 Handshake 逻辑: 扫描兄弟节点的摘要)
        scope_node = state.root_node
        if active_node.parent_id:
            parent = state.node_map.get(active_node.parent_id)
            if parent: scope_node = parent
        handshake_report = []
        completed_siblings = [c for c in scope_node.children if c.status == TaskStatus.COMPLETED and c.node_id != active_node.node_id]
        if completed_siblings:
            handshake_report.append(f"📜 [Handshake] Siblings Summary:")
            for node in completed_siblings:
                handshake_report.append(f"   - {node.instruction}: {node.semantic_summary}")
        return "\n".join(handshake_report)

    def _get_dynamic_context(self, state: ProjectState) -> str:
        active_node = state.get_active_node()
        if not active_node: return "Error"
        
        ctx = [f"🌍 Global: {state.root_node.instruction}"]
        ctx.append(self._perform_context_handshake(state))
        ctx.append(f"\n📍 Focus: {active_node.instruction}")
        
        # [Speculative] 如果有预加载的搜索结果，展示在这里
        if state.prefetch_cache:
            ctx.append("\n⚡️ [Prefetched Knowledge]:")
            for q, res in list(state.prefetch_cache.items())[-2:]: # 只展示最近2条
                ctx.append(f"   - Query '{q}': {res[:200]}...")

        return "\n".join(ctx)

    def _classify_complexity(self, context_str: str) -> str:
        # (保持原有的复杂度分类逻辑)
        return "complex" 

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        project_state = state.get("project_state")
        if not project_state: return {}

        print(f"\n⚙️ [Orchestrator] Thinking... (Node: {project_state.active_node_id[-4:]})")
        
        # 1. 准备上下文
        dynamic_context = self._get_dynamic_context(project_state)
        
        # 2. 构造 Prompt
        tool_desc = ToolRegistry.get_tool_description_str()
        final_prompt = f"""
        Analyze context and decide next move.
        
        === CONTEXT ===
        {dynamic_context}
        
        === TOOLS ===
        {tool_desc}
        
        === AGENTS ===
        - researcher, coding_crew, data_crew, content_crew
        
        Output JSON following SupervisorDecision schema.
        If you foresee a need for data (e.g., "I need to check stock prices later"), put queries in 'speculative_search_queries'.
        """
        
        # 3. 调用 LLM
        try:
            complexity = self._classify_complexity(dynamic_context)
            response = self.rotator.call_gemini_with_rotation(
                model_name="auto", 
                contents=[{"role": "user", "parts": [{"text": final_prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=SupervisorDecision,
                complexity=complexity
            )
            
            if response:
                cleaned = response.replace("```json", "").replace("```", "").strip()
                decision = SupervisorDecision.model_validate_json(cleaned)
                
                print(f"   🧠 Thought: {decision.thought}")
                print(f"   ⚡️ Action: {decision.action_type.upper()}")
                
                # 处理 Speculative Search 字段 (实际上由 Graph 处理，这里只负责存入 State 或 Decision)
                # 我们将其暂存到 next_step 的 meta 中，或者直接通过 graph logic 处理
                
                # Mapping decision...
                if decision.action_type == "finish_task":
                    project_state.router_decision = "finish"
                    project_state.final_report = decision.instruction
                    if project_state.get_active_node():
                        project_state.get_active_node().status = TaskStatus.COMPLETED

                elif decision.action_type == "delegate_to_crew":
                    project_state.router_decision = "continue"
                    project_state.next_step = {
                        "agent_name": decision.delegate_target,
                        "instruction": decision.instruction,
                        "speculative_queries": decision.speculative_search_queries # 传递给 Graph
                    }

                elif decision.action_type == "call_tool":
                    project_state.router_decision = "tool" 
                    project_state.next_step = {
                        "tool_name": decision.tool_call.tool_name,
                        "tool_params": decision.tool_call.tool_params
                    }
                    
                # 即使不是 Delegate，如果 Orchestrator 想要预热数据，也可以处理
                # 这里为了简化，我们假设只有在 Delegate 或 ToolCall 时才附带
                
            else:
                raise ValueError("Empty response")

        except Exception as e:
            print(f"❌ [Orchestrator] Error: {e}")
            project_state.last_error = str(e)
            project_state.router_decision = "human"

        return {"project_state": project_state}
