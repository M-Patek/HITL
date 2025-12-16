import random
import time
from typing import List, Optional, Any
from google import genai
from google.genai.errors import APIError
from pydantic import BaseModel

class GeminiKeyRotator:
    """
    Gemini API Key 轮询管理器。
    负责在多个 Key 之间负载均衡，并处理自动重试。
    """
    def __init__(self, api_keys: List[str]):
        if not api_keys:
            raise ValueError("❌ Init Error: API Key list cannot be empty.")
        
        # 简单的验证逻辑
        self.keys = [k.strip() for k in api_keys if k.strip()]
        if not self.keys:
             raise ValueError("❌ Init Error: No valid keys found.")
        
        random.shuffle(self.keys)
        self.current_key_index = 0
        self.max_retries = len(self.keys) * 2 # 允许每把钥匙失败两次

    def _get_client(self) -> genai.Client:
        """获取当前激活的客户端"""
        current_key = self.keys[self.current_key_index]
        return genai.Client(api_key=current_key)

    def _rotate(self):
        """切换到下一个 Key"""
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)
        print(f"🔄 Rotating API Key... (Index: {self.current_key_index})")

    def call_gemini_with_rotation(
        self, 
        model_name: str, 
        contents: List[Any], 
        system_instruction: str, 
        response_schema: Optional[Any] = None
    ) -> Optional[str]:
        """
        执行 API 调用，包含自动重试和 Key 轮换机制。
        """
        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                
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
                print(f"⚠️ API Error (Key Index {self.current_key_index}): {e}")
                self._rotate()
                time.sleep(1) # 简单的避让等待

            except Exception as e:
                print(f"❌ Unexpected Error: {e}")
                self._rotate()
        
        print("🚨 Critical: All API keys exhausted or max retries reached.")
        return None
