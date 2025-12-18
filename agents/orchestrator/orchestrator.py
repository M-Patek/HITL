from typing import Dict, Any, Literal, List, Optional
import json
from pydantic import BaseModel, Field

from core.rotator import GeminiKeyRotator
from core.models import ProjectState, TaskNode, TaskLevel, TaskStatus
from config.keys import GEMINI_MODEL_NAME
from tools.registry import ToolRegistry

# --- Output Models for ReAct ---

class ToolCallSpec(BaseModel):
    tool_name: str
    tool_params: Dict[str, Any]

class SupervisorDecision(BaseModel):
    """
    [ReAct] Orchestrator 的结构化决策输出
    """
    thought: str = Field(..., description="思考过程 (Chain of Thought)")
    action_type: Literal["delegate_to_crew", "call_tool", "ask_human", "finish_task"]
    
    # 互斥字段：根据 action_type 填充其中一个
    delegate_target: Optional[Literal["researcher", "coding_crew", "data_crew", "content_crew"]] = None
    tool_call: Optional[ToolCallSpec] = None
    human_question: Optional[str] = None
    
    instruction: str = Field(..., description="具体的执行指令或总结")

class OrchestratorAgent:
    """
    [SWARM 3.0] ReAct Orchestrator
    基于任务树 (Task Tree) 和动态上下文的超级调度器。
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = GEMINI_MODEL_NAME

    def _get_dynamic_context(self, state: ProjectState) -> str:
        """
        [Dynamic Context] 根据当前节点深度构建上下文
        """
        active_node = state.get_active_node()
        if not active_node: return "Error: No active node."

        context = []
        
        # 1. 全局目标
        context.append(f"Global Goal: {state.root_node.instruction}")
        
        # 2. 祖先链摘要 (Path to Root)
        # 这里简化处理：只取父节点的摘要
        if active_node.parent_id:
            parent = state.node_map.get(active_node.parent_id)
            if parent and parent.semantic_summary:
                context.append(f"Parent Context: {parent.semantic_summary}")

        # 3. 当前节点的执行状态
        context.append(f"Current Task ({active_node.level}): {active_node.instruction}")
        
        # 4. 局部历史 (Local History) - 只看当前任务的
        # 如果是子叶节点，展示最近几条执行记录
        recent_history = active_node.local_history[-5:] # 只看最后 5 条
        if recent_history:
            context.append("Recent Local History:")
            for h in recent_history:
                role = h.get('role', 'unknown')
                text = h.get('parts', [{}])[0].get('text', '')[:200]
                context.append(f" - {role}: {text}...")
        
        # 5. 用户干预
        if state.user_feedback_queue:
            context.append(f"URGENT USER FEEDBACK: {state.user_feedback_queue}")

        return "\n".join(context)

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        project_state = state.get("project_state")
        if not project_state: return {}

        print(f"\n⚙️ [Orchestrator] ReAct Loop Start (Active Node: {project_state.active_node_id[-4:]})")
        
        # 1. 构建动态上下文
        dynamic_context = self._get_dynamic_context(project_state)
        
        # 2. 获取工具定义
        tool_schemas = ToolRegistry.get_all_tool_schemas()
        tool_desc_str = ToolRegistry.get_tool_description_str() # Fallback for text prompt

        # 3. 构造 Prompt
        final_prompt = f"""
        Analyze the current state and decide the next move.
        
        === CONTEXT ===
        {dynamic_context}
        ================
        
        === AVAILABLE TOOLS ===
        {tool_desc_str}
        =======================
        
        === AVAILABLE AGENTS ===
        - researcher: Fact checking, docs.
        - coding_crew: Python coding & execution.
        - data_crew: Data analysis reports.
        - content_crew: Creative writing.
        
        Output a JSON object following the SupervisorDecision schema.
        """
        
        # 4. 调用 LLM
        try:
            response = self.rotator.call_gemini_with_rotation(
                model_name=self.model,
                contents=[{"role": "user", "parts": [{"text": final_prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=SupervisorDecision
            )
            
            if response:
                cleaned = response.replace("```json", "").replace("```", "").strip()
                decision = SupervisorDecision.model_validate_json(cleaned)
                
                print(f"   🧠 Thought: {decision.thought}")
                print(f"   ⚡️ Action: {decision.action_type.upper()}")

                # 映射到 ProjectState (兼容层)
                # 注意：实际的 Tool Execution 逻辑通常在主图 (Graph) 的条件边里处理，
                # 或者在这里直接修改 state 的 next_step 指向特定的 Tool Node。
                
                if decision.action_type == "finish_task":
                    project_state.router_decision = "finish"
                    project_state.final_report = decision.instruction
                    # 更新节点状态
                    if project_state.get_active_node():
                        project_state.get_active_node().status = TaskStatus.COMPLETED

                elif decision.action_type == "delegate_to_crew":
                    project_state.router_decision = "continue"
                    project_state.next_step = {
                        "agent_name": decision.delegate_target,
                        "instruction": decision.instruction
                    }

                elif decision.action_type == "call_tool":
                    # 标记下一步为 System Tool Execution
                    project_state.router_decision = "tool" 
                    project_state.next_step = {
                        "tool_name": decision.tool_call.tool_name,
                        "tool_params": decision.tool_call.tool_params
                    }

                elif decision.action_type == "ask_human":
                    project_state.router_decision = "human"
                    # 将问题推给前端 (此处略去具体实现，通常是更新 state 的某个字段等待中断)
                
                # 清理用户反馈队列，因为已经处理了
                project_state.user_feedback_queue = None
                
            else:
                raise ValueError("Empty response from Orchestrator")

        except Exception as e:
            print(f"❌ [Orchestrator] ReAct Failed: {e}")
            project_state.last_error = str(e)
            project_state.router_decision = "human" # 降级为人工干预

        return {"project_state": project_state}
