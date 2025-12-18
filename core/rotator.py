import time
import logging
import json
from typing import List, Optional, Any, Dict
import httpx
# [New] 引入上下文变量
from core.logger_setup import trace_id_ctx

logger = logging.getLogger("Brain-Rotator")

class GeminiKeyRotator:
    """
    大脑层请求代理。
    [Update] 支持全链路追踪透传与健康检查。
    """
    def __init__(self, gateway_url: str, gateway_secret: str):
        self.gateway_url = gateway_url.rstrip('/')
        self.gateway_secret = gateway_secret
        self.client = httpx.Client(
            timeout=httpx.Timeout(120.0, connect=5.0),
            limits=httpx.Limits(max_connections=50)
        )

    # [New] 主动健康检查接口
    def check_gateway_health(self) -> Dict[str, Any]:
        """
        调用 Gateway 的 /v1/pool/status 接口，确认链路通畅。
        """
        endpoint = f"{self.gateway_url}/v1/pool/status"
        headers = {
            "Authorization": f"Bearer {self.gateway_secret}",
            "X-Swarm-Node": "Brain-HealthCheck"
        }
        
        start = time.time()
        try:
            resp = self.client.get(endpoint, headers=headers, timeout=3.0)
            latency = (time.time() - start) * 1000
            
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "connected",
                    "latency_ms": round(latency, 2),
                    "gateway_version": data.get("version"),
                    "gateway_active_slots": data.get("active_slots", 0)
                }
            else:
                return {
                    "status": "error", 
                    "code": resp.status_code,
                    "msg": "Gateway refused connection"
                }
        except Exception as e:
            return {
                "status": "disconnected",
                "error": str(e),
                "tips": "请检查 Gateway 是否启动，或 GATEWAY_API_BASE 是否正确"
            }

    def call_gemini_with_rotation(
        self, 
        model_name: str, 
        contents: List[Any], 
        system_instruction: str, 
        response_schema: Optional[Any] = None
    ) -> Optional[str]:
        
        endpoint = f"{self.gateway_url}/v1/chat/completions"
        
        # [核心] 获取当前上下文的 Trace ID
        current_trace_id = trace_id_ctx.get() or "no-trace-id"

        headers = {
            "Authorization": f"Bearer {self.gateway_secret}",
            "Content-Type": "application/json",
            "X-Swarm-Node": "Brain-Rotator",
            
            # [核心] 注入 Trace ID，透传给 Gateway
            "X-Request-ID": current_trace_id 
        }
        
        # 记录调用日志
        logger.info("calling_gateway", extra={"extra_data": {
            "model": model_name, 
            "url": endpoint
        }})

        payload = {
            "model": model_name, # [New] 传给 Gateway 记录日志用
            "contents": contents,
            "system_instruction": {
                "role": "system",
                "parts": [{"text": system_instruction}]
            } if isinstance(system_instruction, str) else system_instruction,
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "maxOutputTokens": 4096
            }
        }

        if response_schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            if hasattr(response_schema, "model_json_schema"):
                payload["generationConfig"]["responseSchema"] = response_schema.model_json_schema()
            elif isinstance(response_schema, dict):
                payload["generationConfig"]["responseSchema"] = response_schema

        for attempt in range(3):
            try:
                resp = self.client.post(endpoint, headers=headers, json=payload)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    except:
                        return resp.text
                
                if resp.status_code == 429:
                    logger.warning(f"ratelimit_retry", extra={"extra_data": {"attempt": attempt+1}})
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"gateway_error", extra={"extra_data": {"code": resp.status_code, "body": resp.text}})
                    break

            except Exception as e:
                logger.error(f"connection_error", extra={"extra_data": {"error": str(e)}})
                time.sleep(1)
        
        return None

    def __del__(self):
        try: self.client.close()
        except: pass
