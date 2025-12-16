import sys
import random
import asyncio
import base64
import os
from typing import Tuple, Optional
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

# 加载环境变量
load_dotenv()

# 导入配置
from config.keys import GEMINI_API_KEYS, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME

# 导入核心模块
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# 导入工作流构建器
from workflow.graph import build_agent_workflow

def get_user_input() -> Tuple[str, Optional[str]]:
    """交互式获取用户输入 (支持图片)"""
    print("\n" + "="*50)
    print("🤖 Gemini Multi-Agent Swarm System (HITL Mode)")
    print("="*50)
    print("Please enter your complex task (e.g., 'Analyze this UI design'):")
    task = input(">>> Task: ").strip()
    if not task:
        print("❌ Empty input. Exiting.")
        sys.exit(0)
        
    print("Enter image path (optional, press Enter to skip):")
    img_path = input(">>> Image Path: ").strip()
    
    encoded_image = None
    if img_path:
        # 去除可能存在的引号
        img_path = img_path.strip('"').strip("'")
        if os.path.exists(img_path):
            try:
                with open(img_path, "rb") as image_file:
                    encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                print(f"🖼️ Image loaded successfully.")
            except Exception as e:
                print(f"⚠️ Failed to load image: {e}")
        else:
            print(f"⚠️ File not found: {img_path}")
            
    return task, encoded_image

async def main():
    # 1. 基础检查
    if not GEMINI_API_KEYS:
        print("❌ Error: GEMINI_API_KEYS not found in .env")
        return

    # 2. 初始化工具链
    print("\n🔧 Initializing Toolchain...")
    rotator = GeminiKeyRotator(GEMINI_API_KEYS)
    memory = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
    search = GoogleSearchTool()
    
    # 初始化持久化存储
    checkpointer = MemorySaver()

    # 3. 构建图 (Agent Workflow)
    print("🕸️ Building Agent Graph...")
    app = build_agent_workflow(rotator, memory, search, checkpointer=checkpointer)

    # 4. 准备初始状态
    initial_task, initial_image = get_user_input()
    
    # 构建初始消息 parts
    user_parts = [{"text": initial_task}]
    if initial_image:
        user_parts.append({"text": "[Image Uploaded]"})

    project_state = ProjectState(
        task_id=f"TASK-{random.randint(1000, 9999)}",
        user_input=initial_task,
        image_data=initial_image, # 存入状态
        full_chat_history=[{"role": "user", "parts": user_parts}]
    )
    
    # 配置 Thread ID 以支持状态持久化和中断恢复
    thread_id = "1"
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"\n🚀 Starting Workflow for Task: {project_state.task_id} (Thread: {thread_id})")
    
    # 初始输入
    current_input = {"project_state": project_state}

    # 5. 运行主循环 (Handling Interrupts & Resume)
    while True:
        try:
            # A. 执行工作流 (直到结束或遇到中断点)
            # 注意：传入 None 作为 input 意味着从当前状态继续 (Resume)
            # 只有第一次循环或需要注入新状态时才传入 current_input
            async for step in app.astream(current_input, config=config):
                for node_name, node_state in step.items():
                    print(f"--- Node Finished: {node_name} ---")
                    if 'project_state' in node_state:
                        # 简单的实时反馈打印
                        ps = node_state['project_state']
                        if ps.router_decision == "continue" and ps.next_step:
                             print(f"   🔮 Planned Next: {ps.next_step.get('agent_name')} -> {ps.next_step.get('instruction')[:50]}...")

            # B. 检查执行状态
            snapshot = app.get_state(config)
            
            # 如果没有下一步，说明流程自然结束
            if not snapshot.next:
                print("\n✅ Workflow Completed.")
                # 打印最终结果
                final_state = snapshot.values.get('project_state')
                if final_state and final_state.final_report:
                    print("\n📄 [FINAL REPORT]:")
                    print(final_state.final_report)
                break
            
            # C. 处理中断 (HITL Interaction)
            # 代码运行到这里意味着碰到了 interrupt_before
            print(f"\n⏸️ [HITL] Workflow Paused before: {snapshot.next}")
            
            # 获取当前上下文以便展示
            current_ps = snapshot.values['project_state']
            if current_ps.next_step:
                print(f"   👉 Pending Action: {current_ps.next_step.get('agent_name')}")
                print(f"   📝 Instruction: {current_ps.next_step.get('instruction')}")
            
            print("\nOptions: [A]pprove (Execute), [F]eedback (Edit Instruction), [Q]uit")
            user_choice = input(">>> ").strip().lower()
            
            if user_choice == 'a':
                # Approve: 继续执行
                print("👍 Approved. Resuming...")
                current_input = None 
            
            elif user_choice == 'f':
                # Feedback: 修改状态 (Time Travel)
                new_instruction = input("✏️  Enter new instruction (leave empty to keep current): ").strip()
                new_feedback = input("💬 Enter feedback context (optional): ").strip()
                
                if new_instruction:
                    current_ps.next_step['instruction'] = new_instruction
                    print("✅ Instruction updated.")
                
                if new_feedback:
                    current_ps.user_feedback_queue = f"User Intervention: {new_feedback}"
                    print("✅ Feedback queued.")
                
                # 更新图状态
                print("⏳ Updating State...")
                app.update_state(config, {"project_state": current_ps})
                
                # 准备 Resume
                print("🔄 Resuming with updated state...")
                current_input = None 
                
            else:
                print("🛑 User stopped execution.")
                break

        except Exception as e:
            print(f"\n💥 Runtime Error: {e}")
            import traceback
            traceback.print_exc()
            break

if __name__ == "__main__":
    asyncio.run(main())
