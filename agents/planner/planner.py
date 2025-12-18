from typing import List, Dict, Any
from pydantic import BaseModel, Field
from core.rotator import GeminiKeyRotator
from config.keys import GEMINI_MODEL_NAME

class PlanStep(BaseModel):
    step_id: int
    agent: str = Field(..., description="负责该步骤的 Agent: researcher, coding_crew, data_crew, content_crew")
    instruction: str = Field(..., description="具体的执行指令")
    dependency: int = Field(0, description="依赖的前置步骤 ID，0 表示无依赖")

class ProjectPlan(BaseModel):
    goal: str
    steps: List[PlanStep]
    reasoning: str

class PlannerAgent:
    """
    [SWARM 3.0] Strategic Planner
    在任务开始时生成全局执行计划 (Chain of Thought)。
    """
    def __init__(self, rotator: GeminiKeyRotator):
        self.rotator = rotator
        self.model = GEMINI_MODEL_NAME

    def create_plan(self, user_input: str) -> Dict[str, Any]:
        print(f"\n🗺️ [Planner] 正在制定全局战略计划...")
        
        prompt = f"""
        You are a Strategic Planner for an AI Agent Swarm.
        Break down the following user task into a logical sequence of steps.
        
        Available Agents:
        - researcher: Search for information, API docs, or facts.
        - coding_crew: Write and execute Python code (plotting, calculation, scraping).
        - data_crew: Analyze data and generate business reports.
        - content_crew: Write articles or copy.

        User Task: {user_input}
        
        Output a structured JSON plan.
        """
        
        try:
            response = self.rotator.call_gemini_with_rotation(
                model_name=self.model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction="You are a strict planner. Output JSON only.",
                response_schema=ProjectPlan
            )
            
            if response:
                plan = ProjectPlan.model_validate_json(response.replace("```json", "").replace("```", "").strip())
                print(f"   📝 计划生成完毕，共 {len(plan.steps)} 步。")
                print(f"   🔍 核心思路: {plan.reasoning}")
                for step in plan.steps:
                    print(f"      [{step.step_id}] {step.agent}: {step.instruction[:40]}...")
                
                return plan.model_dump()
            
        except Exception as e:
            print(f"❌ [Planner] Planning failed: {e}")
            return {}
        
        return {}
