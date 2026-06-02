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

        # 对大文件使用流式处理避免 OOM
        line_count = sum(1 for _ in open(filepath, "r", encoding="utf-8", errors="replace"))
        if not self.enable_llm and line_count > 500_000:
            self._parse_drain3_streaming(filepath, logName)
            return

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

    def _parse_drain3_streaming(self, filepath: str, logName: str) -> None:
        """流式 Drain3 解析，内存占用 O(clusters) 而非 O(lines)。

        Pass 1: 逐行读取 → 提取 Content → 预处理 → 喂入 Drain3，只保存 cluster_id 列表
        Pass 2: 重新读取文件 → 用 cluster_id 查找最终模板 → 逐行写入 CSV
        """
        import csv
        import time

        from drain3 import TemplateMiner
        from drain3.template_miner_config import TemplateMinerConfig

        config = TemplateMinerConfig()
        config.drain_depth = self.drain_depth
        config.drain_sim_th = self.drain_sim_th
        config.profiling_enabled = False
        miner = TemplateMiner(config=config)

        # Pass 1: 训练 Drain3，只存 cluster_id（每个 int 8 字节，16M 行 ≈ 128MB）
        cluster_ids = []
        total = 0
        t0 = time.time()
        progress_interval = 500_000

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line.strip():
                    cluster_ids.append(-1)
                    total += 1
                    continue

                match = self.regex.match(line)
                if match:
                    content = match.group("Content") if "Content" in match.groupdict() else line
                else:
                    content = line

                processed = self._apply_regex(content)
                result = miner.add_log_message(processed)
                cluster_ids.append(result["cluster_id"])
                total += 1

                if total % progress_interval == 0:
                    elapsed = time.time() - t0
                    speed = total / elapsed
                    print(f"\r    Pass1(train): {total} lines, {speed:.0f} lines/s, {len(miner.drain.clusters)} clusters", end="", flush=True)

        elapsed = time.time() - t0
        print(f"\r    Pass1(train): {total} lines done in {elapsed:.1f}s, {len(miner.drain.clusters)} clusters          ", flush=True)

        # 构建 cluster_id → 最终模板
        cluster_map = {}
        template_counts = {}
        for cluster in miner.drain.clusters:
            tpl = cluster.get_template().replace("<:*:>", "<*>")
            cid = cluster.cluster_id
            cluster_map[cid] = tpl
            eid = self._compute_event_id(tpl)
            template_counts[eid] = template_counts.get(eid, 0) + cluster.size

        # Pass 2: 重读文件，流式写入 CSV
        structured_file = os.path.join(self.outdir, f"{logName}_structured.csv")
        csv_headers = [h for h in self.headers if h != "Content"] + ["Content", "EventId", "EventTemplate"]

        t0 = time.time()
        idx = 0
        line_id = 0
        with open(filepath, "r", encoding="utf-8", errors="replace") as fin, \
             open(structured_file, "w", newline="", encoding="utf-8") as fout:
            writer = csv.DictWriter(fout, fieldnames=["LineId"] + csv_headers)
            writer.writeheader()

            for line in fin:
                line = line.rstrip("\n\r")
                line_id += 1
                cid = cluster_ids[idx]
                idx += 1

                if cid == -1:
                    continue

                match = self.regex.match(line)
                if match:
                    fields = match.groupdict()
                    content = fields.get("Content", line)
                else:
                    fields = {}
                    content = line

                event_template = cluster_map.get(cid, self._apply_regex(content))
                event_id = self._compute_event_id(event_template)

                row = {"LineId": line_id}
                for h in self.headers:
                    if h != "Content":
                        row[h] = fields.get(h, "")
                row["Content"] = content
                row["EventId"] = event_id
                row["EventTemplate"] = event_template
                writer.writerow(row)

                if line_id % progress_interval == 0:
                    elapsed = time.time() - t0
                    speed = line_id / elapsed
                    print(f"\r    Pass2(write): {line_id}/{total} ({100*line_id//total}%) {speed:.0f} lines/s", end="", flush=True)

        print(f"\r    Pass2(write): {total}/{total} (100%) done in {time.time()-t0:.1f}s          ", flush=True)

        # 写 templates.csv
        templates_file = os.path.join(self.outdir, f"{logName}_templates.csv")
        templates_rows = []
        for cluster in miner.drain.clusters:
            tpl = cluster.get_template().replace("<:*:>", "<*>")
            eid = self._compute_event_id(tpl)
            templates_rows.append({"EventId": eid, "EventTemplate": tpl, "Occurrences": cluster.size})
        pd.DataFrame(templates_rows).to_csv(templates_file, index=False)

    def _parse_with_drain3(self, parsed_lines: list) -> List[Dict]:
        """标准单遍 Drain3 解析（与 Loghub-2.0 benchmark 对齐）。

        Drain 是在线单遍算法：对每行日志调用 add_log_message() 即完成训练+分配。
        解析结束后取各 cluster 的最终模板作为该 cluster 所有日志的 EventTemplate。
        这与 logpai/loghub-2.0 官方 benchmark 评测方式一致。
        """
        import time

        from drain3 import TemplateMiner
        from drain3.template_miner_config import TemplateMinerConfig

        config = TemplateMinerConfig()
        config.drain_depth = self.drain_depth
        config.drain_sim_th = self.drain_sim_th
        config.profiling_enabled = False

        miner = TemplateMiner(config=config)

        total = len(parsed_lines)
        progress_interval = max(total // 20, 10000)

        # 单遍：add_log_message 同时训练并分配 cluster
        t0 = time.time()
        cluster_ids = []
        for i, (_, _, _, processed_content) in enumerate(parsed_lines):
            result = miner.add_log_message(processed_content)
            cluster_ids.append(result["cluster_id"])
            if (i + 1) % progress_interval == 0:
                elapsed = time.time() - t0
                speed = (i + 1) / elapsed
                print(f"\r    Drain3: {i+1}/{total} ({100*(i+1)//total}%) {speed:.0f} lines/s, {len(miner.drain.clusters)} clusters", end="", flush=True)
        if total > progress_interval:
            print(f"\r    Drain3: {total}/{total} (100%) done in {time.time()-t0:.1f}s, {len(miner.drain.clusters)} clusters", flush=True)

        # 取最终模板（训练结束后 cluster 模板已稳定）
        cluster_map = {}
        for cluster in miner.drain.clusters:
            tpl = cluster.get_template().replace("<:*:>", "<*>")
            cluster_map[cluster.cluster_id] = tpl

        rows = []
        for i, (line_id, fields, content, processed_content) in enumerate(parsed_lines):
            cid = cluster_ids[i]
            event_template = cluster_map.get(cid, processed_content)
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
