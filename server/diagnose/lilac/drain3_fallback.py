"""LILAC Drain3 兜底解析器"""

import logging
from typing import Optional

from server.diagnose.lilac.models import LogTemplate

logger = logging.getLogger(__name__)


class Drain3Fallback:
    """Drain3 确定性兜底解析器

    当 LLM 不可用或失败时，使用 Drain3 算法进行确定性模板提取。
    """

    def __init__(self, depth: int = 4, sim_th: float = 0.4):
        self._depth = depth
        self._sim_th = sim_th
        self._miner = None
        self._available = False
        self._init_miner()

    def _init_miner(self) -> None:
        try:
            from drain3 import TemplateMiner
            from drain3.template_miner_config import TemplateMinerConfig

            config = TemplateMinerConfig()
            config.drain_depth = self._depth
            config.drain_sim_th = self._sim_th
            config.profiling_enabled = False

            self._miner = TemplateMiner(config=config)
            self._available = True
        except ImportError:
            logger.info("drain3 not installed, fallback disabled")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def parse(self, log_message: str) -> Optional[LogTemplate]:
        """使用 Drain3 解析日志，返回 LogTemplate 或 None"""
        if not self._available or not self._miner:
            return None

        try:
            result = self._miner.add_log_message(log_message)
            if result and result.get("cluster_id"):
                template_str = result.get("template_mined", "")
                if template_str:
                    template_str = template_str.replace("<:*:>", "<*>")
                    return LogTemplate.from_template_str(template_str, source="drain3")
        except Exception as e:
            logger.warning(f"Drain3 parsing failed: {e}")

        return None
