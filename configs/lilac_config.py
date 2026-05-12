"""LILAC 日志解析模块配置常量"""

import os

# ============================================================
# LILAC 解析器配置
# ============================================================

# SQLite 缓存路径
LILAC_CACHE_DB_PATH = os.environ.get("LILAC_CACHE_DB_PATH", "data/lilac_cache.db")

# 缓存命中相似度阈值
LILAC_CACHE_SIMILARITY_THRESHOLD = float(
    os.environ.get("LILAC_CACHE_SIMILARITY_THRESHOLD", "0.85")
)

# LLM 参数
LILAC_LLM_TEMPERATURE = float(os.environ.get("LILAC_LLM_TEMPERATURE", "0.0"))
LILAC_LLM_TIMEOUT = float(os.environ.get("LILAC_LLM_TIMEOUT", "10.0"))

# Demonstration 池
LILAC_DEMO_POOL_MAX = int(os.environ.get("LILAC_DEMO_POOL_MAX", "500"))
LILAC_DEMO_SAMPLE_K = int(os.environ.get("LILAC_DEMO_SAMPLE_K", "8"))

# 功能开关
LILAC_ENABLE_LLM = os.environ.get("LILAC_ENABLE_LLM", "true").lower() in (
    "true", "1", "yes"
)
LILAC_ENABLE_DRAIN3 = os.environ.get("LILAC_ENABLE_DRAIN3", "true").lower() in (
    "true", "1", "yes"
)
