import sys
import random
import asyncio
import base64
import os
import json
import time  # 新增: 用于生成时间戳
import re    # 新增: 用于处理文件名中的非法字符
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
    """交互式获取用户输入 (支持图片路径)"""
    print("\n" + "="*50)
    print("🤖 Gemini Multi-Agent Swarm System (HITL Mode)")
    print("="*50)
    print("请输入您的复杂任务 (例如: '分析这张图表的趋势'):")
    task = input(">>> 任务描述: ").strip()
    if not task:
        print("❌ 输入为空，退出程序。")
        sys.exit(0)
        
    print("请输入图片路径 (可选，直接回车跳过):")
    img_path = input(">>> 图片路径: ").strip()
    
    encoded_image = None
    if img_path:
        # 去除可能存在的引号
        img_path = img_path.strip('"').strip("'")
        if os.path.exists(img_path):
            try:
                with open(img_path, "rb") as image_file:
                    encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                print(f"🖼️ 图片加载成功: {os.path.basename(img_path)}")
            except Exception as e:
                print(f"⚠️ 图片加载失败: {e}")
        else:
            print(f"⚠️ 文件未找到: {img_path}")
            
    return task, encoded_image

def save_output_images(folder_name: str, image_artifacts: list):
    """保存生成的图片到 D 盘指定目录"""
    if not image_artifacts:
        return
        
    # [修改点 1] 设置你的 D 盘目标根目录
    # 注意：Windows 路径前加 r 可以防止转义字符报错
    base_save_path = r"D:\SwarmTasks" 
    
    # 拼接完整的保存路径，例如: D:\SwarmTasks\20231027-1030_分析图表任务
    output_dir = os.path.join(base_save_path, folder_name)
    
    # 如果目录不存在则创建
    os.makedirs(output_dir, exist_ok=True)
    
    for img in image_artifacts:
        filename = img.get('filename', 'unknown.png')
        b64_data = img.get('data', '')
        if b64_data:
            try:
                file_path = os.path.join(output_dir, filename)
                with open(file_path, "wb") as f:
                    f.write(base64.b64decode(b64_data))
                print(f"💾 [Output] 图片已保存到 D 盘: {file_path}")
            except Exception as e:
                print(f"⚠️ 保存图片失败 {filename}: {e}")

async def main():
    # 1. 基础检查
    if not GEMINI_API_KEYS:
        print("❌ 错误: .env 中未找到 GEMINI_API_KEYS")
        return

    # 2. 初始化工具链
    print("\n🔧 正在初始化工具链...")
    rotator = GeminiKeyRotator(GEMINI_API_KEYS) # 注意：这里假设 Rotator 初始化参数已适配
    memory = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
    search = GoogleSearchTool()
    
    # 初始化持久化存储
    checkpointer = MemorySaver()

    # 3. 构建图 (Agent Workflow)
    print("🕸️ 正在构建 Agent 工作流图...")
    app = build_agent_workflow(rotator, memory, search, checkpointer=checkpointer)

    # 4. 准备初始状态
    initial_task, initial_image = get_user_input()
    
    # [修改点 2] 生成更有意义的文件夹名 (Task ID)
    # 获取当前时间，格式如: 20231027-1030
    timestamp = time.strftime("%Y%m%d-%H%M")
    
    # 提取任务描述的前10个字作为文件名的一部分，去掉特殊字符防止路径报错
    safe_task_name = re.sub(r'[\\/*?:"<>|]', "", initial_task)[:10]
    if not safe_task_name:
        safe_task_name = "未命名任务"
        
    # 组合成新的 ID: 20231027-1030_分析这张图表
    task_folder_name = f"{timestamp}_{safe_task_name}"
    
    # 构建初始消息 parts
    user_parts = [{"text": initial_task}]
    
    project_state = ProjectState(
        task_id=task_folder_name, # 使用生成的文件夹名作为 task_id
        user_input=initial_task,
        image_data=initial_image, # 存入状态
        full_chat_history=[{"role": "user", "parts": user_parts}]
    )
    
    # 配置 Thread ID 以支持状态持久化和中断恢复
    thread_id = "1"
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"\n🚀 开始执行任务: {project_state.task_id} (Thread: {thread_id})")
    
    # 初始输入
    current_input = {"project_state": project_state}

    # 5. 运行主循环 (Handling Interrupts & Resume)
    while True:
        try:
            # A. 执行工作流 (直到结束或遇到中断点)
            # stream_mode="values" 可以获取每一步的状态快照
            async for event in app.astream(current_input, config=config, stream_mode="values"):
                if 'project_state' not in event: continue
                ps = event['project_state']
                
                # 实时反馈决策
                if ps.next_step:
                     print(f"   🔮 [Plan] 下一步: {ps.next_step.get('agent_name')} -> {ps.next_step.get('instruction')[:50]}...")

                # 检查是否有新生成的图片产物并保存
                if ps.artifacts.get("images"):
                    save_output_images(ps.task_id, ps.artifacts["images"])
                    # 清空以防重复保存（可选，视逻辑而定）
                    # ps.artifacts["images"] = [] 

            # B. 检查执行状态
            snapshot = app.get_state(config)
            
            # 如果没有下一步，说明流程自然结束
            if not snapshot.next:
                print("\n✅ 工作流执行完毕。")
                # 打印最终结果
                final_state = snapshot.values.get('project_state')
                if final_state:
                    if final_state.final_report:
                        print("\n📄 [最终报告]:")
                        print(final_state.final_report)
                    
                    # 再次检查是否有遗漏的图片需要保存
                    if final_state.artifacts.get("images"):
                        save_output_images(final_state.task_id, final_state.artifacts["images"])
                break
            
            # C. 处理中断 (HITL Interaction)
            print(f"\n⏸️ [HITL] 工作流在 [{snapshot.next[0]}] 前暂停")
            
            # 获取当前上下文以便展示
            current_ps = snapshot.values['project_state']
            if current_ps.next_step:
                print(f"   👉 待执行动作: {current_ps.next_step.get('agent_name')}")
                print(f"   📝 指令内容: {current_ps.next_step.get('instruction')}")
            
            print("\n选项: [A]pprove (批准执行), [F]eedback (修改指令/反馈), [Q]uit (退出)")
            user_choice = input(">>> 请选择: ").strip().lower()
            
            if user_choice == 'a':
                print("👍 已批准。继续执行...")
                current_input = None # Resume
            
            elif user_choice == 'f':
                new_instruction = input("✏️  输入新指令 (回车保持原样): ").strip()
                new_feedback = input("💬 输入反馈上下文 (可选): ").strip()
                
                # [New] 支持在中断时补充图片
                new_img_path = input("🖼️  补充图片路径 (可选): ").strip()
                
                if new_instruction:
                    current_ps.next_step['instruction'] = new_instruction
                    print("✅ 指令已更新。")
                
                if new_feedback:
                    current_ps.user_feedback_queue = f"用户干预: {new_feedback}"
                    print("✅ 反馈已加入队列。")
                    
                if new_img_path:
                    new_img_path = new_img_path.strip('"').strip("'")
                    if os.path.exists(new_img_path):
                         with open(new_img_path, "rb") as f:
                             # 更新状态中的图片数据，这会覆盖之前的图片
                             # 如果支持多图，需要改为列表
                             current_ps.image_data = base64.b64encode(f.read()).decode('utf-8')
                         print("✅ 新图片已加载。")

                # 更新图状态
                print("⏳ 正在更新状态...")
                app.update_state(config, {"project_state": current_ps})
                
                print("🔄 携带更新后的状态继续...")
                current_input = None 
                
            else:
                print("🛑 用户停止了任务。")
                break

        except Exception as e:
            print(f"\n💥 运行时错误: {e}")
            import traceback
            traceback.print_exc()
            break

if __name__ == "__main__":
    asyncio.run(main())
