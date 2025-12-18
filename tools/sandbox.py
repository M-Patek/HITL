import docker
import tarfile
import io
import time
import base64
from typing import Tuple, List, Dict

class DockerSandbox:
    """
    [SWARM 3.0] 视觉增强型沙箱。
    不仅能跑代码，还能“看见”代码生成的图片产物。
    """
    def __init__(self, image: str = "python:3.11-slim"):
        self.image = image
        self.container_name = "swarm-sandbox-runner"
        self.client = None
        
        try:
            self.client = docker.from_env()
            self._ensure_container()
        except Exception as e:
            print(f"⚠️ [Sandbox] Docker init failed: {e}. Is Docker Desktop running?")
            self.client = None

    def _ensure_container(self):
        """确保沙箱容器正在后台静默运行"""
        if not self.client: return
        
        try:
            container = self.client.containers.get(self.container_name)
            if container.status != "running":
                container.start()
        except docker.errors.NotFound:
            print(f"📦 [Sandbox] Creating local container ({self.image})...")
            # 预装 matplotlib, pandas 等常用库，避免每次运行时安装
            # 注意：生产环境建议构建专门的 Docker Image
            self.client.containers.run(
                self.image,
                name=self.container_name,
                detach=True,
                tty=True,
                command="tail -f /dev/null", 
                mem_limit="1024m", # 画图可能需要更多内存
                nano_cpus=1000000000 
            )
            # 尝试预装库 (非阻塞，即使失败也不影响启动)
            try:
                print("📦 [Sandbox] Pre-installing plotting libs...")
                self.client.containers.get(self.container_name).exec_run("pip install matplotlib pandas numpy seaborn", detach=True)
            except: pass

    def run_code(self, code: str) -> Tuple[str, str, List[Dict[str, str]]]:
        """
        执行代码并捕获输出及图片产物。
        Returns: (stdout, stderr, image_artifacts)
        """
        if not self.client:
            return "", "Docker client not available.", []

        try:
            container = self.client.containers.get(self.container_name)
            
            # 1. 清理旧图片 (可选)
            container.exec_run("rm -f /app/*.png /app/*.jpg")

            # 2. 注入代码
            encoded_code = code.encode('utf-8')
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                tar_info = tarfile.TarInfo(name='script.py')
                tar_info.size = len(encoded_code)
                tar_info.mtime = time.time()
                tar.addfile(tar_info, io.BytesIO(encoded_code))
            tar_stream.seek(0)
            
            container.put_archive('/app', tar_stream)

            # 3. 执行
            print(f"🏃 [Sandbox] Executing code (Vision Enabled)...")
            exec_res = container.exec_run(
                "python /app/script.py", 
                workdir="/app",
                demux=True
            )
            
            stdout = exec_res.output[0].decode('utf-8') if exec_res.output[0] else ""
            stderr = exec_res.output[1].decode('utf-8') if exec_res.output[1] else ""
            
            # 4. [New] 抓取图片产物
            images = []
            if not stderr:
                images = self._extract_images(container)
            
            return stdout, stderr, images

        except Exception as e:
            return "", f"Sandbox Execution Error: {str(e)}", []

    def _extract_images(self, container) -> List[Dict[str, str]]:
        """从容器中提取 .png/.jpg 文件并转为 Base64"""
        images = []
        try:
            # 列出文件
            res = container.exec_run("ls /app")
            files = res.output.decode().split()
            img_files = [f for f in files if f.endswith('.png') or f.endswith('.jpg')]
            
            for fname in img_files:
                print(f"   🖼️ Found image artifact: {fname}")
                # 获取文件流
                bits, stat = container.get_archive(f"/app/{fname}")
                file_obj = io.BytesIO()
                for chunk in bits:
                    file_obj.write(chunk)
                file_obj.seek(0)
                
                # 解压 tar 流 (get_archive 返回的是 tar)
                with tarfile.open(fileobj=file_obj) as tar:
                    member = tar.getmember(fname)
                    img_data = tar.extractfile(member).read()
                    b64_str = base64.b64encode(img_data).decode('utf-8')
                    images.append({
                        "filename": fname,
                        "data": b64_str,
                        "mime_type": "image/png" if fname.endswith('.png') else "image/jpeg"
                    })
        except Exception as e:
            print(f"⚠️ Failed to extract images: {e}")
        
        return images
