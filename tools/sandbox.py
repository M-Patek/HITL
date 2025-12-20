import docker
import time
import logging
import tarfile
import io
import base64
import os
from typing import Tuple, List, Optional, Dict

logger = logging.getLogger("Tools-Sandbox")

class DockerSandbox:
    """
    [Speculative Warming Enhanced]
    安全执行 Python 代码的沙箱环境。支持容器预热。
    已修复: 移除 Shell 注入风险，支持真实图片提取。
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
            
        except Exception as e:
            logger.error(f"Sandbox container error: {e}")
            raise e

    def run_code(self, code: str) -> Tuple[str, str, List[Dict[str, str]]]:
        """
        执行代码并返回 (stdout, stderr, image_artifacts)
        """
        self._ensure_container()
        
        # 1. 代码预处理与封装 (注入 matplotlib Agg 后端)
        wrapped_code = self._wrap_code_with_plot_saving(code)
        
        # 2. [Secure Fix] 使用 put_archive 安全写入代码文件
        # 废弃: setup_cmd = f"cat <<EOF > /tmp/script.py..." (Vulnerable)
        try:
            self._write_file_to_container("/tmp", "script.py", wrapped_code)
        except Exception as e:
            logger.error(f"Failed to write code to sandbox: {e}")
            return "", f"System Error: Failed to write code ({str(e)})", []
        
        # 3. 执行代码
        logger.info("Running code in sandbox...")
        # 注意: 如果需要捕获 print 输出，确保 python 脚本中有 flush 或使用 -u 参数
        exec_result = self.container.exec_run("python -u /tmp/script.py")
        
        stdout = exec_result.output.decode("utf-8", errors="replace")
        stderr = ""
        if exec_result.exit_code != 0:
            # 简单处理: 如果失败，通常 stdout 包含错误堆栈
            stderr = stdout 
            stdout = ""

        # 4. [Real Feature] 尝试提取生成的图片
        images = self._extract_image_from_container("/tmp/plot.png")
        if images:
            logger.info(f"📸 Retrieved {len(images)} image(s) from sandbox.")
        
        return stdout, stderr, images

    def _write_file_to_container(self, dest_dir: str, filename: str, content: str):
        """
        将字符串内容以文件的形式写入容器指定目录 (安全原子操作)
        """
        # 在内存中构建 tar 包
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            data = content.encode('utf-8')
            tarinfo = tarfile.TarInfo(name=filename)
            tarinfo.size = len(data)
            tarinfo.mtime = time.time()
            tar.addfile(tarinfo, io.BytesIO(data))
        
        tar_stream.seek(0)
        # 上传 tar 包，Docker 会自动解压到 dest_dir
        self.container.put_archive(path=dest_dir, data=tar_stream)

    def _extract_image_from_container(self, filepath: str) -> List[Dict[str, str]]:
        """
        从容器中提取指定文件并转换为 Base64 (用于前端展示)
        """
        images = []
        try:
            # get_archive 返回 (stream, stat)
            stream, stat = self.container.get_archive(filepath)
            
            # 将 stream 读入内存
            file_obj = io.BytesIO()
            for chunk in stream:
                file_obj.write(chunk)
            file_obj.seek(0)
            
            # 解压 tar 流
            with tarfile.open(fileobj=file_obj, mode='r') as tar:
                # 获取文件名 (通常是 basename)
                member_name = os.path.basename(filepath)
                # 能够容错：有时 tar 内的文件名可能带路径，遍历寻找
                target_member = None
                for m in tar.getmembers():
                    if m.name.endswith(member_name):
                        target_member = m
                        break
                
                if target_member:
                    img_data = tar.extractfile(target_member).read()
                    b64_img = base64.b64encode(img_data).decode('utf-8')
                    
                    images.append({
                        "type": "image", 
                        "filename": member_name,
                        # 前端可直接使用的 Data URI
                        "data": f"data:image/png;base64,{b64_img}" 
                    })
                    
        except docker.errors.NotFound:
            # 文件不存在，说明代码没有生成图片，正常情况
            pass
        except Exception as e:
            logger.warning(f"Failed to extract image artifact: {e}")
            
        return images

    def _wrap_code_with_plot_saving(self, code: str) -> str:
        """注入 matplotlib 保存逻辑 (简化版)"""
        if "matplotlib" in code or "plt." in code:
            # 强制非交互式后端，防止报错
            header = "import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
            # 捕获可能的绘图并保存
            footer = "\ntry:\n    if plt.get_fignums():\n        plt.savefig('/tmp/plot.png')\n        print('[SYSTEM] Plot saved to /tmp/plot.png')\nexcept Exception as e:\n    print(f'[SYSTEM] Plot save failed: {e}')"
            return header + code + footer
        return code
