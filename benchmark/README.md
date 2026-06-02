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
| `--no-drain3` | 同时禁用 Drain3 |
| `--reset-cache` | 每个数据集前清空 LILAC 缓存 |
| `--similarity-threshold` | LILAC cache 相似度阈值（默认 0.85） |
| `--data-dir` | 自定义数据集目录 |
| `--output-dir` | 自定义输出目录 |
| `--via-api` | 通过 HTTP API 调用 LILAC 服务（评测生产环境行为） |
| `--api-base` | LILAC API 地址（默认 `http://localhost:7861`） |
| `--batch-size` | API 模式每批发送行数（默认 10000） |

## 通过 API 评测（生产环境模式）

`--via-api` 模式通过 HTTP 调用 LILAC REST API 评测，反映真实生产环境行为：

- Cache 在批次间持续生效 — 重复日志模式直接命中缓存
- 完整流水线: caller regex → MASK_PATTERNS → cache → Drain3/LLM
- 在线解析 — 模板随处理进度演化（与离线 benchmark 行为有固有差异）

### 前置条件

启动 LILAC 后端服务：

```bash
# Drain3 模式（无 LLM）
LILAC_ENABLE_LLM=false LILAC_ENABLE_DRAIN3=true python3 run_server.py

# 完整流水线（LLM + Cache + Drain3）
LILAC_ENABLE_LLM=true LILAC_ENABLE_DRAIN3=true python3 run_server.py
```

确认服务就绪：

```bash
curl -s http://localhost:7861/diagnose/lilac/cache/stats
```

### 运行 API 评测

```bash
# 单数据集快速验证
python3 -m benchmark.runner --mode 2k --datasets Apache --via-api --no-llm

# full 全量评测（Drain3 模式）
python3 -m benchmark.runner --mode full --datasets all --via-api --no-llm

# 启用 LLM 模式评测
python3 -m benchmark.runner --mode full --datasets all --via-api --enable-llm

# 指定 API 地址和批量大小
python3 -m benchmark.runner --mode full --datasets all --via-api --no-llm \
    --api-base http://10.0.0.1:7861 --batch-size 5000
```

### 架构说明

```
Benchmark Client                          LILAC Server (port 7861)
     │                                         │
     ├─ log_format regex 提取 Content           │
     │                                         │
     ├─ DELETE /diagnose/lilac/cache ─────────►│  清空缓存（公平起点）
     │                                         │
     ├─ POST /diagnose/lilac/parse_text ─────►│  batch 1: lines + regex
     │◄── {entries: [{template, ...}]} ────────┤
     │                                         │
     ├─ POST /diagnose/lilac/parse_text ─────►│  batch 2: cache hits 增多
     │◄── {entries: [{template, ...}]} ────────┤
     │    ...                                  │
     └─ 写 structured.csv + templates.csv      │
```

Client 传递 dataset-specific regex（如 IP、端口等模式）给 API 的 `regex` 参数，Server 按顺序应用：调用方 regex → 内置 MASK_PATTERNS → cache/Drain3/LLM。

### API 模式 vs 直接调用模式的区别

| 特征 | 直接调用 (`--no-llm`) | API 模式 (`--via-api`) |
|------|------------------------|------------------------|
| 模板分配 | 离线（用最终模板回溯） | 在线（模板随演化分配） |
| Cache | 无 | 有，跨批次积累 |
| 评测目标 | Drain3 理论上限 | 生产环境真实效果 |
| GA 预期 | 较高 | 因在线演化可能稍低 |

### 评测结果示例（full 模式，Drain3，10 数据集）

| Dataset | GA | PA | FTA | Cache Hits | Drain3 |
|---------|------|------|------|-----------|--------|
| Apache | 0.969 | 0.631 | 0.852 | 51,946 | 32 |
| Zookeeper | 0.820 | 0.498 | 0.780 | 73,583 | 690 |
| HPC | 0.800 | 0.695 | 0.321 | 414,836 | 15,152 |
| Mac | 0.652 | 0.351 | 0.659 | 94,847 | 5,467 |
| Linux | 0.617 | 0.089 | 0.722 | 23,185 | 736 |
| OpenSSH | 0.456 | 0.217 | 0.738 | 638,901 | 46 |
| OpenStack | 0.326 | 0.028 | 0.011 | 196,750 | 10,882 |
| Hadoop | 0.293 | 0.499 | 0.452 | 169,518 | 10,475 |
| HealthApp | 0.255 | 0.326 | 0.174 | 211,134 | 1,260 |
| Proxifier | 0.041 | 0.689 | 0.526 | 21,081 | 239 |

> Cache Hits 远大于 Drain3 调用数说明缓存机制在生产中有效运作。

## 输出结果

运行结束后在 `benchmark/results/` 生成：

- `summary_lilac_{nollm|llm}_{2k|full}.json` — 汇总 JSON（含每个数据集的 6 项指标）
- `lilac_{nollm|llm}_{2k|full}/` — 每个数据集的解析结果 CSV
- `per_dataset_{api_nollm|api_llm}_{2k|full}/` — API 模式下每个数据集的详细 JSON

API 模式的 per-dataset JSON 额外包含：

```json
{
  "cache_hits": 51946,
  "drain3_fallbacks": 32,
  "llm_calls": 0,
  "batch_size": 10000,
  "via_api": true
}
```

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
