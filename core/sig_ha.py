import hashlib
import secrets
import time
from typing import Tuple, List, Dict, Any

# -------------------------------------------------------------------------
# SIG-HA: Holographic Accumulator for Distributed Topology Steganography
# Pure Python Implementation adapted for HITL
# Independent Module: No internal project dependencies to prevent cycles.
# -------------------------------------------------------------------------

# RFC 3526 - 2048-bit MODP Group (Safe Prime)
RFC_3526_PRIME_2048_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA237327FFFFFFFFFFFFFFFF"
)

class SigHAManager:
    """
    SIG-HA 全息溯源管理器 (Pure Python Version)
    负责管理 Agent 身份映射、状态演化和全息指纹计算。
    此模块设计为零依赖，可被任何层级调用。
    """
    
    def __init__(self):
        self.M = int(RFC_3526_PRIME_2048_HEX, 16)
        self.G = 4  # Generator
        self._prime_cache: Dict[str, int] = {}

    def _is_prime_miller_rabin(self, n: int, k: int = 10) -> bool:
        """Miller-Rabin 素数检测算法"""
        if n == 2 or n == 3: return True
        if n % 2 == 0: return False

        r, s = 0, n - 1
        while s % 2 == 0:
            r += 1
            s //= 2
            
        for _ in range(k):
            a = secrets.randbelow(n - 4) + 2
            x = pow(a, s, n)
            if x == 1 or x == n - 1:
                continue
            for _ in range(r - 1):
                x = pow(x, 2, n)
                if x == n - 1:
                    break
            else:
                return False
        return True

    def hash_to_prime(self, agent_id: str) -> int:
        """将 Agent ID 确定性地映射到一个素数"""
        if agent_id in self._prime_cache:
            return self._prime_cache[agent_id]

        h = hashlib.sha256(agent_id.encode()).hexdigest()
        candidate = int(h, 16)
        if candidate % 2 == 0: candidate += 1
            
        while True:
            if self._is_prime_miller_rabin(candidate):
                self._prime_cache[agent_id] = candidate
                return candidate
            candidate += 2

    def evolve_state(self, current_t_str: str, agent_id: str, current_depth: int) -> Tuple[str, int]:
        """
        计算下一个状态指纹
        T_next = (T_prev ^ P_agent * G ^ H(depth)) mod M
        """
        try:
            prev_t = int(current_t_str)
        except (ValueError, TypeError):
            # Fallback for genesis or malformed state
            prev_t = int(hashlib.sha256(b"GENESIS_SEED").hexdigest(), 16)

        p_agent = self.hash_to_prime(agent_id)
        
        term1 = pow(prev_t, p_agent, self.M)
        h_depth = int(hashlib.sha256(str(current_depth).encode()).hexdigest(), 16)
        term2 = pow(self.G, h_depth, self.M)
        
        new_t = (term1 * term2) % self.M
        new_depth = current_depth + 1
        return str(new_t), new_depth

    def update_trace_in_state(self, state_obj: Any, agent_name: str) -> None:
        """
        统一处理 Dict 或 Pydantic 模型的签名更新。
        通过反射机制解耦对具体 Model 类的依赖。
        
        Args:
            state_obj: ProjectState 对象 (Pydantic) 或 TypedDict (Dict)
            agent_name: 当前执行操作的 Agent 名称
        """
        # 动态判断是否为 Pydantic 对象 (兼容 v1/v2)
        # 只要不是 dict 且具有 trace_t 属性，或具有 model_dump 方法，就视为对象操作
        is_pydantic = (not isinstance(state_obj, dict)) and (
            hasattr(state_obj, 'model_dump') or hasattr(state_obj, 'trace_t')
        )
        
        # 1. 提取当前状态
        if is_pydantic:
            current_t = getattr(state_obj, 'trace_t', "0")
            current_depth = getattr(state_obj, 'trace_depth', 0)
            # Pydantic 可能会返回 None，需要防御性处理
            history = getattr(state_obj, 'trace_history', [])
        else:
            current_t = state_obj.get('trace_t', "0")
            current_depth = state_obj.get('trace_depth', 0)
            history = state_obj.get('trace_history', [])
        
        if history is None: 
            history = []

        # 2. 计算新签名
        new_t, new_depth = self.evolve_state(current_t, agent_name, current_depth)
        
        entry = {
            "depth": new_depth,
            "agent": agent_name,
            "t_fingerprint": new_t[:16] + "...", # 只存储前缀以便于阅读
            "timestamp": time.time()
        }
        
        # 3. 更新历史 (Copy to avoid mutation issues in some frameworks)
        new_history = list(history) + [entry]

        # 4. 写回状态
        if is_pydantic:
            setattr(state_obj, 'trace_t', new_t)
            setattr(state_obj, 'trace_depth', new_depth)
            setattr(state_obj, 'trace_history', new_history)
        else:
            state_obj['trace_t'] = new_t
            state_obj['trace_depth'] = new_depth
            state_obj['trace_history'] = new_history

# 全局单例
sig_ha = SigHAManager()
