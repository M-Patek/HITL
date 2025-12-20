import time
import random
import logging
import requests
from typing import List, Dict, Any, Optional, Literal
from config.keys import TIER_1_FAST, TIER_2_PRO

logger = logging.getLogger("GeminiRotator")

class GeminiKeyRotator:
    def __init__(self, base_url: str, api_key: str):
        # 移除末尾斜杠，防止拼接时出现双斜杠
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        
        # [Fix] 自动检测模式：如果 URL 中不包含 googleapis，则认为是我们的私有 RP 网关
        self.is_gateway = "googleapis.com" not in self.base_url

    def check_gateway_health(self) -> str:
        """
        [Fix] 智能健康检查，根据是否是 Gateway 决定检查逻辑
        """
        if not self.api_key:
            return "misconfigured_no_key"
        
        try:
            if self.is_gateway:
                # RP 模式：检查专用健康接口 /health
                # 注意：RP 的 health 不需要鉴权
                url = f"{self.base_url}/health"
                resp = requests.get(url, timeout=5)
                # RP 返回 {"status": "healthy"}
                if resp.status_code == 200:
                    return "connected"
                else:
                    return f"error_{resp.status_code}"
            else:
                # Google 模式：列出模型 (轻量级请求)
                url = f"{self.base_url}/models?key={self.api_key}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    return "connected"
                else:
                    return f"error_{resp.status_code}"
        except Exception as e:
            # 记录异常以便调试
            logger.debug(f"Health check failed: {str(e)}")
            return "disconnected"

    def _get_model_by_complexity(self, complexity: str) -> str:
        """根据复杂度路由到对应的模型 Tier"""
        if complexity == "simple":
            return TIER_1_FAST
        elif complexity == "complex":
            return TIER_2_PRO
        else:
            return TIER_2_PRO # Default safe

    def call_gemini_with_rotation(
        self,
        model_name: str,
        contents: List[Dict[str, Any]],
        system_instruction: str = "",
        response_schema: Optional[Any] = None,
        complexity: Literal["simple", "complex"] = "complex",
        semantic_cache_tool: Optional[Any] = None # [Phase 3] 注入缓存工具
    ) -> str:
        """
        调用 Gemini API，支持自动路由、重试和语义缓存。
        自动适配 Gateway (RP) 和 Google 原生 API。
        """
        # [Phase 3] Cache Hit Check
        if semantic_cache_tool and contents:
            try:
                # 提取用户 Query (简化逻辑: 取最后一个 user part)
                last_user_msg = ""
                for c in reversed(contents):
                    if c.get("role") == "user":
                        last_user_msg = c.get("parts", [{}])[0].get("text", "")
                        break
                
                if len(last_user_msg) > 10: # 太短的不查
                    cached_res = semantic_cache_tool.check_semantic_cache(last_user_msg)
                    if cached_res:
                        return cached_res
            except Exception as e:
                logger.warning(f"Cache check skipped due to error: {e}")

        # [Smart Routing]
        target_model = model_name
        if complexity:
            target_model = self._get_model_by_complexity(complexity)
            
        # --- [Fix] 构造请求 Payload ---
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7 if complexity == "complex" else 0.3, 
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        if response_schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            if hasattr(response_schema, "model_json_schema"):
                payload["generationConfig"]["responseSchema"] = response_schema.model_json_schema()
            elif isinstance(response_schema, dict):
                payload["generationConfig"]["responseSchema"] = response_schema

        # --- [Fix] 根据模式分叉 ---
        url = ""
        
        if self.is_gateway:
            # === Gateway (RP) 模式 ===
            # 1. 接口：固定指向 /v1/chat/completions (模拟 OpenAI 风格路径)
            url = f"{self.base_url}/v1/chat/completions"
            
            # 2. 鉴权：使用 Bearer Token 放在 Header 中
            headers["Authorization"] = f"Bearer {self.api_key}"
            
            # 3. 参数：模型名称必须放在 Body 中
            payload["model"] = target_model
            
        else:
            # === Google 原生模式 ===
            # 1. 接口：使用 Google 标准路径
            url = f"{self.base_url}/{target_model}:generateContent?key={self.api_key}"
            
            # 2. 鉴权：已包含在 URL query param 中
            # 3. 参数：模型名称已包含在 URL path 中
            pass

        # Retry Logic
        retries = 3
        for attempt in range(retries):
            try:
                # 使用 post 发送请求
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    data = response.json()
                    # 尝试解析标准 Gemini 响应格式
                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        if parts:
                            text_resp = parts[0].get("text", "")
                            return text_resp
                    return "" 
                
                elif response.status_code in [429, 500, 503]:
                    wait_time = 2 ** attempt
                    logger.warning(f"API Error {response.status_code}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"API Failed: {response.text}")
                    break
                    
            except Exception as e:
                logger.error(f"Request failed: {e}")
                time.sleep(1)
                
        return ""
