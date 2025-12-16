import random
from typing import List, Optional, Dict, Any
from google import genai
from google.genai.errors import APIError
from pydantic import BaseModel
from core.models import ExecutionPlan # 导入调度器输出的 Schema

# =======================================================
# Gemini API 轮询池 (GeminiKeyRotator)
# =======================================================

class GeminiKeyRotator:
    """
    负责管理和轮换 Gemini API Keys 的类。
    在 API 调用失败时，自动切换到下一个 Key，以确保系统的稳定性。
    """
    def __init__(self, api_keys: List[str]):
        if not api_keys:
            raise ValueError("API Key 列表不能为空！")
        
        valid_keys = [k.strip() for k in api_keys if k.strip().startswith("AIzaSy")]
        if not valid_keys:
             raise ValueError("API Key 列表中没有找到有效的 Gemini Key。")
        
        random.shuffle(valid_keys)
        self.keys = valid_keys
        self.current_key_index = 0
        self.max_retries = len(self.keys) 

    def get_client(self) -> genai.Client:
        """返回使用当前 Key 初始化的 Gemini 客户端对象。"""
        current_key = self.keys[self.current_key_index]
        return genai.Client(api_key=current_key)

    def rotate_key(self):
        """切换到列表中的下一个 Key。"""
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)
        print(f"🔑 Key 轮换成功！正在使用列表中的第 {self.current_key_index + 1} 个 Key。")

    def call_gemini_with_rotation(self, model_name: str, contents: List, system_instruction: str, response_schema: Optional[BaseModel] = None) -> Optional[str]:
        """
        封装了 API 调用的核心方法，包含自动轮询逻辑。
        支持结构化 JSON 输出 (通过 response_schema)。
        """
        for _ in range(self.max_retries):
            try:
                client = self.get_client()
                
                config_params = {"system_instruction": system_instruction}
                if response_schema:
                    config_params["response_mime_type"] = "application/json"
                    config_params["response_schema"] = response_schema
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config_params
                )
                return response.text

            except APIError as e:
                # 捕获 API Key 错误、限速错误等
                print(f"❌ 当前 Key 调用失败: {e}. 正在尝试切换 Key...")
                self.rotate_key()

            except Exception as e:
                # 捕获其他网络或未知错误
                print(f"❌ 发生未知错误: {e}")
                self.rotate_key()
        
        print("🚨 警告：所有 API Key 均已尝试失败。任务中止。")
        return None
