#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : utils.py
@Author  : LI
@Date    : 2026
@Desc    : 服务端工具函数模块
            提供 LLM 模型加载、Embedding 加载、时间处理等通用功能
"""
import os
import sys
import re
import asyncio
import httpx
import pydantic
import logging
import shutil
import urllib
from pydantic import BaseModel, Field
from typing import List, Optional, Callable, Generator, Dict, Any, Awaitable, Union, Tuple
from fastapi import FastAPI, UploadFile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_now():
    """
    @brief 获取当前北京时间
    @return: 带时区的 datetime 对象
    """
    return datetime.now(BEIJING_TZ)


def get_beijing_now_str(format_str="%Y-%m-%d %H:%M:%S"):
    """
    @brief 获取当前北京时间字符串
    @param format_str: 时间格式字符串
    @return: 格式化的时间字符串
    """
    return get_beijing_now().strftime(format_str)


def format_datetime_beijing(dt, format_str="%Y-%m-%d %H:%M:%S"):
    """
    @brief 将 datetime 对象转换为北京时间字符串
    @param dt: datetime 对象
    @param format_str: 输出格式
    @return: 格式化的北京时间字符串
    """
    if dt is None:
        return ""
    if dt.tzinfo is None:
        # 如果无时区信息，直接视为北京时间
        dt = dt.replace(tzinfo=BEIJING_TZ)
    beijing_dt = dt.astimezone(BEIJING_TZ)
    return beijing_dt.strftime(format_str)


from configs import (LLM_MODELS, MODEL_PATH, ONLINE_LLM_MODEL, logger, log_verbose, HTTPX_DEFAULT_TIMEOUT)
from langchain.chat_models import ChatOpenAI
from langchain.llms import OpenAI

os.environ['NO_PROXY'] = '*'
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

for env_key in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    os.environ[env_key] = ''
    if env_key in os.environ:
        del os.environ[env_key]


class BaseResponse(BaseModel):
    """
    @class BaseResponse
    @brief 统一 API 响应模型
    @param code: 状态码，200 表示成功
    @param msg: 响应消息
    @param data: 响应数据
    """
    code: int = Field(default=200)
    msg: str = Field(default="success")
    data: Any = Field(default=None)


class ListResponse(BaseResponse):
    """
    @class ListResponse
    @brief 列表类型 API 响应模型
    @param data: 列表数据（支持任意类型）
    """
    data: List[Any] = Field(default_factory=list, description="List of items")


MY_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MY_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
MY_MODEL_NAME = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").split(",")[0].strip()


def get_ChatOpenAI(model_name: str, temperature: float, max_tokens: int = None, streaming: bool = True, callbacks: List[Callable] = [], **kwargs: Any) -> ChatOpenAI:
    """
    @brief 获取 ChatOpenAI 实例
    @param model_name: 模型名称
    @param temperature: 生成温度参数
    @param max_tokens: 最大生成 token 数
    @param streaming: 是否启用流式输出
    @param callbacks: 回调函数列表
    @return: ChatOpenAI 实例
    @note 使用 DeepSeek API 作为后端
    """
    kwargs.pop("proxies", None) 
    kwargs.pop("http_client", None)
    kwargs.pop("http_async_client", None)
    
    return ChatOpenAI(
        streaming=streaming,
        callbacks=callbacks,
        openai_api_key=MY_API_KEY,
        openai_api_base=MY_API_BASE,
        model_name=MY_MODEL_NAME,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )


def get_OpenAI(model_name: str, temperature: float, **kwargs: Any) -> OpenAI:
    """
    @brief 获取 OpenAI LLM 实例
    @param model_name: 模型名称
    @param temperature: 生成温度参数
    @return: OpenAI 实例
    """
    kwargs.pop("proxies", None)
    return OpenAI(
        openai_api_key=MY_API_KEY,
        openai_api_base=MY_API_BASE,
        model_name=MY_MODEL_NAME,
        temperature=temperature,
        **kwargs
    )


def get_httpx_client(use_async: bool = False, **kwargs):
    """
    @brief 获取 httpx 客户端实例
    @param use_async: 是否使用异步客户端
    @return: httpx.Client 或 httpx.AsyncClient 实例
    """
    kwargs.pop("proxies", None)
    kwargs.pop("trust_env", None)
    if use_async:
        return httpx.AsyncClient(trust_env=False, **kwargs)
    return httpx.Client(trust_env=False, **kwargs)


async def wrap_done(fn: Awaitable, event: asyncio.Event):
    """
    @brief 包装异步任务完成事件
    @param fn: 异步任务
    @param event: 完成事件
    """
    try:
        await fn
    except Exception as e:
        logger.error(f"Chat Error: {e}")
    finally:
        event.set()


def run_in_thread_pool(func: Callable, params: List[Dict] = []) -> Generator:
    """
    @brief 在线程池中执行函数
    @param func: 要执行的函数
    @param params: 参数字典列表
    @return: 结果生成器
    """
    tasks = []
    with ThreadPoolExecutor() as pool:
        for kwargs in params:
            thread = pool.submit(func, **kwargs)
            tasks.append(thread)
        for obj in as_completed(tasks):
            yield obj.result()


def run_async(cor):
    """
    @brief 在同步环境中运行异步协程
    @param cor: 协程对象
    @return: 协程执行结果
    """
    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
    return loop.run_until_complete(cor)


def iter_over_async(ait, loop=None):
    """
    @brief 将异步迭代器转换为同步迭代器
    @param ait: 异步迭代器
    @param loop: 事件循环（可选）
    @return: 同步迭代器
    """
    ait = ait.__aiter__()
    async def get_next():
        try:
            obj = await ait.__anext__()
            return False, obj
        except StopAsyncIteration:
            return True, None
    if loop is None:
        loop = asyncio.get_event_loop()
    while True:
        done, obj = loop.run_until_complete(get_next())
        if done: break
        yield obj


def fschat_controller_address() -> str:
    """
    @brief 获取 FSChat Controller 地址
    @return: Controller URL
    """
    from configs.server_config import FSCHAT_CONTROLLER
    return f"http://127.0.0.1:{FSCHAT_CONTROLLER['port']}"


def fschat_model_worker_address(model_name: str = LLM_MODELS[0]) -> str:
    """
    @brief 获取 FSChat Model Worker 地址
    @param model_name: 模型名称
    @return: Model Worker URL
    """
    return "http://127.0.0.1:21002"


def fschat_openai_api_address() -> str:
    """
    @brief 获取 FSChat OpenAI API 地址
    @return: OpenAI API URL
    """
    from configs.server_config import FSCHAT_OPENAI_API
    return f"http://127.0.0.1:{FSCHAT_OPENAI_API['port']}/v1"


def api_address() -> str:
    """
    @brief 获取后端 API 地址
    @return: API URL
    """
    from configs.server_config import API_SERVER
    return f"http://127.0.0.1:{API_SERVER['port']}"


def webui_address() -> str:
    """
    @brief 获取 WebUI 地址
    @return: WebUI URL
    """
    from configs.server_config import WEBUI_SERVER
    return f"http://127.0.0.1:{WEBUI_SERVER['port']}"


def get_prompt_template(type: str, name: str) -> Optional[str]:
    """
    @brief 获取提示词模板
    @param type: 模板类型
    @param name: 模板名称
    @return: 模板字符串
    """
    from configs import prompt_config
    return prompt_config.PROMPT_TEMPLATES[type].get(name)


def get_model_worker_config(model_name: str = None) -> dict:
    """
    @brief 获取模型 Worker 配置
    @param model_name: 模型名称
    @return: 配置字典
    """
    from configs.model_config import ONLINE_LLM_MODEL
    return ONLINE_LLM_MODEL.get(model_name, {}).copy()


def list_config_llm_models() -> Dict:
    """
    @brief 列出配置的 LLM 模型
    @return: 模型配置字典
    """
    return {"local": MODEL_PATH.get("llm_model", {}), "online": ONLINE_LLM_MODEL}


def list_embed_models() -> List[str]:
    """
    @brief 列出可用的 Embedding 模型
    @return: 模型名称列表
    """
    return list(MODEL_PATH.get("embed_model", {}).keys())


def list_online_embed_models() -> List[str]:
    """
    @brief 列出在线 Embedding 模型
    @return: 模型名称列表
    """
    return []


def get_model_path(model_name: str, type: str = None):
    """
    @brief 获取模型路径
    @param model_name: 模型名称
    @param type: 模型类型
    @return: 模型绝对路径
    """
    paths = MODEL_PATH.get(type, {}) if type else {k: v for d in MODEL_PATH.values() for k, v in d.items()}
    raw_path = paths.get(model_name)
    if raw_path:
        return os.path.normpath(os.path.abspath(raw_path))
    return None


FALLBACK_EMBEDDING_MODELS = [
    "moka-ai/m3e-base",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "BAAI/bge-small-zh-v1.5",
]

_CACHED_EMBEDDINGS = None
_CACHED_MODEL_NAME = None


def load_local_embeddings(model: str = None, device: str = None):
    """
    @brief 加载本地 Embedding 模型
    @param model: 模型名称或路径
    @param device: 运行设备（cuda/cpu）
    @return: HuggingFaceEmbeddings 实例
    @note 自动检测 GPU 并使用备选模型
    """
    global _CACHED_EMBEDDINGS, _CACHED_MODEL_NAME
    
    from langchain.embeddings.huggingface import HuggingFaceEmbeddings
    from configs.model_config import EMBEDDING_DEVICE
    
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            print(f"[START] 检测到 GPU: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            print("[WARN] 未检测到 GPU，使用 CPU 模式")
    except ImportError:
        device = "cpu"
        print("[WARN] PyTorch 未安装，使用 CPU 模式")
    except Exception as e:
        device = "cpu"
        print(f"[WARN] GPU检测异常: {e}")
    model_path = get_model_path(model, "embed_model")

    if _CACHED_EMBEDDINGS is not None and _CACHED_MODEL_NAME == model:
        print(f"[OK] 使用缓存的嵌入模型: {model}")
        return _CACHED_EMBEDDINGS
    
    print(f"--- [DEBUG] Model Name: {model}, Path: {model_path} ---")
    
    models_to_try = []
    
    if model_path and os.path.exists(model_path):
        models_to_try.append(model_path)
    
    models_to_try.append(model)
    models_to_try.extend(FALLBACK_EMBEDDING_MODELS)
    
    for model_name in models_to_try:
        try:
            print(f"[REFLECT] 正在尝试加载 Embedding 模型: {model_name} (Device: {device})...")
            embeddings = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={'device': device},
                encode_kwargs={
                    'normalize_embeddings': True,
                    'batch_size': 32
                }
            )
            test_embedding = embeddings.embed_query("测试")
            if test_embedding and len(test_embedding) > 0:
                print(f"[OK] 模型 {model_name} 加载成功！向量维度: {len(test_embedding)}")
                _CACHED_EMBEDDINGS = embeddings
                _CACHED_MODEL_NAME = model
                return embeddings
            else:
                print(f"[WARN] 模型 {model_name} 加载成功但测试失败，尝试下一个...")
        except Exception as e:
            print(f"[ERROR] 加载 {model_name} 失败: {str(e)[:100]}")
            continue
    
    print(f"[ERROR] 所有嵌入模型都加载失败！")
    return None


def save_file(file: UploadFile, path: str) -> bool:
    """
    @brief 保存上传文件
    @param file: 上传的文件对象
    @param path: 保存路径
    @return: 保存成功返回 True
    """
    try:
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return True
    except:
        return False


def MakeFastAPIOffline(app: FastAPI, static_dir=Path(__file__).parent / "static") -> None:
    """
    @brief 配置 FastAPI 离线模式
    @param app: FastAPI 应用实例
    @param static_dir: 静态文件目录
    """
    pass


def set_httpx_config(): 
    """
    @brief 配置 httpx 全局设置
    @return: 配置成功返回 True
    """
    os.environ["no_proxy"] = "*"
    return True


def all_embed_models() -> BaseResponse:
    """
    @brief 获取所有 Embedding 模型列表
    @return: API 响应对象
    """
    return BaseResponse(data=list_embed_models())


def get_server_configs() -> Dict:
    """
    @brief 获取服务器配置
    @return: 配置字典
    """
    from configs.model_config import HISTORY_LEN, TEMPERATURE
    return {"LLM_MODELS": LLM_MODELS, "HISTORY_LEN": HISTORY_LEN, "TEMPERATURE": TEMPERATURE}


def get_all_model_worker_configs() -> Dict:
    """
    @brief 获取所有模型 Worker 配置
    @return: 配置字典
    """
    from configs.model_config import ONLINE_LLM_MODEL, MODEL_PATH
    configs = {}
    configs.update(ONLINE_LLM_MODEL)
    for k, v in MODEL_PATH.get("llm_model", {}).items():
        configs[k] = {"local_model_path": v}
    return configs


def llm_device() -> str:
    """
    @brief 获取 LLM 运行设备
    @return: 设备名称（cuda/cpu）
    """
    try:
        from configs.model_config import LLM_DEVICE
        return LLM_DEVICE
    except:
        return "cpu"


def embedding_device() -> str:
    """
    @brief 获取 Embedding 运行设备
    @return: 设备名称（cuda/cpu）
    """
    try:
        from configs.model_config import EMBEDDING_DEVICE
        return EMBEDDING_DEVICE
    except:
        return "cpu"


# ==============================================================================
# 类型转换工具集 - 解决 PostgreSQL Decimal 类型无法 JSON 序列化问题
# ==============================================================================

import json
from decimal import Decimal
from datetime import date, time


class DecimalEncoder(json.JSONEncoder):
    """
    自定义 JSON 编码器，支持 Decimal、datetime 等特殊类型
    
    解决 PostgreSQL 返回的 numeric/float8 类型为 Decimal 对象，
    Python 原生 json 模块无法序列化的问题
    """
    
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (datetime, date, time)):
            return obj.isoformat()
        elif isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)


def convert_decimal_to_float(value):
    """
    将 Decimal 类型转换为 float
    
    @param value: 输入值
    @return: 转换后的值
    """
    if isinstance(value, Decimal):
        return float(value)
    return value


def convert_datetime_to_str(value):
    """
    将 datetime 类型转换为 ISO 格式字符串
    
    @param value: 输入值
    @return: 转换后的值
    """
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def normalize_value(value):
    """
    标准化单个值，处理 Decimal、datetime 等特殊类型
    
    @param value: 输入值
    @return: 标准化后的值
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value


def normalize_data(data):
    """
    递归转换数据结构中的 Decimal、datetime 等特殊类型为 Python 原生类型
    
    支持 dict、list、tuple、set 等嵌套结构
    
    @param data: 输入数据（任意类型）
    @return: 标准化后的数据
    """
    if data is None:
        return None
    
    if isinstance(data, Decimal):
        return float(data)
    
    if isinstance(data, (datetime, date, time)):
        return data.isoformat()
    
    if isinstance(data, bytes):
        return data.decode('utf-8', errors='replace')
    
    if isinstance(data, dict):
        return {key: normalize_data(value) for key, value in data.items()}
    
    if isinstance(data, (list, tuple)):
        return [normalize_data(item) for item in data]
    
    if isinstance(data, set):
        return [normalize_data(item) for item in data]
    
    return data


def safe_json_dumps(data, **kwargs):
    """
    安全的 JSON 序列化函数，自动处理 Decimal、datetime 等特殊类型
    
    @param data: 要序列化的数据
    @param kwargs: 传递给 json.dumps 的其他参数
    @return: JSON 字符串
    """
    normalized_data = normalize_data(data)
    return json.dumps(normalized_data, ensure_ascii=False, **kwargs)


def safe_json_loads(json_str, **kwargs):
    """
    安全的 JSON 反序列化函数
    
    @param json_str: JSON 字符串
    @param kwargs: 传递给 json.loads 的其他参数
    @return: Python 对象
    """
    if json_str is None:
        return None
    return json.loads(json_str, **kwargs)


def clean_garbage_text(text: str) -> str:
    """
    【优化2】清洗 LLM 输出中的乱码和垃圾文本
    
    针对性过滤常见的乱码模式：
    - (u7b, (u' 等 Python 内部表示
    - bJT, b'...' 等字节串表示
    - 内存地址 0x7f...
    - Unicode 转义序列 \\uXXXX
    - 长串无意义字符
    - penc, ck8^, _8^9h 等乱码词
    
    @param text: 待清洗的文本
    @return: 清洗后的干净文本
    """
    if not isinstance(text, str):
        return ""
    
    patterns = [
        r'\(u[0-9a-fA-F]{2,}\b',
        r'\(u\'[^\']*\'\)',
        r"b['\"][^'\"]*['\"]",
        r'0x[0-9a-fA-F]{8,}',
        r'\\u[0-9a-fA-F]{4}',
        r'<[a-zA-Z0-9_]+>',
        r'\\x[0-9a-fA-F]{2}',
        r'\(u[0-9a-z]{2,}',
        r'[a-z]?\^[0-9a-z_]{1,}',
        r'\b[a-z]{1,3}[0-9]{1,2}\^[a-z0-9_]{1,}\b',
        r'\b_[0-9a-z\^]{2,}\b',
        r'\bpenc\b',
        r'\bck8\^[a-z0-9]*',
        r'\b[a-z]{2,4}[0-9]{1,2}\^[a-z0-9_]{1,}\b',
        r'[a-zA-Z0-9\^_]{8,}(?=\s|$)',
        r'\s+[a-z]{1,3}[0-9]{1,3}[a-z]{0,3}\s+',
        r'\b[uU][\'"][^\'"]*[\'"]',
        r'\([a-z]{1,2}[0-9a-fA-F]{2,}\)',
    ]
    
    combined_pattern = '|'.join(patterns)
    cleaned = re.sub(combined_pattern, '', text, flags=re.IGNORECASE)
    
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'\s+([,.，。])', r'\1', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned


def robust_json_parse(raw_text: str, strict: bool = False) -> Any:
    """
    【优化1】增强版 JSON 解析器 - 解决 LLM 输出截断导致的 JSON 损坏问题
    
    支持多种修复策略：
    1. 标准解析
    2. Markdown 代码块提取
    3. 补全缺失的引号和括号
    4. 截取最后一个完整对象
    5. 正则提取键值对（最后的保底）
    
    @param raw_text: LLM 原始输出文本
    @param strict: 是否严格模式（严格模式下解析失败会抛出异常）
    @return: 解析后的 Python 对象，解析失败返回 None
    """
    import re
    
    if not raw_text or not isinstance(raw_text, str):
        return None
    
    raw_text = raw_text.strip()
    
    # 策略1：尝试直接解析
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.debug(f"[robust_json_parse] 标准解析失败: {e}")
    
    # 策略2：提取 Markdown 代码块中的 JSON
    code_block_patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
    ]
    for pattern in code_block_patterns:
        matches = re.findall(pattern, raw_text, re.IGNORECASE)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue
    
    # 策略3：提取 JSON 数组或对象
    json_patterns = [
        r'\[\s*\{[\s\S]*\}\s*\]',
        r'\{[\s\S]*\}',
    ]
    for pattern in json_patterns:
        matches = re.findall(pattern, raw_text)
        for json_str in matches:
            # 3a: 尝试直接解析
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
            
            # 3b: 补全缺失的引号
            try:
                if json_str.count('"') % 2 == 1:
                    json_str = json_str + '"'
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
            
            # 3c: 补全缺失的括号
            try:
                open_braces = json_str.count('{')
                close_braces = json_str.count('}')
                open_brackets = json_str.count('[')
                close_brackets = json_str.count(']')
                
                json_str = json_str + '}' * (open_braces - close_braces)
                json_str = json_str + ']' * (open_brackets - close_brackets)
                
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
            
            # 3d: 截取最后一个完整对象
            try:
                last_brace = json_str.rfind('}')
                if last_brace > 0:
                    partial = json_str[:last_brace+1]
                    if partial.startswith('[') and not partial.endswith(']'):
                        partial = partial + ']'
                    return json.loads(partial)
            except json.JSONDecodeError:
                pass
    
    # 策略4：正则提取键值对（最后的保底）
    try:
        result = []
        action_pattern = r'"action"\s*:\s*"([^"]*)"'
        sql_pattern = r'"sql"\s*:\s*"([^"]*)"'
        
        actions = re.findall(action_pattern, raw_text)
        sqls = re.findall(sql_pattern, raw_text)
        
        for i, action in enumerate(actions):
            item = {"action": action}
            if i < len(sqls):
                item["sql"] = sqls[i]
            result.append(item)
        
        if result:
            logger.info(f"[robust_json_parse] 正则提取成功，找到 {len(result)} 个对象")
            return result
    except Exception as e:
        logger.warning(f"[robust_json_parse] 正则提取失败: {e}")
    
    if strict:
        raise ValueError("LLM 输出被严重截断，无法解析为有效 JSON。请增加 max_tokens 或优化 Prompt。")
    
    logger.warning("[robust_json_parse] 所有解析策略失败，返回 None")
    return None


# ==============================================================================
# 【优化3】并发控制 - LLM 请求限流
# ==============================================================================

_llm_semaphore: Optional[asyncio.Semaphore] = None


def get_llm_semaphore(limit: int = None) -> asyncio.Semaphore:
    """
    获取 LLM 并发控制信号量
    
    @param limit: 并发限制数量，默认从配置读取
    @return: asyncio.Semaphore 实例
    """
    global _llm_semaphore
    if _llm_semaphore is None:
        try:
            from configs import LLM_CONCURRENT_LIMIT
            limit = limit or LLM_CONCURRENT_LIMIT
        except ImportError:
            limit = limit or 3
        _llm_semaphore = asyncio.Semaphore(limit)
    return _llm_semaphore


async def with_llm_semaphore(coro, limit: int = None):
    """
    在并发控制下执行 LLM 请求
    
    @param coro: 异步协程对象
    @param limit: 并发限制数量
    @return: 协程执行结果
    """
    semaphore = get_llm_semaphore(limit)
    async with semaphore:
        return await coro
