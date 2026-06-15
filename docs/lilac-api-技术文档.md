# LILAC 日志解析 API 技术文档

> 版本: 1.0
> 日期: 2026-06-02
> 模块路径: `server/diagnose/lilac_api.py`, `server/diagnose/lilac/`

---

## 1. 概述

LILAC (Log Inference with Leveraged Adaptive Caching) 是一个高性能日志模板提取引擎，通过 **缓存 + Drain3 + LLM** 三层架构实现生产级日志结构化解析。

**处理流水线:**

```
原始日志文本
    │
    ▼
┌──────────────────────┐
│  调用方 regex 预处理   │  API 参数传入，由调用方定义领域规则
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  内置 MASK_PATTERNS   │  UUID、IPv4、Hex、路径、长数字
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Cache 查找           │  相似度匹配已知模板（SQLite）
└──────────┬───────────┘
           │
      ┌────┴────┐
      │ 命中?    │
      └────┬────┘
     Yes   │   No
      │    │    │
      ▼    │    ▼
   返回    │  ┌──────────────────┐
   模板    │  │  Drain3 / LLM    │  在线聚类或 LLM 提取
           │  └──────────┬───────┘
           │             │
           │             ▼
           │       存入 Cache
           │             │
           └─────────────┘
                   │
                   ▼
            返回 template + parameters
```

**设计哲学:**

引擎提供解析能力（Cache + Drain3 + LLM），调用方提供领域知识（regex 模式）。这与 Elastic/Logstash Grok、Datadog Pipeline、Splunk Source Types 相同的行业范式。

---

## 2. 快速开始

### 启动服务

```bash
cd sundb-ai-ops

# Drain3 模式（不调用 LLM，推荐初次测试）
LILAC_ENABLE_LLM=false python3 run_server.py

# 完整模式（LLM + Drain3 + Cache）
LILAC_ENABLE_LLM=true python3 run_server.py
```

服务默认监听 `http://0.0.0.0:7861`。

### 验证就绪

```bash
curl http://localhost:7861/diagnose/lilac/cache/stats
# 预期: {"code": 200, "msg": "Success", "data": {"total_templates": 0, "total_hits": 0}}
```

### 快速测试

```bash
curl -X POST http://localhost:7861/diagnose/lilac/parse_text \
  -H "Content-Type: application/json" \
  -d '{"text": "Connection from 192.168.1.100 port 22\nConnection from 10.0.0.5 port 22"}'
```

---

## 3. 环境变量配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LILAC_ENABLE_LLM` | `true` | 启用 LLM 模板提取 |
| `LILAC_ENABLE_DRAIN3` | `true` | 启用 Drain3 fallback |
| `LILAC_CACHE_DB_PATH` | `data/lilac_cache.db` | SQLite 缓存数据库路径 |
| `LILAC_CACHE_SIMILARITY_THRESHOLD` | `0.85` | Cache 命中相似度阈值 |
| `LILAC_LLM_TEMPERATURE` | `0.0` | LLM 温度参数 |
| `LILAC_LLM_TIMEOUT` | `10.0` | LLM 调用超时（秒） |
| `LILAC_DEMO_POOL_MAX` | `500` | LLM demonstration pool 最大容量 |
| `LILAC_DEMO_SAMPLE_K` | `8` | LLM few-shot 采样数 |

---

## 4. API 接口

### 4.1 POST `/diagnose/lilac/parse` — 上传文件解析

上传任意日志文件，LILAC 自动识别格式并解析。

**请求:**

```
Content-Type: multipart/form-data
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | 是 | 日志文件 |

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "filename": "system.trc",
    "total_entries": 1523,
    "cache_hits": 1200,
    "llm_calls": 5,
    "drain3_fallbacks": 318,
    "parse_time_ms": 2340.5,
    "entries": [
      {
        "timestamp": "2024-03-12 15:49:05",
        "level": "INFORMATION",
        "message": "Database started successfully",
        "raw_text": "[2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] [INFORMATION] Database started successfully",
        "template": "Database started successfully",
        "template_source": "cache",
        "parameters": {}
      }
    ]
  }
}
```

**cURL 示例:**

```bash
curl -X POST http://localhost:7861/diagnose/lilac/parse \
  -F "file=@/path/to/system.trc"
```

---

### 4.2 POST `/diagnose/lilac/parse_text` — 文本直接解析

直接提交日志文本解析，支持调用方自定义 regex 预处理规则。

**请求:**

```
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 日志文本（多行用 `\n` 分隔） |
| `source_file` | string | 否 | 来源文件名标记（用于统计） |
| `regex` | array | 否 | 自定义正则预处理规则列表 |

**`regex` 参数格式:**

```json
[
  {"pattern": "(\\d+\\.){3}\\d+", "replacement": "<*>"},
  {"pattern": "blk_-?\\d+"},
  {"pattern": ":\\d{2,5}\\b", "replacement": ":<*>"}
]
```

- `pattern`: 正则表达式字符串（必填）
- `replacement`: 替换文本（可选，默认 `<*>`）

**处理顺序:** 调用方 regex → 内置 MASK_PATTERNS → Cache/Drain3/LLM

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total_entries": 50,
    "cache_hits": 45,
    "llm_calls": 0,
    "drain3_fallbacks": 5,
    "parse_time_ms": 120.3,
    "entries": [
      {
        "timestamp": null,
        "level": null,
        "message": "Connection from <*> port <*>",
        "template": "Connection from <*> port <*>",
        "template_source": "cache",
        "parameters": ["192.168.1.100", "22"]
      }
    ]
  }
}
```

**cURL 示例:**

```bash
# 基础调用
curl -X POST http://localhost:7861/diagnose/lilac/parse_text \
  -H "Content-Type: application/json" \
  -d '{"text": "Connection from 192.168.1.100 port 22\nFailed password for root from 10.0.0.5 port 48234"}'

# 带调用方 regex
curl -X POST http://localhost:7861/diagnose/lilac/parse_text \
  -H "Content-Type: application/json" \
  -d '{
    "text": "081109 203518 148 INFO dfs.DataNode$PacketResponder: Received block blk_-1608999687919862906 of size 67108864 from /10.251.73.220",
    "regex": [
      {"pattern": "blk_-?\\d+"},
      {"pattern": "(\\d+\\.){3}\\d+"}
    ]
  }'
```

---

### 4.3 GET `/diagnose/lilac/cache/stats` — 缓存统计

获取 LILAC 缓存的命中率统计信息。

**请求:** 无参数

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total_templates": 46,
    "total_hits": 638901
  }
}
```

**cURL 示例:**

```bash
curl http://localhost:7861/diagnose/lilac/cache/stats
```

---

### 4.4 GET `/diagnose/lilac/cache/templates` — 缓存模板列表

查看已缓存的模板，按命中次数降序排列。

**请求:**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 100 | 返回模板数上限 |
| `offset` | int | 0 | 偏移量（分页） |

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total": 46,
    "returned": 10,
    "templates": [
      {
        "template_id": 1,
        "template_str": "Connection from <*> port <*>",
        "hit_count": 15230,
        "source": "drain3",
        "created_at": "2026-06-02T10:30:00"
      }
    ]
  }
}
```

**cURL 示例:**

```bash
curl "http://localhost:7861/diagnose/lilac/cache/templates?limit=20&offset=0"
```

---

### 4.5 DELETE `/diagnose/lilac/cache` — 清空缓存

清空所有已缓存的模板。

**请求:** 无参数

**响应:**

```json
{
  "code": 200,
  "msg": "缓存已清空",
  "data": null
}
```

**cURL 示例:**

```bash
curl -X DELETE http://localhost:7861/diagnose/lilac/cache
```

---

### 4.6 POST `/diagnose/lilac/seed` — 种子模板生成

从 SunDB 样本日志目录预生成模板种子，加速冷启动。

**请求:**

```
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sample_dir` | string | 是 | SunDB 样本日志目录路径 |

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "templates_added": 42,
    "sample_dir": "/data/sundb_samples/"
  }
}
```

**cURL 示例:**

```bash
curl -X POST http://localhost:7861/diagnose/lilac/seed \
  -H "Content-Type: application/json" \
  -d '{"sample_dir": "/data/sundb_samples/"}'
```

---

## 5. 调用方 Regex 设计指南

### 原则

调用方比引擎更了解自己日志中的变量模式。通过 `regex` 参数将领域知识传递给引擎：

| 日志类型 | 推荐 regex |
|----------|-----------|
| HDFS | `blk_-?\d+`, `(\d+\.){3}\d+` |
| Hadoop | `(\d+\.){3}\d+` |
| OpenStack | `(\d+\.){3}\d+(:\d+)?`, `(req-)?[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}` |
| SunDB | 通常不需要（内置 MASK_PATTERNS 已覆盖） |
| Proxifier | `\d{2}:\d{2}(:\d{2})?`, `[\w.-]+\.\w{2,}(:\d+)?`, `\d+ bytes` |

### 与内置 MASK_PATTERNS 的关系

内置 MASK_PATTERNS（5 条）作为兜底：

1. UUID (`[0-9a-fA-F]{8}-...-[0-9a-fA-F]{12}`)
2. IPv4 (`\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`)
3. Hex (`\b0x[0-9a-fA-F]+\b`)
4. 文件路径 (`(?:/[\w.\-]+){2,}`)
5. 长数字 (`\b\d{4,}\b`)

执行顺序: **调用方 regex 先于 MASK_PATTERNS**，两者互补不冲突。

---

## 6. 错误码

| HTTP Code | `code` 字段 | 含义 |
|-----------|-------------|------|
| 200 | 200 | 成功 |
| 200 | 500 | 服务端内部错误（详见 `msg`） |

所有接口均返回 HTTP 200，业务错误通过 `code` 字段区分。

---

## 7. 典型应用场景

### SunDB 日志解析

```bash
# 上传 system.trc 文件
curl -X POST http://localhost:7861/diagnose/lilac/parse \
  -F "file=@system.trc"

# 或直接传入文本（LILAC 自动识别 SunDB header）
curl -X POST http://localhost:7861/diagnose/lilac/parse_text \
  -H "Content-Type: application/json" \
  -d '{"text": "[2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] [INFORMATION] Database started successfully"}'
```

### 通用日志（带自定义 regex）

```bash
curl -X POST http://localhost:7861/diagnose/lilac/parse_text \
  -H "Content-Type: application/json" \
  -d '{
    "text": "081109 203518 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_-1608999687919862906 terminating",
    "regex": [
      {"pattern": "blk_-?\\d+", "replacement": "<*>"}
    ]
  }'
```

### 批量处理（生产推荐）

对大量日志进行批量处理时，建议：
1. 每批 1,000~10,000 行（用 `\n` 拼接）
2. 传入 `regex` 参数让服务端预处理
3. 批次间不清空 cache — 随着处理推进，cache 命中率会持续提升

```python
import requests

lines = open("app.log").readlines()
batch_size = 5000

for i in range(0, len(lines), batch_size):
    batch = "\n".join(lines[i:i+batch_size])
    resp = requests.post(
        "http://localhost:7861/diagnose/lilac/parse_text",
        json={
            "text": batch,
            "regex": [{"pattern": r"(\d+\.){3}\d+"}]
        }
    )
    data = resp.json()["data"]
    print(f"Batch {i//batch_size}: cache_hits={data['cache_hits']}")
```

---

## 8. Swagger UI

服务启动后访问 `http://localhost:7861/docs` 可查看 FastAPI 自动生成的交互式 API 文档。
