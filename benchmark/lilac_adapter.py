"""LILAC Loghub-2.0 适配器

将 LILAC 包装为 Loghub-2.0 兼容的 LogParser 接口：
- 使用 log_format 模板拆分日志行为 header fields + Content
- 对 Content 应用 dataset-specific regex 预处理
- 支持两种模式：
  - LLM 模式：完整 LILAC 流水线（cache → LLM → Drain3）
  - no-llm 模式：标准两遍 Drain3（与 Loghub-2.0 benchmark 对齐）
- 输出标准 structured.csv 和 templates.csv
"""

import hashlib
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.diagnose.lilac.config import LilacConfig
from server.diagnose.lilac.parser import LilacParser
from server.diagnose.lilac.preprocessor import LogPreprocessor


def generate_logformat_regex(log_format: str) -> Tuple[List[str], re.Pattern]:
    """将 Loghub log_format 模板转为命名捕获组正则。

    log_format 中的文字部分本身就是正则语法（如 \\[ 表示匹配 [），
    只有 <Field> 占位符被替换为捕获组。
    """
    headers = []
    splitters = re.split(r"(<[^<>]+>)", log_format)
    regex_parts = []

    for item in splitters:
        if item.startswith("<") and item.endswith(">"):
            header = item.strip("<>")
            headers.append(header)
            if header == "Content":
                regex_parts.append(f"(?P<{header}>.*)")
            else:
                regex_parts.append(f"(?P<{header}>.*?)")
        else:
            regex_parts.append(item)

    regex_str = "^" + "".join(regex_parts) + "$"
    return headers, re.compile(regex_str)


class LilacLoghubAdapter:
    """Loghub-2.0 兼容的 LILAC 适配器。

    实现 LogParser 接口: __init__(log_format, indir, outdir, ...) + parse(logName)
    """

    def __init__(
        self,
        log_format: str,
        indir: str,
        outdir: str,
        rex: Optional[List[str]] = None,
        cache_db_path: Optional[str] = None,
        enable_llm: bool = True,
        enable_drain3: bool = True,
        similarity_threshold: float = 0.85,
        drain_depth: int = 4,
        drain_sim_th: float = 0.4,
    ):
        self.log_format = log_format
        self.indir = indir
        self.outdir = outdir
        self.enable_llm = enable_llm
        self.drain_depth = drain_depth
        self.drain_sim_th = drain_sim_th

        self.headers, self.regex = generate_logformat_regex(log_format)
        self.rex = []
        for r in (rex or []):
            if isinstance(r, tuple):
                # (pattern, replacement) 格式：支持自定义替换（如空字符串）
                self.rex.append((re.compile(r[0]), r[1]))
            else:
                self.rex.append((re.compile(r), "<*>"))

        os.makedirs(outdir, exist_ok=True)

        if enable_llm:
            config = LilacConfig()
            config.enable_llm = True
            config.enable_drain3 = enable_drain3
            config.cache_similarity_threshold = similarity_threshold
            if cache_db_path:
                config.cache_db_path = cache_db_path
            self.lilac = LilacParser(config)
            self.lilac._preprocessor = LogPreprocessor(header_patterns=[])

    def parse(self, logName: str) -> None:
        """解析日志文件，输出 structured.csv 和 templates.csv。"""
        filepath = os.path.join(self.indir, logName)

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # 提取 header fields 和 Content
        parsed_lines = []
        for line_id, line in enumerate(lines, start=1):
            line = line.rstrip("\n\r")
            if not line.strip():
                continue

            match = self.regex.match(line)
            if match:
                fields = match.groupdict()
                content = fields.get("Content", line)
            else:
                fields = {}
                content = line

            processed_content = self._apply_regex(content)
            parsed_lines.append((line_id, fields, content, processed_content))

        if self.enable_llm:
            rows = self._parse_with_lilac(parsed_lines)
        else:
            rows = self._parse_with_drain3(parsed_lines)

        df = pd.DataFrame(rows)

        structured_file = os.path.join(self.outdir, f"{logName}_structured.csv")
        df.to_csv(structured_file, index=False)

        if not df.empty:
            templates_df = (
                df.groupby("EventId")
                .agg(EventTemplate=("EventTemplate", "first"), Occurrences=("EventId", "count"))
                .reset_index()
            )
        else:
            templates_df = pd.DataFrame(columns=["EventId", "EventTemplate", "Occurrences"])
        templates_file = os.path.join(self.outdir, f"{logName}_templates.csv")
        templates_df.to_csv(templates_file, index=False)

    def _parse_with_drain3(self, parsed_lines: list) -> List[Dict]:
        """标准两遍 Drain3 解析（与 Loghub-2.0 benchmark 对齐）。

        Pass 1: 所有日志喂入 Drain3 构建集群
        Pass 2: 对每条日志用 match() 获取最终模板
        """
        from drain3 import TemplateMiner
        from drain3.template_miner_config import TemplateMinerConfig

        config = TemplateMinerConfig()
        config.drain_depth = self.drain_depth
        config.drain_sim_th = self.drain_sim_th
        config.profiling_enabled = False

        miner = TemplateMiner(config=config)

        # Pass 1: 训练 — 所有日志喂入 Drain3
        for _, _, _, processed_content in parsed_lines:
            miner.add_log_message(processed_content)

        # Pass 2: 推理 — 用 match 获取每条日志的最终模板
        rows = []
        for line_id, fields, content, processed_content in parsed_lines:
            cluster = miner.match(processed_content)
            if cluster:
                event_template = cluster.get_template()
                # drain3 内部使用 <:*:> 作占位符，统一为 <*>
                event_template = event_template.replace("<:*:>", "<*>")
            else:
                event_template = processed_content

            event_id = self._compute_event_id(event_template)

            row = {"LineId": line_id}
            for header in self.headers:
                if header != "Content":
                    row[header] = fields.get(header, "")
            row["Content"] = content
            row["EventId"] = event_id
            row["EventTemplate"] = event_template
            rows.append(row)

        return rows

    def _parse_with_lilac(self, parsed_lines: list) -> List[Dict]:
        """LILAC 完整流水线解析（cache → LLM → Drain3）。"""
        rows = []
        for line_id, fields, content, processed_content in parsed_lines:
            entry = self.lilac.parse_line(processed_content, line_number=line_id)

            if entry.template:
                event_template = entry.template.template_str
            else:
                event_template = processed_content

            event_id = self._compute_event_id(event_template)

            row = {"LineId": line_id}
            for header in self.headers:
                if header != "Content":
                    row[header] = fields.get(header, "")
            row["Content"] = content
            row["EventId"] = event_id
            row["EventTemplate"] = event_template
            row["ParameterList"] = entry.parameters
            rows.append(row)

        return rows

    def _apply_regex(self, content: str) -> str:
        """应用 dataset-specific 正则预处理"""
        for pattern, replacement in self.rex:
            content = pattern.sub(replacement, content)
        return content

    @staticmethod
    def _compute_event_id(template: str) -> str:
        """MD5 前 8 字符作为 EventId"""
        return hashlib.md5(template.encode("utf-8")).hexdigest()[:8]
