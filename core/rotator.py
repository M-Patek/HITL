import time
import random
import logging
import requests
from typing import List, Dict, Any, Optional, Literal
from config.keys import TIER_1_FAST, TIER_2_PRO

logger = logging.getLogger("GeminiRotator")

class GeminiKeyRotator:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def check_gateway_health(self) -> str:
        """
        [Fix] 检查网关或 API Key 是否可用
        """
        if not self.api_key:
            return "misconfigured_no_key"
        
        # 简单做一次轻量级请求 (列出模型) 来验证连接
        # 这里使用 REST API 方式，避免依赖 SDK 版本
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return "connected"
            else:
                return f"error_{resp.status_code}"
        except Exception:
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
        """
        # [Phase 3] Cache Hit Check
        # 只针对 complex 任务或 standard query 启用缓存，避免简单指令(如json formatting)误命中
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
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={self.api_key}"
        
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

        # Retry Logic
        retries = 3
        for attempt in range(retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        if parts:
                            text_resp = parts[0].get("text", "")
                            
                            # [Phase 3] Write Back to Cache (Optional)
                            # 可以在这里做，也可以在业务层做。这里为了通用性暂不自动写入。
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
