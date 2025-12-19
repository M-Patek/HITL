import hashlib
import secrets
import time
from typing import Tuple, List, Dict, Any

# -------------------------------------------------------------------------
# SIG-HA: Holographic Accumulator for Distributed Topology Steganography
# Pure Python Implementation adapted for HITL
# -------------------------------------------------------------------------

# RFC 3526 - 2048-bit MODP Group (Safe Prime)
# 这是一个标准的 Diffie-Hellman 安全大素数，足以满足演示和生产级的安全需求。
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
        # 初始化加密上下文
        self.M = int(RFC_3526_PRIME_2048_HEX, 16)
        self.G = 4  # Generator (Quadratic Residue)
        self._prime_cache = {}

    def _is_prime_miller_rabin(self, n: int, k: int = 10) -> bool:
        """
        Miller-Rabin 素性测试
        """
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
        """
        Phi (Φ) Operator: Identity Mapper
        将 Agent ID 映射为唯一的安全大素数。
        """
        if agent_id in self._prime_cache:
            return self._prime_cache[agent_id]

        # Step 1: SHA256 Hash
        h = hashlib.sha256(agent_id.encode()).hexdigest()
        candidate = int(h, 16)
        
        # Step 2: Ensure Odd
        if candidate % 2 == 0:
            candidate += 1
            
        # Step 3: Increment until Prime (Deterministic for same seed usually, 
        # but here we just need a prime associated with the ID roughly)
        # Note: In strict SIG-HA, this should be deterministic. 
        # Here we scan forward.
        while True:
            if self._is_prime_miller_rabin(candidate):
                self._prime_cache[agent_id] = candidate
                return candidate
            candidate += 2

    def evolve_state(self, current_t_str: str, agent_id: str, current_depth: int) -> Tuple[str, int]:
        """
        Omega (Ω) Operator: Evolution
        T_next = (T_prev ^ P_agent * G ^ H(depth)) mod M
        """
        # Parse inputs
        try:
            prev_t = int(current_t_str)
        except (ValueError, TypeError):
            # Fallback for genesis or error state
            prev_t = int(hashlib.sha256(b"GENESIS_SEED").hexdigest(), 16)

        p_agent = self.hash_to_prime(agent_id)
        
        # Term 1: Identity Influence -> T ^ P (mod M)
        term1 = pow(prev_t, p_agent, self.M)
        
        # Term 2: Topological Influence -> G ^ H(depth) (mod M)
        # Hash depth to add entropy
        h_depth = int(hashlib.sha256(str(current_depth).encode()).hexdigest(), 16)
        term2 = pow(self.G, h_depth, self.M)
        
        # Combine
        new_t = (term1 * term2) % self.M
        new_depth = current_depth + 1
        
        return str(new_t), new_depth

    def update_trace_in_state(self, state_dict: Dict[str, Any], agent_name: str) -> None:
        """
        Helper to update a state dictionary (or Pydantic model dump) in-place.
        Used within LangGraph nodes.
        """
        # Extract current trace info
        # Check if it's a dict or object (Pydantic)
        is_pydantic = not isinstance(state_dict, dict)
        
        if is_pydantic:
            current_t = getattr(state_dict, 'trace_t', "0")
            current_depth = getattr(state_dict, 'trace_depth', 0)
            history = getattr(state_dict, 'trace_history', [])
        else:
            current_t = state_dict.get('trace_t', "0")
            current_depth = state_dict.get('trace_depth', 0)
            history = state_dict.get('trace_history', [])
            if history is None: history = []

        # Evolve
        new_t, new_depth = self.evolve_state(current_t, agent_name, current_depth)
        
        # Log
        entry = {
            "depth": new_depth,
            "agent": agent_name,
            "t_fingerprint": new_t[:32] + "...", # Log shortened version for readability
            "timestamp": time.time()
        }
        # In a real immutable ledger, we wouldn't just append to list, 
        # but this is for HITL visualization.
        new_history = history + [entry]

        # Apply back
        if is_pydantic:
            setattr(state_dict, 'trace_t', new_t)
            setattr(state_dict, 'trace_depth', new_depth)
            setattr(state_dict, 'trace_history', new_history)
        else:
            state_dict['trace_t'] = new_t
            state_dict['trace_depth'] = new_depth
            state_dict['trace_history'] = new_history

# Global Singleton
sig_ha = SigHAManager()
