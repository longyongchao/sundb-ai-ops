"""LILAC API-Based Loghub-2.0 适配器

通过 HTTP 调用 LILAC REST API 来评测生产环境行为：
- Cache 机制在批次间持续生效（重复模式命中缓存）
- 完整的 LILAC 流水线：preprocessor → cache → Drain3/LLM
- 支持流式批量处理（大文件不 OOM）
"""

import csv
import hashlib
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark.utils import generate_logformat_regex


class LilacApiAdapter:
    """通过 LILAC REST API 进行 Loghub-2.0 兼容评测。

    与 LilacLoghubAdapter 相同的 LogParser 接口: __init__(...) + parse(logName)
    """

    def __init__(
        self,
        log_format: str,
        indir: str,
        outdir: str,
        rex: Optional[List] = None,
        api_base: str = "http://localhost:7861",
        batch_size: int = 10000,
        reset_cache: bool = True,
        **kwargs,
    ):
        self.log_format = log_format
        self.indir = indir
        self.outdir = outdir
        self.api_base = api_base.rstrip("/")
        self.batch_size = batch_size
        self.reset_cache = reset_cache

        self.headers, self.regex = generate_logformat_regex(log_format)

        # 构建 API regex 参数（传给服务端做预处理）
        self.api_regex = None
        if rex:
            self.api_regex = []
            for r in rex:
                if isinstance(r, tuple):
                    self.api_regex.append({"pattern": r[0], "replacement": r[1]})
                else:
                    self.api_regex.append({"pattern": r})

        os.makedirs(outdir, exist_ok=True)

        self.total_cache_hits = 0
        self.total_llm_calls = 0
        self.total_drain3_fallbacks = 0

    def parse(self, logName: str) -> None:
        """解析日志文件，通过 API 批量调用，输出 structured.csv 和 templates.csv。"""
        filepath = os.path.join(self.indir, logName)

        self._check_server()

        if self.reset_cache:
            self._clear_cache()

        self.total_cache_hits = 0
        self.total_llm_calls = 0
        self.total_drain3_fallbacks = 0

        line_count = sum(1 for _ in open(filepath, "r", encoding="utf-8", errors="replace"))

        if line_count > 500_000:
            self._parse_streaming(filepath, logName, line_count)
        else:
            self._parse_in_memory(filepath, logName)

    def _parse_in_memory(self, filepath: str, logName: str) -> None:
        """内存模式：读取全部行，分批调用 API。"""
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

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

            parsed_lines.append((line_id, fields, content))

        total = len(parsed_lines)
        rows = []
        progress_interval = max(total // 20, 1000)

        t0 = time.time()
        for batch_start in range(0, total, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total)
            batch = parsed_lines[batch_start:batch_end]

            batch_texts = [item[2] for item in batch]
            entries = self._send_batch(batch_texts)

            for i, (line_id, fields, content) in enumerate(batch):
                if i < len(entries):
                    entry = entries[i]
                    event_template = entry.get("template") or content
                else:
                    event_template = content

                event_id = self._compute_event_id(event_template)

                row = {"LineId": line_id}
                for header in self.headers:
                    if header != "Content":
                        row[header] = fields.get(header, "")
                row["Content"] = content
                row["EventId"] = event_id
                row["EventTemplate"] = event_template
                rows.append(row)

            if (batch_end) % progress_interval < self.batch_size or batch_end == total:
                elapsed = time.time() - t0
                speed = batch_end / elapsed if elapsed > 0 else 0
                print(
                    f"\r    API: {batch_end}/{total} ({100*batch_end//total}%) "
                    f"{speed:.0f} lines/s, cache_hits={self.total_cache_hits}",
                    end="", flush=True,
                )

        if total > 0:
            print(
                f"\r    API: {total}/{total} (100%) done in {time.time()-t0:.1f}s, "
                f"cache={self.total_cache_hits} drain3={self.total_drain3_fallbacks} "
                f"llm={self.total_llm_calls}          ",
                flush=True,
            )

        self._write_results(rows, logName)

    def _parse_streaming(self, filepath: str, logName: str, total_lines: int) -> None:
        """流式模式：逐批读取+发送+写入，避免 OOM。"""
        structured_file = os.path.join(self.outdir, f"{logName}_structured.csv")
        csv_headers = [h for h in self.headers if h != "Content"] + ["Content", "EventId", "EventTemplate"]

        template_counts: Dict[str, Tuple[str, int]] = {}

        t0 = time.time()
        total_processed = 0
        progress_interval = 500_000

        with open(filepath, "r", encoding="utf-8", errors="replace") as fin, \
             open(structured_file, "w", newline="", encoding="utf-8") as fout:
            writer = csv.DictWriter(fout, fieldnames=["LineId"] + csv_headers)
            writer.writeheader()

            batch_lines = []
            batch_meta = []
            line_id = 0

            for raw_line in fin:
                raw_line = raw_line.rstrip("\n\r")
                line_id += 1

                if not raw_line.strip():
                    continue

                match = self.regex.match(raw_line)
                if match:
                    fields = match.groupdict()
                    content = fields.get("Content", raw_line)
                else:
                    fields = {}
                    content = raw_line

                batch_lines.append(content)
                batch_meta.append((line_id, fields, content))

                if len(batch_lines) >= self.batch_size:
                    self._flush_batch(batch_lines, batch_meta, writer, template_counts)
                    total_processed += len(batch_lines)
                    batch_lines = []
                    batch_meta = []

                    if total_processed % progress_interval < self.batch_size:
                        elapsed = time.time() - t0
                        speed = total_processed / elapsed if elapsed > 0 else 0
                        print(
                            f"\r    API(stream): {total_processed}/{total_lines} "
                            f"({100*total_processed//total_lines}%) {speed:.0f} lines/s",
                            end="", flush=True,
                        )

            if batch_lines:
                self._flush_batch(batch_lines, batch_meta, writer, template_counts)
                total_processed += len(batch_lines)

        elapsed = time.time() - t0
        print(
            f"\r    API(stream): {total_processed}/{total_processed} (100%) done in {elapsed:.1f}s, "
            f"cache={self.total_cache_hits} drain3={self.total_drain3_fallbacks}          ",
            flush=True,
        )

        templates_file = os.path.join(self.outdir, f"{logName}_templates.csv")
        templates_rows = [
            {"EventId": eid, "EventTemplate": tpl, "Occurrences": count}
            for eid, (tpl, count) in template_counts.items()
        ]
        pd.DataFrame(templates_rows).to_csv(templates_file, index=False)

    def _flush_batch(self, batch_lines, batch_meta, writer, template_counts):
        """发送一批并写入 CSV。"""
        entries = self._send_batch(batch_lines)

        for i, (line_id, fields, content) in enumerate(batch_meta):
            if i < len(entries):
                entry = entries[i]
                event_template = entry.get("template") or content
            else:
                event_template = content

            event_id = self._compute_event_id(event_template)

            row = {"LineId": line_id}
            for h in self.headers:
                if h != "Content":
                    row[h] = fields.get(h, "")
            row["Content"] = content
            row["EventId"] = event_id
            row["EventTemplate"] = event_template
            writer.writerow(row)

            if event_id in template_counts:
                tpl, count = template_counts[event_id]
                template_counts[event_id] = (tpl, count + 1)
            else:
                template_counts[event_id] = (event_template, 1)

    def _send_batch(self, lines: List[str]) -> List[Dict]:
        """发送一批日志行到 API，返回 entries 列表。"""
        text = "\n".join(lines)
        url = f"{self.api_base}/diagnose/lilac/parse_text"

        payload = {"text": text}
        if self.api_regex:
            payload["regex"] = self.api_regex

        try:
            resp = requests.post(url, json=payload, timeout=300)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 200:
                return [{}] * len(lines)

            result = data.get("data", {})
            self.total_cache_hits += result.get("cache_hits", 0)
            self.total_llm_calls += result.get("llm_calls", 0)
            self.total_drain3_fallbacks += result.get("drain3_fallbacks", 0)

            return result.get("entries", [])

        except requests.RequestException as e:
            print(f"\n    [WARN] API request failed: {e}")
            return [{}] * len(lines)

    def _check_server(self) -> None:
        """检查 LILAC 服务是否就绪。"""
        url = f"{self.api_base}/diagnose/lilac/cache/stats"
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(
                f"LILAC server not reachable at {self.api_base}: {e}\n"
                f"Start it with: LILAC_ENABLE_LLM=false python run_server.py"
            )

    def _clear_cache(self) -> None:
        """清空服务端缓存。"""
        url = f"{self.api_base}/diagnose/lilac/cache"
        try:
            resp = requests.delete(url, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    [WARN] Failed to clear cache: {e}")

    def get_cache_stats(self) -> Dict:
        """获取服务端缓存统计。"""
        url = f"{self.api_base}/diagnose/lilac/cache/stats"
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {})
        except requests.RequestException:
            return {}

    def _write_results(self, rows: List[Dict], logName: str) -> None:
        """写入 structured.csv 和 templates.csv。"""
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

    @staticmethod
    def _compute_event_id(template: str) -> str:
        """MD5 前 8 字符作为 EventId"""
        return hashlib.md5(template.encode("utf-8")).hexdigest()[:8]
