import os

def load_prompt(base_path: str, filename: str) -> str:
    """
    通用 Prompt 文件加载工具。
    遵循 DRY (Don't Repeat Yourself) 原则，统一处理文件读取和异常。
    """
    path = os.path.join(base_path, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"⚠️ Warning: Prompt file {path} not found.")
        return ""
