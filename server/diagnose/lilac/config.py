"""LILAC 配置管理"""

import os
from dataclasses import dataclass, field


@dataclass
class LilacConfig:
    """LILAC 解析器配置，所有参数通过环境变量 LILAC_* 控制"""

    cache_db_path: str = field(
        default_factory=lambda: os.environ.get(
            "LILAC_CACHE_DB_PATH", "data/lilac_cache.db"
        )
    )

    cache_similarity_threshold: float = field(
        default_factory=lambda: float(
            os.environ.get("LILAC_CACHE_SIMILARITY_THRESHOLD", "0.85")
        )
    )

    llm_temperature: float = field(
        default_factory=lambda: float(
            os.environ.get("LILAC_LLM_TEMPERATURE", "0.0")
        )
    )

    llm_timeout: float = field(
        default_factory=lambda: float(
            os.environ.get("LILAC_LLM_TIMEOUT", "10.0")
        )
    )

    demo_pool_max: int = field(
        default_factory=lambda: int(
            os.environ.get("LILAC_DEMO_POOL_MAX", "500")
        )
    )

    demo_sample_k: int = field(
        default_factory=lambda: int(
            os.environ.get("LILAC_DEMO_SAMPLE_K", "8")
        )
    )

    enable_llm: bool = field(
        default_factory=lambda: os.environ.get(
            "LILAC_ENABLE_LLM", "true"
        ).lower() in ("true", "1", "yes")
    )

    enable_drain3: bool = field(
        default_factory=lambda: os.environ.get(
            "LILAC_ENABLE_DRAIN3", "true"
        ).lower() in ("true", "1", "yes")
    )
