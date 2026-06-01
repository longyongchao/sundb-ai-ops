# LILAC Loghub-2.0 Benchmark

使用 [Loghub-2.0](https://github.com/logpai/loghub-2.0)（ISSTA'24）标准评测框架验证 LILAC 日志解析精度。

## 数据集下载

从 Zenodo 下载数据集并解压到 `benchmark/datasets/` 目录：

```bash
# 2k 数据集（轻量，约 30MB，推荐首次验证使用）
wget https://zenodo.org/records/8275861/files/2k_dataset.tar.gz
tar -xzf 2k_dataset.tar.gz -C benchmark/datasets/

# full 数据集（约 965MB，14 个 zip 分别下载）
mkdir -p benchmark/datasets/full_dataset
cd benchmark/datasets/full_dataset
for ds in Apache BGL Hadoop HDFS HealthApp HPC Linux Mac OpenSSH OpenStack Proxifier Spark Thunderbird Zookeeper; do
    wget "https://zenodo.org/records/8275861/files/${ds}.zip"
    unzip "${ds}.zip"
    rm "${ds}.zip"
done
```

也可以直接在浏览器打开 https://zenodo.org/records/8275861 手动下载。

下载完成后目录结构应为：

```
benchmark/datasets/
├── 2k_dataset/
│   ├── Apache/
│   │   ├── Apache_2k.log
│   │   ├── Apache_2k.log_structured.csv
│   │   └── Apache_2k.log_structured_corrected.csv
│   ├── BGL/
│   └── ...（14 个数据集）
└── full_dataset/
    ├── Apache/
    │   ├── Apache_full.log
    │   └── Apache_full.log_structured.csv
    ├── BGL/
    └── ...（14 个数据集）
```

## 依赖安装

```bash
pip install drain3 pandas
```

## 运行评测

在项目根目录下执行：

```bash
# 快速验证：单个数据集，无 LLM（秒级完成）
python -m benchmark.runner --mode 2k --datasets Apache --no-llm

# 2k 全量评测，无 LLM
python -m benchmark.runner --mode 2k --datasets all --no-llm

# 2k 全量评测，启用 LLM（需配置 DEEPSEEK_API_KEY 环境变量）
python -m benchmark.runner --mode 2k --datasets all --enable-llm --reset-cache

# full 数据集评测
python -m benchmark.runner --mode full --datasets all --no-llm
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--mode 2k\|full` | 数据集规模（默认 2k） |
| `--datasets all\|Hadoop,HDFS,...` | 逗号分隔的数据集列表或 `all` |
| `--enable-llm` | 启用 LLM 模板提取（完整 LILAC 流水线） |
| `--no-llm` | 禁用 LLM，仅用 Drain3（基线对比） |
| `--reset-cache` | 每个数据集前清空 LILAC 缓存 |
| `--similarity-threshold` | LILAC cache 相似度阈值（默认 0.85） |
| `--data-dir` | 自定义数据集目录 |
| `--output-dir` | 自定义输出目录 |

## 输出结果

运行结束后在 `benchmark/results/` 生成：

- `summary_lilac_{nollm|llm}_{2k|full}.json` — 汇总 JSON（含每个数据集的 6 项指标）
- `lilac_{nollm|llm}_{2k|full}/` — 每个数据集的解析结果 CSV

## 评测指标

| 指标 | 含义 |
|------|------|
| GA | Grouping Accuracy — 日志分组正确率 |
| FGA | F1-weighted Grouping Accuracy |
| PA | Parsing Accuracy — 模板精确匹配率 |
| PTA | Precision Template Accuracy |
| RTA | Recall Template Accuracy |
| FTA | F1 Template Accuracy |

## 运行测试

```bash
pytest tests/benchmark/ -v
```
