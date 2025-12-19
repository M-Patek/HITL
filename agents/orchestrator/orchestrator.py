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
    [Phase 2 Upgrade] Orchestrator 决策结构升级：支持并行指挥
    """
    thought: str = Field(..., description="思考过程 (Chain of Thought), 请分析当前向量时钟状态和并行需求")
    action_type: Literal["delegate_to_crew", "call_tool", "ask_human", "finish_task"]
    
    # [Phase 2 Change] 支持多选，用于并行分发
    delegate_targets: Optional[List[Literal["researcher", "coding_crew", "data_crew", "content_crew"]]] = Field(
        default=None,
        description="选择 1 个或多个 Agent 并行执行任务"
    )
    
    # [Phase 2 New] 并行同步策略
    sync_requirement: Literal["all_completed", "any_completed", "none"] = Field(
        default="all_completed",
        description="定义并行任务的汇聚逻辑：所有分支完成(all)或任一完成(any)"
    )

    tool_call: Optional[ToolCallSpec] = None
    human_question: Optional[str] = None
    
    # [Speculative Warming] 预测性资源加载
    speculative_search_queries: Optional[List[str]] = Field(
        default=None, 
        description="预判后续步骤需要的搜索关键词（后台静默加载）"
    )
    
    instruction: str = Field(..., description="具体的执行指令或总结")

class ComplexityCheck(BaseModel):
    reasoning: str
    complexity: Literal["simple", "complex"]

class OrchestratorAgent:
    """
    [SWARM 3.0] ReAct Orchestrator with Parallel Awareness
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = GEMINI_MODEL_NAME

    def _perform_context_handshake(self, state: ProjectState) -> str:
        """
        [Phase 2 Upgrade] 基于执行图和向量时钟的握手
        """
        active_node = state.get_active_node()
        if not active_node: return ""
        
        handshake_report = []
        
        # 1. 向量时钟快照 (感知并行进度)
        clock_status = ", ".join([f"{k}:v{v}" for k, v in state.vector_clock.items()])
        handshake_report.append(f"🕰️ [Vector Clock Status]: {{{clock_status}}}")
        
        # 2. 兄弟/并行节点摘要
        # 简单策略：获取同一父节点下的已完成节点
        scope_node = state.root_node
        if active_node.parent_id:
            parent = state.node_map.get(active_node.parent_id)
            if parent: scope_node = parent
            
        completed_siblings = [c for c in scope_node.children if c.status == TaskStatus.COMPLETED and c.node_id != active_node.node_id]
        
        if completed_siblings:
            handshake_report.append(f"📜 [Sibling/Parallel Results]:")
            for node in completed_siblings:
                # 尝试显示该节点产生的最新 Artifact 版本
                handshake_report.append(f"   - Agent '{node.stage_protocol.meta_data.get('agent', 'Unknown')}': {node.semantic_summary[:200]}...")
                
        return "\n".join(handshake_report)

    def _get_dynamic_context(self, state: ProjectState) -> str:
        active_node = state.get_active_node()
        if not active_node: return "Error"
        
        ctx = [f"🌍 Global Task: {state.root_node.instruction}"]
        ctx.append(self._perform_context_handshake(state))
        ctx.append(f"\n📍 Current Focus (Node {active_node.node_id[-4:]}): {active_node.instruction}")
        
        # [Speculative] Prefetch Cache Display
        if state.prefetch_cache:
            ctx.append("\n⚡️ [Prefetched Knowledge]:")
            for q, res in list(state.prefetch_cache.items())[-2:]:
                ctx.append(f"   - Query '{q}': {res[:200]}...")

        return "\n".join(ctx)

    def _classify_complexity(self, context_str: str) -> str:
        # (保持原有的复杂度分类逻辑)
        return "complex" 

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        project_state = state.get("project_state")
        if not project_state: return {}

        print(f"\n⚙️ [Orchestrator] Thinking... (Clock: {project_state.vector_clock})")
        
        # 1. 准备上下文
        dynamic_context = self._get_dynamic_context(project_state)
        
        # 2. 构造 Prompt
        tool_desc = ToolRegistry.get_tool_description_str()
        final_prompt = f"""
        Analyze context and decide next move. 
        You are the Conductor. You can dispatch MULTIPLE agents in parallel if the task requires it.
        
        === CONTEXT & CLOCK ===
        {dynamic_context}
        
        === TOOLS ===
        {tool_desc}
        
        === AVAILABLE CREWS ===
        - researcher (Info gathering)
        - coding_crew (Software dev)
        - data_crew (Analysis)
        - content_crew (Writing)
        
        Output JSON following SupervisorDecision schema.
        Use 'delegate_targets' (list) to trigger parallel work.
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
                
                # Mapping decision...
                if decision.action_type == "finish_task":
                    project_state.router_decision = "finish"
                    project_state.final_report = decision.instruction
                    if project_state.get_active_node():
                        project_state.get_active_node().status = TaskStatus.COMPLETED

                elif decision.action_type == "delegate_to_crew":
                    project_state.router_decision = "continue"
                    # [Phase 2 Change] 将多选目标打包
                    project_state.next_step = {
                        "parallel_agents": decision.delegate_targets, # List[str]
                        "sync_requirement": decision.sync_requirement,
                        "instruction": decision.instruction,
                        "speculative_queries": decision.speculative_search_queries
                    }
                    print(f"   🚀 Dispatching: {decision.delegate_targets}")

                elif decision.action_type == "call_tool":
                    project_state.router_decision = "tool" 
                    project_state.next_step = {
                        "tool_name": decision.tool_call.tool_name,
                        "tool_params": decision.tool_call.tool_params
                    }
                    
            else:
                raise ValueError("Empty response from Gemini")

        except Exception as e:
            print(f"❌ [Orchestrator] Error: {e}")
            project_state.last_error = str(e)
            project_state.router_decision = "human"

        return {"project_state": project_state}
