import json
import logging
import sys
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Optional

# [核心黑科技] ContextVar
# trace_id: 贯穿整个 HTTP 请求或任务生命周期
# node_id: 贯穿当前 TaskNode 的执行周期
trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
node_id_ctx: ContextVar[Optional[str]] = ContextVar("node_id", default=None)

class JSONFormatter(logging.Formatter):
    """
    [OTel 风格] 结构化日志格式化器
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
        
        # [自动注入] 从上下文获取 Trace ID 和 Node ID
        tid = trace_id_ctx.get()
        if tid:
            log_object["trace_id"] = tid
            
        nid = node_id_ctx.get()
        if nid:
            log_object["node_id"] = nid

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
