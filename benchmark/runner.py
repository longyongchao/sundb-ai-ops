"""Loghub-2.0 Benchmark Runner for LILAC

用法:
    python -m benchmark.runner --mode 2k --datasets all --no-llm
    python -m benchmark.runner --mode 2k --datasets Hadoop,HDFS --enable-llm
    python -m benchmark.runner --mode full --datasets all --enable-llm --reset-cache
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
from benchmark.lilac_adapter import LilacLoghubAdapter
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
    parser.add_argument("--no-drain3", action="store_true", default=False, help="同时禁用 Drain3")
    parser.add_argument("--reset-cache", action="store_true", help="每个数据集前清空缓存")
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
        "--similarity-threshold",
        type=float,
        default=0.85,
        help="LILAC cache 相似度阈值 (default: 0.85)",
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
    cache_dir = os.path.join(output_dir, "cache")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    enable_llm = args.enable_llm and not args.no_llm
    enable_drain3 = not args.no_drain3
    mode_label = "llm" if enable_llm else "nollm"

    datasets = get_datasets(args)
    results: List[EvalResult] = []
    total_time = 0.0

    print(f"\n{'='*60}")
    print(f"  LILAC Loghub-2.0 Benchmark")
    print(f"  Mode: {args.mode} | LLM: {enable_llm} | Drain3: {enable_drain3}")
    print(f"  Datasets: {len(datasets)} | Similarity: {args.similarity_threshold}")
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

        # 独立缓存
        cache_path = os.path.join(cache_dir, f"{dataset}_{mode_label}.db")
        if args.reset_cache and os.path.exists(cache_path):
            os.remove(cache_path)

        print(f"  [{dataset}] Parsing...", end=" ", flush=True)
        start = time.time()

        indir = os.path.join(data_dir, os.path.dirname(log_file))
        log_name = os.path.basename(log_file)
        result_dir = os.path.join(output_dir, f"lilac_{mode_label}_{args.mode}")

        adapter = LilacLoghubAdapter(
            log_format=setting["log_format"],
            indir=indir,
            outdir=result_dir,
            rex=setting["regex"],
            cache_db_path=cache_path,
            enable_llm=enable_llm,
            enable_drain3=enable_drain3,
            similarity_threshold=args.similarity_threshold,
            drain_depth=setting.get("depth", 4),
            drain_sim_th=setting.get("st", 0.5),
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

        # 输出详细 JSON
        summary = {
            "mode": args.mode,
            "llm_enabled": enable_llm,
            "drain3_enabled": enable_drain3,
            "similarity_threshold": args.similarity_threshold,
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
