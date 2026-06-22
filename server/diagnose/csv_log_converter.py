#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CSV 日志转换器

将任意结构的 CSV 日志文件自动识别列角色，
转换为 LILAC 预处理器可解析的标准 .log 文本格式：

  {timestamp} {level} {message}  [其余列追加在消息后]

列角色推断策略：
  - 完全基于"打分制"，值分析权重高于列名分析
  - 不依赖任何固定字段名（不针对特定系统或业务）
  - 每列独立计算 timestamp / level / message 得分
  - 得分最高且互不重叠的列被分别选为对应角色
"""

import csv
import io
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================

# 已知日志级别集合（含业务状态伪级别）
_KNOWN_LEVELS = {
    # 标准日志级别
    "trace", "debug", "info", "information", "notice",
    "warn", "warning", "error", "err", "fatal",
    "critical", "severe", "alert", "emerg",
    # 业务状态伪级别（SUCCEED/FAILED 等各系统均可能出现）
    "succeed", "success", "ok", "pass", "passed",
    "fail", "failed", "failure", "exception",
    "timeout", "cancelled", "canceled", "rejected",
    "pending", "running", "done", "skipped",
    "normal", "abnormal", "healthy", "unhealthy",
}

_LEVEL_NORMALIZE = {
    "info": "INFO", "information": "INFO", "notice": "INFO",
    "normal": "INFO", "healthy": "INFO",
    "debug": "DEBUG", "trace": "TRACE",
    "warn": "WARNING", "warning": "WARNING",
    "timeout": "WARNING", "cancelled": "WARNING",
    "canceled": "WARNING", "rejected": "WARNING",
    "abnormal": "WARNING", "unhealthy": "WARNING",
    "error": "ERROR", "err": "ERROR",
    "fail": "ERROR", "failed": "ERROR", "failure": "ERROR",
    "exception": "ERROR",
    "fatal": "FATAL", "critical": "FATAL",
    "severe": "FATAL", "alert": "FATAL", "emerg": "FATAL",
    # 通用正向状态 → INFO
    "succeed": "INFO", "success": "INFO", "ok": "INFO",
    "pass": "INFO", "passed": "INFO", "done": "INFO",
    "running": "INFO", "pending": "INFO", "skipped": "INFO",
}

# 日期时间正则（宽松版：月/日/小时允许1-2位，支持 / - 分隔符）
_RE_DATETIME = re.compile(
    r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}'
    r'(?:[T \t]\d{1,2}:\d{2}(?::\d{2})?)?'
    r'(?:[.,]\d+)?'
    r'(?:Z|[+-]\d{2}:?\d{2})?$'
)
# Unix 时间戳：整数或浮点，10-13 位整数部分（秒/毫秒）
_RE_EPOCH = re.compile(r'^\d{10,13}(\.\d+)?$')
_RE_PURE_NUMBER = re.compile(r'^-?\d+(\.\d+)?$')  # 纯数字


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ColumnSchema:
    """CSV 列角色推断结果"""
    timestamp_col: Optional[str] = None
    level_col: Optional[str] = None
    message_col: Optional[str] = None
    extra_cols: List[str] = field(default_factory=list)


@dataclass
class ColumnFeatures:
    """单列特征（用于打分）"""
    name: str
    ts_value_ratio: float       # 值命中 datetime 的比例
    level_value_ratio: float    # 值命中 known_levels 的比例
    numeric_ratio: float        # 值为纯数字的比例
    avg_text_len: float         # 非空值平均字符长度
    cardinality: int            # 唯一值数量
    total_non_empty: int        # 非空值总数


@dataclass
class ConversionResult:
    """转换结果"""
    log_text: str
    schema: ColumnSchema
    total_rows: int
    converted_rows: int
    warnings: List[str] = field(default_factory=list)
    row_mapping: List[int] = field(default_factory=list)
    csv_rows: List[Dict[str, str]] = field(default_factory=list)


# ============================================================
# 核心转换器
# ============================================================

class CsvLogConverter:
    """CSV 日志 → 标准 .log 文本转换器（自动推断列角色）"""

    def __init__(self, sample_rows: int = 50):
        """
        :param sample_rows: 用于推断列角色的采样行数（越多越准确）
        """
        self._sample_rows = sample_rows

    # ----------------------------------------------------------
    # 公共接口
    # ----------------------------------------------------------

    def convert_file(self, path: str, encoding: str = "utf-8") -> ConversionResult:
        """从文件路径读取并转换"""
        try:
            with open(path, "r", encoding=encoding, errors="replace", newline="") as f:
                text = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"CSV 文件不存在: {path}")
        return self.convert_text(text)

    def convert_text(self, csv_text: str) -> ConversionResult:
        """从 CSV 文本内容转换"""
        warnings: List[str] = []
        dialect, rows, headers = self._read_csv(csv_text)
        if not rows:
            return ConversionResult(
                log_text="", schema=ColumnSchema(),
                total_rows=0, converted_rows=0,
                warnings=["CSV 内容为空或无法解析"],
            )

        sample = rows[:self._sample_rows]
        schema = self._infer_schema(headers, sample, warnings)

        log_lines: List[str] = []
        row_mapping: List[int] = []
        converted = 0
        for idx, row in enumerate(rows):
            line = self._row_to_log_line(row, schema)
            if line:
                log_lines.append(line)
                row_mapping.append(idx)
                converted += 1

        return ConversionResult(
            log_text="\n".join(log_lines),
            schema=schema,
            total_rows=len(rows),
            converted_rows=converted,
            warnings=warnings,
            row_mapping=row_mapping,
            csv_rows=rows,
        )

    def schema_only(self, csv_text: str) -> Tuple[ColumnSchema, List[str]]:
        """仅推断列角色，不执行转换（供预览/调试）"""
        warnings: List[str] = []
        _, rows, headers = self._read_csv(csv_text)
        if not rows:
            return ColumnSchema(), ["CSV 内容为空"]
        schema = self._infer_schema(headers, rows[:self._sample_rows], warnings)
        return schema, warnings

    # ----------------------------------------------------------
    # CSV 读取
    # ----------------------------------------------------------

    @staticmethod
    def _read_csv(text: str) -> Tuple[csv.Dialect, List[Dict[str, str]], List[str]]:
        """读取 CSV，自动检测分隔符"""
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        try:
            headers = reader.fieldnames or []
            rows = [dict(row) for row in reader]
        except Exception as exc:
            logger.warning(f"[CSV] 读取失败: {exc}")
            return dialect, [], []

        return dialect, rows, list(headers)

    # ----------------------------------------------------------
    # 列特征提取
    # ----------------------------------------------------------

    @staticmethod
    def _extract_features(col: str, rows: List[Dict[str, str]]) -> ColumnFeatures:
        """计算单列的统计特征"""
        values = [row.get(col, "") for row in rows]
        non_empty = [v.strip() for v in values if v and v.strip()]
        total = len(non_empty)

        if total == 0:
            return ColumnFeatures(
                name=col, ts_value_ratio=0, level_value_ratio=0,
                numeric_ratio=0, avg_text_len=0, cardinality=0, total_non_empty=0,
            )

        ts_hits = sum(1 for v in non_empty
                      if _RE_DATETIME.match(v) or _RE_EPOCH.match(v))
        level_hits = sum(1 for v in non_empty if v.lower() in _KNOWN_LEVELS)
        numeric_hits = sum(1 for v in non_empty if _RE_PURE_NUMBER.match(v))
        avg_len = sum(len(v) for v in non_empty) / total
        cardinality = len(set(v.lower() for v in non_empty))

        return ColumnFeatures(
            name=col,
            ts_value_ratio=ts_hits / total,
            level_value_ratio=level_hits / total,
            numeric_ratio=numeric_hits / total,
            avg_text_len=avg_len,
            cardinality=cardinality,
            total_non_empty=total,
        )

    # ----------------------------------------------------------
    # 打分函数
    # ----------------------------------------------------------

    @staticmethod
    def _score_timestamp(feat: ColumnFeatures) -> float:
        """计算列作为时间戳的得分（值分析权重 >> 列名权重）"""
        # 空列不参与时间戳竞争
        if feat.total_non_empty == 0:
            return 0.0

        score = 0.0
        col_lower = feat.name.lower()

        # === 值分析（主要依据）===
        if feat.ts_value_ratio >= 0.8:
            score += 8.0
        elif feat.ts_value_ratio >= 0.5:
            score += 4.0
        elif feat.ts_value_ratio >= 0.2:
            score += 1.0

        # 纯数字列但不是 epoch 格式 → 不是时间戳（如耗时秒数）
        if feat.numeric_ratio > 0.9 and feat.ts_value_ratio < 0.5:
            score -= 5.0

        # === 列名分析（辅助，只用通用词，不写死任何具体字段名）===
        generic_ts_suffixes = (
            "_time", "_date", "_at", "_ts", "_datetime",
            "_stamp", "_timestamp", "_created", "_modified", "_updated",
        )
        generic_ts_exact = {"time", "date", "ts", "timestamp", "datetime"}
        # 前缀匹配：列名以时间相关词开头（如 timestamp_anon、ts_start 等）
        generic_ts_prefixes = ("timestamp", "ts_", "date_", "time_")

        if col_lower in generic_ts_exact:
            score += 2.0
        elif any(col_lower.endswith(sfx) for sfx in generic_ts_suffixes):
            score += 2.0
        elif any(col_lower.startswith(pfx) for pfx in generic_ts_prefixes):
            score += 1.5
        # "time"/"date" 包含在列名中间（如 exec_time_seconds）→ 只有值也命中才加分
        elif "time" in col_lower or "date" in col_lower:
            if feat.ts_value_ratio >= 0.5:
                score += 1.0

        return score

    @staticmethod
    def _score_level(feat: ColumnFeatures) -> float:
        """计算列作为日志级别的得分"""
        score = 0.0
        col_lower = feat.name.lower()

        # === 值分析（主要依据）===
        if feat.level_value_ratio >= 0.8:
            score += 8.0
        elif feat.level_value_ratio >= 0.5:
            score += 4.0
        elif feat.level_value_ratio >= 0.2:
            score += 1.0

        # 低基数是级别列的特征——但必须有至少一定的值命中，
        # 否则 gpu_model/job_type 等低基数分类列会被误判
        if feat.level_value_ratio > 0 and feat.total_non_empty >= 5:
            if feat.cardinality <= 10:
                score += 1.0
            if feat.cardinality <= 5:
                score += 1.0

        # 纯数字列不是级别列
        if feat.numeric_ratio > 0.9:
            score -= 5.0

        # === 列名分析（辅助）===
        # 精确匹配：level, severity, priority, grade
        exact_level_names = {"level", "severity", "priority", "grade", "loglevel", "log_level"}
        # 包含匹配：列名含有以下词（但不误伤 exec_time 等）
        level_keywords = ("level", "severity", "priority", "grade")

        if col_lower in exact_level_names:
            score += 2.0
        elif any(kw in col_lower for kw in level_keywords):
            score += 1.5
        # "status" 作为弱信号：列名含 status 时，仅在值命中时才加分
        elif "status" in col_lower and feat.level_value_ratio >= 0.5:
            score += 1.0

        return score

    @staticmethod
    def _score_message(feat: ColumnFeatures, max_avg_len: float) -> float:
        """计算列作为消息体的得分"""
        score = 0.0
        col_lower = feat.name.lower()

        # === 列名分析（消息列主要靠列名）===
        exact_msg_names = {"message", "msg", "log", "content", "text", "body",
                           "description", "detail", "event", "payload", "remark",
                           "comment", "summary", "info", "note", "reason"}
        msg_keywords = ("message", "msg", "content", "text", "body",
                        "description", "detail", "event", "payload")

        if col_lower in exact_msg_names:
            score += 5.0
        elif any(kw in col_lower for kw in msg_keywords):
            score += 3.0

        # === 值分析（辅助）===
        # 文本越长越可能是消息
        if max_avg_len > 0:
            relative_len = feat.avg_text_len / max_avg_len
            score += relative_len * 2.0  # 最多 +2

        # 高基数（每行内容各不同）是消息列的特征
        if feat.cardinality >= feat.total_non_empty * 0.5:
            score += 1.0

        # 纯数字列不是消息列
        if feat.numeric_ratio > 0.9:
            score -= 5.0

        # datetime 列不是消息列
        if feat.ts_value_ratio >= 0.5:
            score -= 3.0

        # 已知级别列不是消息列
        if feat.level_value_ratio >= 0.5:
            score -= 3.0

        return score

    # ----------------------------------------------------------
    # 列角色推断（打分制）
    # ----------------------------------------------------------

    def _infer_schema(
        self,
        headers: List[str],
        sample_rows: List[Dict[str, str]],
        warnings: List[str],
    ) -> ColumnSchema:
        """对所有列打分，选出互不重叠的最优组合"""

        # 1. 提取所有列的特征
        features: Dict[str, ColumnFeatures] = {
            col: self._extract_features(col, sample_rows)
            for col in headers
        }

        max_avg_len = max((f.avg_text_len for f in features.values()), default=1.0)
        if max_avg_len == 0:
            max_avg_len = 1.0

        # 2. 计算各列三个角色的得分
        ts_scores: Dict[str, float] = {}
        level_scores: Dict[str, float] = {}
        msg_scores: Dict[str, float] = {}

        for col, feat in features.items():
            ts_scores[col] = self._score_timestamp(feat)
            level_scores[col] = self._score_level(feat)
            msg_scores[col] = self._score_message(feat, max_avg_len)

        # 3. 按得分排序，贪心分配（高分优先，已分配的列不再参与其他角色）
        assigned: set = set()

        def pick_best(scores: Dict[str, float], min_score: float = 0.5) -> Optional[str]:
            ranked = sorted(
                ((s, c) for c, s in scores.items() if c not in assigned),
                reverse=True,
            )
            if ranked and ranked[0][0] >= min_score:
                return ranked[0][1]
            return None

        schema = ColumnSchema()

        # 时间戳优先分配（通常特征最明显）
        schema.timestamp_col = pick_best(ts_scores, min_score=1.0)
        if schema.timestamp_col:
            assigned.add(schema.timestamp_col)

        # 级别列
        schema.level_col = pick_best(level_scores, min_score=1.0)
        if schema.level_col:
            assigned.add(schema.level_col)

        # 消息列（min_score 更低，因为很多 CSV 没有 message 字段）
        schema.message_col = pick_best(msg_scores, min_score=0.5)
        if schema.message_col:
            assigned.add(schema.message_col)

        # 剩余列归为 extra
        schema.extra_cols = [c for c in headers if c not in assigned]

        # 4. 记录日志（含各列得分，便于调试）
        score_summary = {
            col: {
                "ts": round(ts_scores[col], 2),
                "lv": round(level_scores[col], 2),
                "msg": round(msg_scores[col], 2),
            }
            for col in headers
        }
        logger.info(
            f"[CSV] 列角色推断 → timestamp={schema.timestamp_col}, "
            f"level={schema.level_col}, message={schema.message_col}, "
            f"extra={schema.extra_cols}"
        )
        logger.debug(f"[CSV] 各列得分: {score_summary}")

        # 5. 警告
        if schema.timestamp_col is None:
            warnings.append("未找到时间戳列，转换行将无时间前缀")
        if schema.level_col is None:
            warnings.append("未找到日志级别列，将使用 INFO 作为默认级别")
        if schema.message_col is None:
            warnings.append("未找到消息主体列，将拼接所有非空列值作为消息")

        return schema

    # ----------------------------------------------------------
    # 行转换
    # ----------------------------------------------------------

    def _row_to_log_line(self, row: Dict[str, str], schema: ColumnSchema) -> str:
        """将单行 CSV 数据转换为一行 log 文本

        输出格式（与 LILAC 预处理器 iso_level 规则对应）：
          {timestamp} {level} {message} [extra_key=extra_val ...]
        """
        # 时间戳
        ts = ""
        if schema.timestamp_col:
            ts = self._normalize_timestamp(row.get(schema.timestamp_col, "").strip())

        # 级别
        level = "INFO"
        if schema.level_col:
            raw_level = row.get(schema.level_col, "").strip()
            level = _LEVEL_NORMALIZE.get(raw_level.lower(), raw_level.upper() or "INFO")

        # 消息主体
        if schema.message_col:
            message = row.get(schema.message_col, "").strip()
            # extra 列追加（key=value 形式）
            extra_parts = []

            # 若 level 列的原始值是业务状态词（非标准日志级别），保留在消息中
            # 例如 predict_status=SUCCEED → 追加到 extra，避免信息丢失
            _STANDARD_LEVELS = {
                "trace", "debug", "info", "warn", "warning",
                "error", "err", "fatal", "critical",
            }
            if schema.level_col:
                raw_level_val = row.get(schema.level_col, "").strip()
                if raw_level_val and raw_level_val.lower() not in _STANDARD_LEVELS:
                    extra_parts.append(f"{schema.level_col}={raw_level_val}")

            extra_parts += [
                f"{col}={row.get(col, '').strip()}"
                for col in schema.extra_cols
                if row.get(col, "").strip()
            ]
            if extra_parts:
                message = f"{message} [{' '.join(extra_parts)}]"
        else:
            # 无 message 列：全列拼接，extra 不再重复追加
            message = " | ".join(
                f"{k}={v}" for k, v in row.items() if v and v.strip()
            )

        if not message:
            return ""

        return f"{ts} {level} {message}".lstrip() if ts else f"{level} {message}"

    # ----------------------------------------------------------
    # 时间戳规范化
    # ----------------------------------------------------------

    @staticmethod
    def _normalize_timestamp(raw: str) -> str:
        """将时间戳规范化为 LILAC 预处理器可识别的 YYYY-MM-DD HH:MM:SS"""
        if not raw:
            return ""

        if _RE_DATETIME.match(raw):
            ts = raw.replace("T", " ").replace("t", " ")
            ts = re.sub(r'[Zz]$', '', ts)
            ts = re.sub(r'[+-]\d{2}:?\d{2}$', '', ts)
            ts = re.sub(r'/', '-', ts)
            ts = ts.strip()

            # 月/日补零：2024-1-5 → 2024-01-05
            ts = re.sub(
                r'^(\d{4})-(\d{1,2})-(\d{1,2})',
                lambda m: (
                    f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
                ),
                ts,
            )
            # 小时补零：空格后单位数小时 4:44 → 04:44
            ts = re.sub(
                r' (\d):(\d{2})',
                lambda m: f" 0{m.group(1)}:{m.group(2)}",
                ts,
            )
            # 补全秒：仅当时间部分是 HH:MM（无秒）时才补 :00
            if not re.search(r'\d{2}:\d{2}:\d{2}', ts) and re.search(r'\d{2}:\d{2}$', ts):
                ts += ":00"
            return ts

        # Unix epoch（整数或浮点）→ datetime
        if _RE_EPOCH.match(raw):
            import datetime
            try:
                epoch = float(raw)
                if epoch > 1e12:   # 毫秒级
                    epoch /= 1000
                dt = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                return raw

        return raw
