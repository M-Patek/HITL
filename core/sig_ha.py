import hashlib
import secrets
import time
from typing import Tuple, List, Dict, Any

# -------------------------------------------------------------------------
# SIG-HA: Holographic Accumulator for Distributed Topology Steganography
# Pure Python Implementation adapted for HITL
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
    """
    
    def __init__(self):
        self.M = int(RFC_3526_PRIME_2048_HEX, 16)
        self.G = 4  # Generator
        self._prime_cache = {}

    def _is_prime_miller_rabin(self, n: int, k: int = 10) -> bool:
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
        try:
            prev_t = int(current_t_str)
        except (ValueError, TypeError):
            # Fallback for genesis
            prev_t = int(hashlib.sha256(b"GENESIS_SEED").hexdigest(), 16)

        p_agent = self.hash_to_prime(agent_id)
        
        # T_next = (T_prev ^ P_agent * G ^ H(depth)) mod M
        term1 = pow(prev_t, p_agent, self.M)
        h_depth = int(hashlib.sha256(str(current_depth).encode()).hexdigest(), 16)
        term2 = pow(self.G, h_depth, self.M)
        
        new_t = (term1 * term2) % self.M
        new_depth = current_depth + 1
        return str(new_t), new_depth

    def update_trace_in_state(self, state_obj: Any, agent_name: str) -> None:
        """
        统一处理 Dict 或 Pydantic 模型的签名更新。
        state_obj 可能是 Pydantic Model (ProjectState) 也可能是 TypedDict (CodingCrewState)。
        """
        # 判断是否为 Pydantic 对象
        is_pydantic = hasattr(state_obj, 'model_dump') or (hasattr(state_obj, 'trace_t') and not isinstance(state_obj, dict))
        
        # 提取当前状态
        if is_pydantic:
            current_t = getattr(state_obj, 'trace_t', "0")
            current_depth = getattr(state_obj, 'trace_depth', 0)
            history = getattr(state_obj, 'trace_history', [])
        else:
            current_t = state_obj.get('trace_t', "0")
            current_depth = state_obj.get('trace_depth', 0)
            history = state_obj.get('trace_history', [])
        
        if history is None: history = []

        # 计算新签名
        new_t, new_depth = self.evolve_state(current_t, agent_name, current_depth)
        
        entry = {
            "depth": new_depth,
            "agent": agent_name,
            "t_fingerprint": new_t[:16] + "...",
            "timestamp": time.time()
        }
        # Copy history to avoid reference issues
        new_history = list(history) + [entry]

        # 写回状态
        if is_pydantic:
            setattr(state_obj, 'trace_t', new_t)
            setattr(state_obj, 'trace_depth', new_depth)
            setattr(state_obj, 'trace_history', new_history)
        else:
            state_obj['trace_t'] = new_t
            state_obj['trace_depth'] = new_depth
            state_obj['trace_history'] = new_history

sig_ha = SigHAManager()
