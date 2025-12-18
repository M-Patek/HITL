import json
import logging
import sys
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Optional, Dict

# [核心黑科技] ContextVars for Full-Link Tracing
trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
node_id_ctx: ContextVar[Optional[str]] = ContextVar("node_id", default=None)
phase_ctx: ContextVar[Optional[str]] = ContextVar("phase", default="UNKNOWN")

# [Protocol Phase 4] Token 计数器上下文
# 格式示例: {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
token_usage_ctx: ContextVar[Optional[Dict[str, int]]] = ContextVar("token_usage", default=None)

class JSONFormatter(logging.Formatter):
    """
    [OTel 风格] 结构化日志格式化器 (Cost Enhanced)
    """
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        
        # [自动注入] 从上下文获取 Trace ID, Node ID, Phase
        tid = trace_id_ctx.get()
        if tid: log_object["trace_id"] = tid
            
        nid = node_id_ctx.get()
        if nid: log_object["node_id"] = nid
        
        phase = phase_ctx.get()
        if phase: log_object["protocol_phase"] = phase

        # [Protocol Phase 4] Token 成本监控
        # 优先读取 logger.info(..., extra={'token_usage': ...}) 中的显式传值
        # 其次读取上下文中的累积值
        token_data = getattr(record, "token_usage", None)
        if not token_data:
            token_data = token_usage_ctx.get()
            
        if token_data:
            log_object["token_usage"] = token_data

        # 支持 extra={"extra_data": {...}}
        if hasattr(record, "extra_data"):
             log_object.update(record.extra_data)

        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_object, ensure_ascii=False)

def setup_logging(service_name: str = "SWARM-Brain"):
    root = logging.getLogger()
    root.handlers.clear()
    
    # 输出到 stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service_name))
    
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    
    # 屏蔽噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
