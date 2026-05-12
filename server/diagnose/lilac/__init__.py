"""
LILAC: LLM-based Log parsing with Adaptive Parsing Cache

统一日志解析模块，基于 LILAC (FSE'24) 方法实现：
  - 自适应前缀树缓存（已知模式秒级命中）
  - LLM 模板提取（未知模式智能解析）
  - Drain3 兜底（LLM 不可用时确定性降级）
"""

from server.diagnose.lilac.config import LilacConfig
from server.diagnose.lilac.parser import LilacParser

__all__ = ["LilacParser", "LilacConfig"]
