import os
import sys

# ================= 0. 【主进程代理补丁】 =================
os.environ["no_proxy"] = "*"
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""
os.environ["all_proxy"] = ""

import asyncio
import multiprocessing as mp
import time
import platform
import subprocess
from multiprocessing import Process
from typing import Tuple, List, Dict
import argparse

# ================= 1. 【ChromaDB 专属强制补丁】 =================
try:
    import sqlite3
    if sqlite3.sqlite_version_info < (3, 35, 0):
        try:
            from pysqlite3 import dbapi2 as sqlite3_backup
            sys.modules["sqlite3"] = sqlite3_backup
            print(">>> [系统补丁] 已完成 SQLite3 版本重定向 (ChromaDB 兼容模式)")
        except ImportError:
            pass
except Exception:
    pass

# ================= 2. 【核心补丁】屏蔽 vllm 并强修路径 =================
sys.modules["vllm"] = None 

conda_site_packages = r"D:\Conda_Latest\Lib\site-packages"
if conda_site_packages not in sys.path:
    sys.path.insert(0, conda_site_packages)

try:
    import chromadb
    print(f">>> [环境检查] ChromaDB 已识别 (版本: {chromadb.__version__})")
except ImportError:
    print("\n[！！！严重警告！！！] 当前环境仍找不到 chromadb。")

def _set_app_event(app, started_event: mp.Event = None):
    @app.on_event("startup")
    async def on_startup():
        if started_event is not None:
            started_event.set()

# ================= 3. 配置与依赖加载 =================
try:
    from configs import (
        LOG_PATH, LLM_MODELS, FSCHAT_CONTROLLER, FSCHAT_OPENAI_API,
        API_SERVER, WEBUI_SERVER, VERSION, DEFAULT_BIND_HOST
    )
    from server.utils import (
        fschat_controller_address, fschat_model_worker_address,
        set_httpx_config, get_model_worker_config,
        FastAPI, llm_device, MakeFastAPIOffline
    )
except ImportError as e:
    print(f"\n[错误] 配置加载失败: {e}")
    sys.exit(1)

# ================= 4. Worker 创建工厂 =================
def create_model_worker_app(log_level: str = "INFO", **kwargs) -> FastAPI:
    import fastchat.constants
    fastchat.constants.LOGDIR = LOG_PATH
    
    controller_addr = kwargs.get("controller_address", fschat_controller_address())
    worker_addr = kwargs.get("worker_address", "")
    model_path = kwargs.get("model_path", "")
    model_names = kwargs.get("model_names", ["default_model"])
    limit_worker_concurrency = kwargs.get("limit_worker_concurrency", 5)
    worker_id = kwargs.get("worker_id", f"worker_{int(time.time())}")
    device = kwargs.get("device", llm_device())

    try:
        from fastchat.serve.model_worker import ModelWorker, app as worker_app
        worker = ModelWorker(
            controller_addr=controller_addr,
            worker_addr=worker_addr,
            worker_id=worker_id,
            model_path=model_path,
            model_names=model_names,
            device=device,
            limit_worker_concurrency=limit_worker_concurrency,
            no_register=False,
            num_gpus=1 if "cuda" in device else 0,
            max_gpu_memory="20GiB" 
        )
    except Exception:
        from fastchat.serve.base_model_worker import BaseModelWorker, app as worker_app
        worker = BaseModelWorker(
            controller_addr=controller_addr,
            worker_addr=worker_addr,
            worker_id=worker_id,
            model_path=model_path,
            model_names=model_names,
            limit_worker_concurrency=limit_worker_concurrency
        )
    worker_app._worker = worker
    return worker_app

# ================= 5. 各模块启动包装 (带子进程隔离补丁) =================
def run_controller(log_level: str = "INFO", started_event: mp.Event = None):
    # 子进程补丁
    os.environ["no_proxy"] = "*"
    os.environ["http_proxy"] = ""
    os.environ["https_proxy"] = ""
    
    import uvicorn
    from fastchat.serve.controller import app, Controller
    set_httpx_config()
    controller = Controller("shortest_queue")
    sys.modules["fastchat.serve.controller"].controller = controller
    app._controller = controller
    _set_app_event(app, started_event)
    uvicorn.run(app, host=FSCHAT_CONTROLLER["host"], port=FSCHAT_CONTROLLER["port"], log_level="info")

def run_model_worker(model_name: str, started_event: mp.Event = None):
    # 子进程补丁
    os.environ["no_proxy"] = "*"
    os.environ["http_proxy"] = ""
    os.environ["https_proxy"] = ""
    
    import uvicorn
    set_httpx_config()
    kwargs = get_model_worker_config(model_name)
    kwargs["controller_address"] = fschat_controller_address()
    kwargs["worker_address"] = fschat_model_worker_address(model_name)
    kwargs["model_names"] = [model_name]
    
    app = create_model_worker_app(log_level="INFO", **kwargs)
    _set_app_event(app, started_event)
    uvicorn.run(app, host=DEFAULT_BIND_HOST, port=kwargs.get("port", 21002), log_level="info")

def run_api_server(started_event: mp.Event = None):
    # 子进程补丁 (API进程是知识库创建的核心，必须强制隔离)
    os.environ["no_proxy"] = "*"
    os.environ["http_proxy"] = ""
    os.environ["https_proxy"] = ""
    os.environ["all_proxy"] = ""

    try:
        from server.api import create_app
        import uvicorn
        app = create_app()
        _set_app_event(app, started_event)
        uvicorn.run(app, host=API_SERVER["host"], port=API_SERVER["port"], log_level="info")
    except Exception as e:
        print(f"\n[API 运行异常]: {e}")

# ================= 6. 主进程调度 =================
async def start_main_server():
    mp.set_start_method("spawn", force=True)
    manager = mp.Manager()
    processes = {}
    
    print("\n" + "="*50)
    print(f"DB-GPT {VERSION} - ChromaDB 终极补丁启动器")
    print("="*50 + "\n")

    c_ev = manager.Event()
    processes["controller"] = Process(target=run_controller, args=("INFO", c_ev), daemon=True)
    processes["controller"].start()
    
    for _ in range(15):
        if c_ev.is_set(): break
        await asyncio.sleep(1)

    for m in LLM_MODELS:
        w_ev = manager.Event()
        p = Process(target=run_model_worker, args=(m, w_ev), daemon=True)
        p.start()
        await asyncio.sleep(3)
        processes[f"worker_{m}"] = p

    a_ev = manager.Event()
    processes["api"] = Process(target=run_api_server, args=(a_ev,), daemon=True)
    processes["api"].start()

    print("\n[启动状态监控中...]")
    
    try:
        while True:
            await asyncio.sleep(1)
            if not processes["controller"].is_alive(): break
    except KeyboardInterrupt:
        print("\n正在安全关闭...")
    finally:
        for p in processes.values():
            if p.is_alive(): p.terminate()

if __name__ == "__main__":
    try:
        asyncio.run(start_main_server())
    except Exception as e:
        print(f"主程序崩溃: {e}")