import docker
import time
import logging
from typing import Tuple, List, Optional, Dict

logger = logging.getLogger("Tools-Sandbox")

class DockerSandbox:
    """
    [Speculative Warming Enhanced]
    安全执行 Python 代码的沙箱环境。支持容器预热。
    """
    def __init__(self, image: str = "python:3.9-slim"):
        self.client = docker.from_env()
        self.image = image
        self.container_name = "swarm_sandbox_runner"
        self.container = None
        self._is_warming = False

    def warm_up(self):
        """
        [New] 预热容器
        在任务正式开始前调用，确保容器处于 Running 状态，减少首次执行延迟。
        """
        if self._is_warming:
            logger.info("🔥 Sandbox is already warming up...")
            return

        logger.info("🔥 [Speculative] Pre-warming sandbox container...")
        self._is_warming = True
        try:
            self._ensure_container()
            logger.info("🔥 Sandbox warmed up and ready!")
        except Exception as e:
            logger.error(f"Failed to warm up sandbox: {e}")
        finally:
            self._is_warming = False

    def _ensure_container(self):
        """确保容器正在运行且配置正确"""
        try:
            # 1. 尝试获取现有容器
            try:
                self.container = self.client.containers.get(self.container_name)
                if self.container.status != "running":
                    logger.info("Restarting stopped sandbox container...")
                    self.container.start()
            except docker.errors.NotFound:
                # 2. 如果不存在，创建新的
                logger.info("Starting new sandbox container...")
                self.container = self.client.containers.run(
                    self.image,
                    detach=True,
                    tty=True,
                    name=self.container_name,
                    # 限制资源防止滥用
                    mem_limit="512m",
                    nano_cpus=500000000, # 0.5 CPU
                    network_mode="none" # 断网，确保安全 (如果需要联网安装库需调整)
                )
                
            # 3. 基础环境检查 (Optional: 预加载常用库)
            # self.container.exec_run("pip install pandas numpy matplotlib") 
            
        except Exception as e:
            logger.error(f"Sandbox container error: {e}")
            raise e

    def run_code(self, code: str) -> Tuple[str, str, List[Dict[str, str]]]:
        """
        执行代码并返回 (stdout, stderr, image_artifacts)
        """
        self._ensure_container()
        
        # 简单的文件封装，为了捕获图片，通常需要更复杂的 wrapper
        # 这里简化为直接执行
        wrapped_code = self._wrap_code_with_plot_saving(code)
        
        # 写入文件
        setup_cmd = f"cat <<EOF > /tmp/script.py\n{wrapped_code}\nEOF"
        self.container.exec_run(f"sh -c '{setup_cmd}'")
        
        # 执行
        logger.info("Running code in sandbox...")
        exec_result = self.container.exec_run("python /tmp/script.py")
        
        stdout = exec_result.output.decode("utf-8")
        stderr = ""
        if exec_result.exit_code != 0:
            stderr = stdout # Python often prints errors to stdout/stderr mixed in docker exec
            stdout = ""

        # 尝试提取图片 (Mock logic for now)
        images = []
        # if "plot.png" in stdout... (Actual implementation would read file bytes from container)
        
        return stdout, stderr, images

    def _wrap_code_with_plot_saving(self, code: str) -> str:
        """注入 matplotlib 保存逻辑 (简化版)"""
        if "matplotlib" in code or "plt." in code:
            header = "import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
            footer = "\ntry:\n    plt.savefig('/tmp/plot.png')\n    print('[SYSTEM] Plot saved to /tmp/plot.png')\nexcept:\n    pass"
            return header + code + footer
        return code
