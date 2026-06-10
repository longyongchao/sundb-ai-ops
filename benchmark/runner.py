"""Loghub-2.0 Benchmark Runner for LILAC (API Mode)

用法:
    python -m benchmark.runner --mode 2k --datasets all --no-llm
    python -m benchmark.runner --mode 2k --datasets Hadoop,HDFS --enable-llm
    python -m benchmark.runner --mode full --datasets all --enable-llm --reset-cache
    python -m benchmark.runner --mode full --datasets all --api-base http://10.0.0.1:7861
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark.evaluator import EvalResult, evaluate_dataset
from benchmark.lilac_api_adapter import LilacApiAdapter
from benchmark.loghub_settings import DATASETS_2K, DATASETS_FULL, benchmark_settings


def parse_args():
    parser = argparse.ArgumentParser(description="LILAC Loghub-2.0 Benchmark Runner")
    parser.add_argument(
        "--mode", choices=["2k", "full"], default="2k", help="数据集规模 (default: 2k)"
    )
    parser.add_argument(
        "--datasets",
        default="all",
        help="逗号分隔的数据集列表，或 'all' (default: all)",
    )
    parser.add_argument("--enable-llm", action="store_true", default=False, help="启用 LLM 模板提取")
    parser.add_argument("--no-llm", action="store_true", default=False, help="禁用 LLM (仅 cache+Drain3)")
    parser.add_argument("--reset-cache", action="store_true", help="每个数据集前清空服务端缓存")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="数据集根目录 (default: benchmark/datasets/{mode}_dataset/)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="结果输出目录 (default: benchmark/results/)",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:7861",
        help="LILAC API 地址 (default: http://localhost:7861)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="每批发送行数 (default: 10000)",
    )
    return parser.parse_args()


def get_datasets(args) -> List[str]:
    if args.datasets == "all":
        return DATASETS_2K if args.mode == "2k" else DATASETS_FULL
    return [d.strip() for d in args.datasets.split(",")]


def run_benchmark(args):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    benchmark_dir = os.path.join(base_dir, "benchmark")

    data_dir = args.data_dir or os.path.join(benchmark_dir, "datasets", f"{args.mode}_dataset")
    output_dir = args.output_dir or os.path.join(benchmark_dir, "results")
    os.makedirs(output_dir, exist_ok=True)

    enable_llm = args.enable_llm and not args.no_llm
    mode_label = "api_llm" if enable_llm else "api_nollm"

    datasets = get_datasets(args)
    results: List[EvalResult] = []
    total_time = 0.0

    print(f"\n{'='*60}")
    print(f"  LILAC Loghub-2.0 Benchmark (API Mode)")
    print(f"  Mode: {args.mode} | LLM: {enable_llm} | Datasets: {len(datasets)}")
    print(f"  API: {args.api_base} | Batch: {args.batch_size}")
    print(f"{'='*60}\n")

    for dataset in datasets:
        if dataset not in benchmark_settings:
            print(f"  [SKIP] Unknown dataset: {dataset}")
            continue

        setting = benchmark_settings[dataset]
        log_file = setting["log_file"].replace("{mode}", args.mode)
        log_path = os.path.join(data_dir, log_file)

        if not os.path.exists(log_path):
            print(f"  [SKIP] {dataset}: file not found: {log_path}")
            continue

        print(f"  [{dataset}] Parsing...", end=" ", flush=True)
        start = time.time()

        indir = os.path.join(data_dir, os.path.dirname(log_file))
        log_name = os.path.basename(log_file)
        result_dir = os.path.join(output_dir, f"lilac_{mode_label}_{args.mode}")

        adapter = LilacApiAdapter(
            log_format=setting["log_format"],
            indir=indir,
            outdir=result_dir,
            rex=setting["regex"],
            api_base=args.api_base,
            batch_size=args.batch_size,
            reset_cache=args.reset_cache,
        )

        try:
            adapter.parse(log_name)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        elapsed = time.time() - start
        total_time += elapsed
        print(f"{elapsed:.1f}s", end="")

        # 评测
        structured_csv = os.path.join(result_dir, f"{log_name}_structured.csv")
        groundtruth_csv = os.path.join(
            indir, f"{log_name}_structured_corrected.csv"
        )
        if not os.path.exists(groundtruth_csv):
            groundtruth_csv = os.path.join(indir, f"{log_name}_structured.csv")

        if os.path.exists(groundtruth_csv):
            try:
                result = evaluate_dataset(structured_csv, groundtruth_csv, dataset)
                results.append(result)
                print(
                    f" | GA={result.ga:.3f} PA={result.pa:.3f} FTA={result.fta:.3f}"
                )
                # 每个数据集单独保存 JSON（含详细统计）
                per_ds_dir = os.path.join(output_dir, f"per_dataset_{mode_label}_{args.mode}")
                os.makedirs(per_ds_dir, exist_ok=True)
                per_ds_path = os.path.join(per_ds_dir, f"{dataset}.json")
                file_size_bytes = os.path.getsize(log_path)
                lines_per_sec = result.n_logs / elapsed if elapsed > 0 else 0
                import pandas as pd_check
                parsed_df = pd_check.read_csv(structured_csv)
                detail = {
                    **asdict(result),
                    "time_s": round(elapsed, 2),
                    "file_size_bytes": file_size_bytes,
                    "file_size_mb": round(file_size_bytes / 1048576, 2),
                    "lines_per_sec": round(lines_per_sec, 1),
                    "avg_log_length": round(parsed_df["Content"].astype(str).str.len().mean(), 1),
                    "max_log_length": int(parsed_df["Content"].astype(str).str.len().max()),
                    "min_log_length": int(parsed_df["Content"].astype(str).str.len().min()),
                    "template_ratio": round(result.n_templates_parsed / result.n_logs, 6) if result.n_logs > 0 else 0,
                    "over_parsed": result.n_templates_parsed - result.n_templates_truth,
                    "drain_depth": setting.get("depth", 4),
                    "drain_sim_th": setting.get("st", 0.5),
                    "mode": args.mode,
                    "llm_enabled": enable_llm,
                    "cache_hits": adapter.total_cache_hits,
                    "drain3_fallbacks": adapter.total_drain3_fallbacks,
                    "llm_calls": adapter.total_llm_calls,
                    "batch_size": args.batch_size,
                }
                with open(per_ds_path, "w") as f:
                    json.dump(detail, f, indent=2, ensure_ascii=False)
                # 大文件评测完成后删除中间 CSV 释放磁盘空间
                if result.n_logs > 500000:
                    templates_csv = os.path.join(result_dir, f"{log_name}_templates.csv")
                    for f_path in [structured_csv, templates_csv]:
                        if os.path.exists(f_path):
                            os.remove(f_path)
            except Exception as e:
                print(f" | Eval error: {e}")
        else:
            print(f" | No ground truth at: {groundtruth_csv}")

    # 汇总
    print(f"\n{'='*60}")
    if results:
        avg_ga = sum(r.ga for r in results) / len(results)
        avg_pa = sum(r.pa for r in results) / len(results)
        avg_fga = sum(r.fga for r in results) / len(results)
        avg_fta = sum(r.fta for r in results) / len(results)

        print(f"  Average ({len(results)} datasets):")
        print(f"    GA={avg_ga:.4f}  FGA={avg_fga:.4f}  PA={avg_pa:.4f}  FTA={avg_fta:.4f}")
        print(f"  Total time: {total_time:.1f}s")

        summary = {
            "mode": args.mode,
            "llm_enabled": enable_llm,
            "api_base": args.api_base,
            "batch_size": args.batch_size,
            "total_time_s": round(total_time, 2),
            "averages": {
                "GA": round(avg_ga, 4),
                "FGA": round(avg_fga, 4),
                "PA": round(avg_pa, 4),
                "FTA": round(avg_fta, 4),
            },
            "per_dataset": [asdict(r) for r in results],
        }
        summary_path = os.path.join(output_dir, f"summary_lilac_{mode_label}_{args.mode}.json")
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  Results saved to: {summary_path}")
    else:
        print("  No results. Check data-dir and dataset availability.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    args = parse_args()
    run_benchmark(args)
