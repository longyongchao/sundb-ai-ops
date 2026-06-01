"""Loghub-2.0 评测指标计算

指标定义:
- GA  (Grouping Accuracy): 日志分组正确率
- FGA (F1-Grouping Accuracy): 分组精度与召回的 F1
- PA  (Parsing Accuracy): 逐行模板精确匹配率
- PTA (Precision Template Accuracy): 正确识别的模板 / 总识别模板数
- RTA (Recall Template Accuracy): 正确识别的模板 / ground truth 模板数
- FTA (F1 Template Accuracy): PTA 和 RTA 的调和平均
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class EvalResult:
    """单数据集评测结果"""
    dataset: str
    ga: float = 0.0
    fga: float = 0.0
    pa: float = 0.0
    pta: float = 0.0
    rta: float = 0.0
    fta: float = 0.0
    n_logs: int = 0
    n_templates_parsed: int = 0
    n_templates_truth: int = 0


def compute_ga(parsed_templates: List[str], truth_templates: List[str]) -> float:
    """Grouping Accuracy: 检查同一 ground truth 模板下的日志是否被分到同一组。"""
    if not truth_templates:
        return 0.0

    n = len(truth_templates)
    truth_to_indices = defaultdict(set)
    parsed_to_indices = defaultdict(set)

    for i, t in enumerate(truth_templates):
        truth_to_indices[t].add(i)
    for i, t in enumerate(parsed_templates):
        parsed_to_indices[t].add(i)

    correct = 0
    for truth_group in truth_to_indices.values():
        # 对于每个 ground truth 组，检查 parsed 是否将组内日志分到同一个模板
        parsed_groups_for_truth = defaultdict(int)
        for idx in truth_group:
            if idx < len(parsed_templates):
                parsed_groups_for_truth[parsed_templates[idx]] += 1

        if parsed_groups_for_truth:
            max_overlap = max(parsed_groups_for_truth.values())
            if max_overlap == len(truth_group):
                # 该组所有日志被映射到同一个 parsed template
                # 还需检查该 parsed template 是否只包含该组的日志
                best_parsed = max(parsed_groups_for_truth, key=parsed_groups_for_truth.get)
                if parsed_to_indices[best_parsed] == truth_group:
                    correct += len(truth_group)

    return correct / n if n > 0 else 0.0


def compute_fga(parsed_templates: List[str], truth_templates: List[str]) -> float:
    """F1-Grouping Accuracy: 基于 precision/recall 的分组评估。"""
    if not truth_templates:
        return 0.0

    n = len(truth_templates)
    truth_to_indices = defaultdict(set)
    parsed_to_indices = defaultdict(set)

    for i, t in enumerate(truth_templates):
        truth_to_indices[t].add(i)
    for i, t in enumerate(parsed_templates):
        parsed_to_indices[t].add(i)

    # Precision: 对每个 parsed 组，最大重叠 / 组大小
    precision_sum = 0.0
    for parsed_group in parsed_to_indices.values():
        max_overlap = 0
        for truth_group in truth_to_indices.values():
            overlap = len(parsed_group & truth_group)
            max_overlap = max(max_overlap, overlap)
        precision_sum += max_overlap

    # Recall: 对每个 truth 组，最大重叠 / 组大小
    recall_sum = 0.0
    for truth_group in truth_to_indices.values():
        max_overlap = 0
        for parsed_group in parsed_to_indices.values():
            overlap = len(truth_group & parsed_group)
            max_overlap = max(max_overlap, overlap)
        recall_sum += max_overlap

    precision = precision_sum / n if n > 0 else 0.0
    recall = recall_sum / n if n > 0 else 0.0

    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def compute_pa(parsed_templates: List[str], truth_templates: List[str]) -> float:
    """Parsing Accuracy: 逐行模板精确匹配率。"""
    if not truth_templates:
        return 0.0

    correct = sum(
        1 for p, t in zip(parsed_templates, truth_templates)
        if _normalize_template(p) == _normalize_template(t)
    )
    return correct / len(truth_templates)


def compute_template_level(
    parsed_templates: List[str], truth_templates: List[str]
) -> Dict[str, float]:
    """计算 PTA, RTA, FTA。

    PTA = 被正确识别的模板数 / 总识别模板数
    RTA = 被正确识别的模板数 / ground truth 模板数
    """
    parsed_unique = set(_normalize_template(t) for t in parsed_templates)
    truth_unique = set(_normalize_template(t) for t in truth_templates)

    # 建立 truth template → 对应日志行的映射
    truth_template_to_lines = defaultdict(set)
    parsed_template_to_lines = defaultdict(set)

    for i, t in enumerate(truth_templates):
        truth_template_to_lines[_normalize_template(t)].add(i)
    for i, t in enumerate(parsed_templates):
        parsed_template_to_lines[_normalize_template(t)].add(i)

    # 一个 parsed template 是 "正确的" 如果它与某个 truth template 关联的日志行完全一致
    correctly_identified = set()
    for pt, pt_lines in parsed_template_to_lines.items():
        for tt, tt_lines in truth_template_to_lines.items():
            if pt_lines == tt_lines:
                correctly_identified.add(pt)
                break

    n_correct = len(correctly_identified)
    n_parsed = len(parsed_unique)
    n_truth = len(truth_unique)

    pta = n_correct / n_parsed if n_parsed > 0 else 0.0
    rta = n_correct / n_truth if n_truth > 0 else 0.0
    fta = 2 * pta * rta / (pta + rta) if (pta + rta) > 0 else 0.0

    return {"pta": pta, "rta": rta, "fta": fta}


def _normalize_template(template: str) -> str:
    """模板归一化：统一空白、去除首尾空格。"""
    return " ".join(template.split())


def evaluate_dataset(
    parsed_csv: str,
    groundtruth_csv: str,
    dataset_name: str = "",
) -> EvalResult:
    """评测单个数据集。

    Args:
        parsed_csv: LILAC 输出的 structured.csv 路径
        groundtruth_csv: ground truth 的 *_structured_corrected.csv 路径
        dataset_name: 数据集名称
    """
    parsed_df = pd.read_csv(parsed_csv)
    truth_df = pd.read_csv(groundtruth_csv)

    parsed_templates = parsed_df["EventTemplate"].astype(str).tolist()
    truth_templates = truth_df["EventTemplate"].astype(str).tolist()

    # 确保长度一致
    min_len = min(len(parsed_templates), len(truth_templates))
    parsed_templates = parsed_templates[:min_len]
    truth_templates = truth_templates[:min_len]

    ga = compute_ga(parsed_templates, truth_templates)
    fga = compute_fga(parsed_templates, truth_templates)
    pa = compute_pa(parsed_templates, truth_templates)
    tl = compute_template_level(parsed_templates, truth_templates)

    return EvalResult(
        dataset=dataset_name,
        ga=ga,
        fga=fga,
        pa=pa,
        pta=tl["pta"],
        rta=tl["rta"],
        fta=tl["fta"],
        n_logs=min_len,
        n_templates_parsed=parsed_df["EventId"].nunique() if not parsed_df.empty else 0,
        n_templates_truth=truth_df["EventId"].nunique() if not truth_df.empty else 0,
    )
