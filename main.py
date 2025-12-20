import sys
import asyncio
import base64
import os
import time
import re
from datetime import datetime
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

# 全局控制事件
running_event = asyncio.Event()
running_event.set()

def get_user_input() -> Tuple[str, Optional[str]]:
    """交互式获取初始用户输入"""
    print("\n" + "="*50)
    print("🤖 HITL 自动驾驶系统 (双线程实时干预版)")
    print("="*50)
    print("请输入您的初始任务:")
    task = input(">>> 任务描述: ").strip()
    if not task:
        print("❌ 输入为空，退出程序。")
        sys.exit(0)
    return task, None

async def input_listener(app, config):
    """
    🎧 上帝视角监听器
    支持命令：
    - timeline: 查看最近的操作记录（带时间戳）
    - log: 查看最近一次的详细输出
    - trace: 查看 SIG-HA 原始指纹（硬核溯源）
    - q: 退出
    - (其他任何文字): 视为即时干预指令，直接修改运行方向
    """
    print("\n🎧 [系统] 实时交互已就绪。")
    print("   输入 'timeline' 查看刚才发生了什么，或直接输入指令修改任务。")
    
    while running_event.is_set():
        # 异步等待输入，不阻塞主流程
        try:
            user_text = await asyncio.get_event_loop().run_in_executor(None, input)
            user_text = user_text.strip()
        except EOFError:
            break
        
        if not user_text: continue

        # === 1. 退出 ===
        if user_text.lower() in ['q', 'quit', 'exit']:
            print("🛑 [系统] 正在停止...")
            running_event.clear()
            break
            
        # === 2. 查时间线 (解决“刚才谁动了”的问题) ===
        elif user_text.lower() == 'timeline':
            snapshot = app.get_state(config)
            if snapshot and snapshot.values.get('project_state'):
                ps = snapshot.values['project_state']
                history = ps.trace_history[-15:] # 看最近15步
                print(f"\n🕒 [最近活动时间线] (当前时间: {datetime.now().strftime('%H:%M:%S')})")
                for item in history:
                    # 将时间戳转换为可读格式
                    ts = datetime.fromtimestamp(item['timestamp']).strftime('%H:%M:%S')
                    print(f"   ⏱️ {ts} | 👤 {item['agent'].ljust(15)} | 深度: {item['depth']}")
            else:
                print("⚠️ 暂无历史记录。")

        # === 3. 查详细日志 (查看具体内容) ===
        elif user_text.lower() == 'log':
            snapshot = app.get_state(config)
            if snapshot and snapshot.values.get('project_state'):
                ps = snapshot.values['project_state']
                # 尝试获取最近一个节点的输出
                active_node = ps.get_active_node()
                if active_node:
                    print(f"\n📄 [节点 {active_node.name} 的当前指令]:")
                    print(f"   {active_node.instruction}")
                    print(f"\n💬 [最近上下文摘要]:")
                    for msg in reversed(active_node.local_history):
                        if msg.get('role') != 'system':
                            content = msg.get('parts', [{}])[0].get('text', '')[:200]
                            print(f"   ({msg.get('role')}): {content}...")
                            break
            else:
                print("⚠️ 无法获取日志。")

        # === 4. 原始溯源 (SIG-HA) ===
        elif user_text.lower() == 'trace':
            snapshot = app.get_state(config)
            ps = snapshot.values.get('project_state') if snapshot else None
            if ps:
                print(f"\n🔐 [SIG-HA 实时签名] 当前指纹: {ps.trace_t[:30]}...")
            else:
                print("⚠️ 状态未初始化。")

        # === 5. 即时修改 (Intervention) ===
        else:
            print(f"⚡ [介入] 收到神谕: '{user_text}'")
            print("   正在强行注入任务流...")
            
            # 获取最新状态
            snapshot = app.get_state(config)
            current_ps = snapshot.values.get('project_state')
            
            if current_ps:
                # 关键点：我们将用户的输入放入 'user_feedback_queue'
                # Orchestrator 在下一次醒来时（甚至当前如果正好在做决定时）会读到这个字段
                current_ps.user_feedback_queue = f"⚠️ [USER INTERRUPT]: {user_text}"
                
                # 立即更新状态，不需要等待节点结束
                app.update_state(config, {"project_state": current_ps})
                print("✅ 指令注入成功！下个节点将执行您的变更。")

async def run_workflow_loop(app, config, initial_input):
    """主工作流循环"""
    print("🚀 任务自动驾驶模式已启动...")
    try:
        # stream_mode="values" 让我们可以看到每一步的变化
        async for event in app.astream(initial_input, config=config, stream_mode="values"):
            if not running_event.is_set(): 
                break
            
            if 'project_state' in event:
                ps = event['project_state']
                # 如果有新产生的计划，打印出来让用户知道进度
                if ps.next_step:
                    agent = ps.next_step.get('agent_name', 'Unknown')
                    instr = ps.next_step.get('instruction', '')[:30]
                    print(f"   🔄 [运行中] {agent} -> {instr}...")
                    
    except Exception as e:
        print(f"\n💥 工作流异常退出: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🏁 工作流结束。")
        running_event.clear()

async def main():
    # 1. 基础检查
    if not GEMINI_API_KEYS:
        print("❌ 错误: .env 中未找到 GEMINI_API_KEYS")
        return

    # 2. 初始化工具链
    print("\n🔧 正在初始化工具链...")
    rotator = GeminiKeyRotator(GEMINI_API_KEYS)
    memory = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
    search = GoogleSearchTool()
    
    # 初始化持久化存储
    checkpointer = MemorySaver()

    # 3. 构建图 (Agent Workflow)
    print("🕸️ 正在构建 Agent 工作流图...")
    # 注意：这里我们传入 checkpointer，让子图也能共享（如果我们在 build_agent_workflow 里处理好的话）
    app = build_agent_workflow(rotator, memory, search, checkpointer=checkpointer)

    # 4. 准备初始状态
    initial_task, _ = get_user_input()
    
    task_id = f"AutoTask_{int(time.time())}"
    user_parts = [{"text": initial_task}]
    
    project_state = ProjectState(
        task_id=task_id,
        user_input=initial_task,
        full_chat_history=[{"role": "user", "parts": user_parts}]
    )
    
    # 主线程 ID
    thread_id = "main_thread_1"
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"\n🚀 开始执行任务: {task_id}")
    
    initial_input = {"project_state": project_state}

    # 5. 双线程启动
    workflow_task = asyncio.create_task(run_workflow_loop(app, config, initial_input))
    listener_task = asyncio.create_task(input_listener(app, config))
    
    await asyncio.gather(workflow_task, listener_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bye!")
