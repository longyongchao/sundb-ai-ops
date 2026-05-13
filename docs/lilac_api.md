# LILAC 日志解析模块 API 文档

## 概述

LILAC（LLM-based Log parsing with Adaptive Caching）是一个通用日志解析模块，基于 FSE'24 论文实现。通过**自适应缓存 + LLM 模板提取 + Drain3 兜底**三层架构，能够解析任意格式的日志文件，将非结构化日志转换为结构化模板。

### 核心特性

- **格式无关**：自动识别 SunDB、Syslog、Nginx、ISO8601 等多种日志格式
- **自适应缓存**：已知模板通过 SQLite 缓存命中，延迟 < 0.1ms/行
- **LLM 提取**：未知模式通过 LLM（DeepSeek）ICL few-shot 提取模板
- **Drain3 兜底**：LLM 不可用时自动降级到确定性解析
- **种子预填充**：SunDB 已知格式预填缓存，零 LLM 调用即可解析

### Base URL

```
http://<host>:7861
```

---

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/diagnose/lilac/parse` | 上传日志文件解析 |
| POST | `/diagnose/lilac/parse_text` | 提交日志文本解析 |
| GET | `/diagnose/lilac/cache/stats` | 缓存统计信息 |
| GET | `/diagnose/lilac/cache/templates` | 查看已缓存模板 |
| DELETE | `/diagnose/lilac/cache` | 清空缓存 |
| POST | `/diagnose/lilac/seed` | 触发种子模板生成 |

---

## 1. POST /diagnose/lilac/parse

上传任意日志文件，返回结构化解析结果。

### 请求

- **Content-Type**: `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 日志文件（.log, .trc, .txt 等） |

### 请求示例

```bash
curl -X POST http://localhost:7861/diagnose/lilac/parse \
  -F "file=@/path/to/system.trc"
```

### 响应

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "filename": "system.trc",
    "total_entries": 5,
    "cache_hits": 5,
    "llm_calls": 0,
    "drain3_fallbacks": 0,
    "parse_time_ms": 0.44,
    "entries": [
      {
        "timestamp": "2024-03-12 15:49:05.591941",
        "level": "INFORMATION",
        "message": "[SERVER STARTUP] Database instance started successfully",
        "raw_text": "[2024-03-12 15:49:05.591941 INSTANCE(G1N1) ...] [INFORMATION] [SERVER STARTUP] ...",
        "template": "[SERVER STARTUP] Database instance started successfully",
        "template_source": "seed",
        "parameters": []
      }
    ]
  }
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| filename | string | 上传文件名 |
| total_entries | int | 解析出的日志条目总数 |
| cache_hits | int | 命中缓存的条目数 |
| llm_calls | int | 通过 LLM 提取模板的条目数 |
| drain3_fallbacks | int | 通过 Drain3 兜底的条目数 |
| parse_time_ms | float | 解析耗时（毫秒） |
| entries | array | 解析结果列表（见 Entry 结构） |

---

## 2. POST /diagnose/lilac/parse_text

直接提交日志文本内容解析，无需上传文件。

### 请求

- **Content-Type**: `application/json`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | string | 是 | 日志文本内容（多行用 `\n` 分隔） |
| source_file | string | 否 | 来源文件名标记（仅做标注） |

### 请求示例

```bash
curl -X POST http://localhost:7861/diagnose/lilac/parse_text \
  -H "Content-Type: application/json" \
  -d '{
    "text": "2024-01-01 10:00:00 INFO User alice logged in from 192.168.1.1\n2024-01-01 10:00:01 ERROR Connection timeout",
    "source_file": "app.log"
  }'
```

### 响应

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total_entries": 2,
    "cache_hits": 0,
    "llm_calls": 0,
    "drain3_fallbacks": 0,
    "parse_time_ms": 0.09,
    "entries": [
      {
        "timestamp": "2024-01-01 10:00:00",
        "level": "INFO",
        "message": "User alice logged in from 192.168.1.1",
        "template": "User <*> logged in from <*>",
        "template_source": "cache",
        "parameters": ["alice", "192.168.1.1"]
      },
      {
        "timestamp": "2024-01-01 10:00:01",
        "level": "ERROR",
        "message": "Connection timeout",
        "template": null,
        "template_source": null,
        "parameters": []
      }
    ]
  }
}
```

---

## 3. GET /diagnose/lilac/cache/stats

获取缓存命中率统计信息。

### 请求

无参数。

### 请求示例

```bash
curl http://localhost:7861/diagnose/lilac/cache/stats
```

### 响应

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total_templates": 5,
    "total_hits": 23
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| total_templates | int | 缓存中的模板总数 |
| total_hits | int | 累计命中次数 |

---

## 4. GET /diagnose/lilac/cache/templates

查看已缓存的模板列表，按命中次数降序排列。

### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| limit | int | 否 | 100 | 返回模板数上限 |
| offset | int | 否 | 0 | 偏移量（用于分页） |

### 请求示例

```bash
curl "http://localhost:7861/diagnose/lilac/cache/templates?limit=10&offset=0"
```

### 响应

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total": 5,
    "returned": 5,
    "templates": [
      {
        "template_id": "7bdfef67c4676bbb",
        "template_str": "Listener port <*> opened",
        "hit_count": 12,
        "source": "seed",
        "created_at": 1778603433.97
      },
      {
        "template_id": "d1d8a33b9fa032f0",
        "template_str": "Undo semaphore acquire failed, session <*>",
        "hit_count": 3,
        "source": "seed",
        "created_at": 1778603433.97
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| total | int | 缓存中模板总数 |
| returned | int | 本次返回的数量 |
| templates[].template_id | string | 模板 ID（SHA256 前 16 位） |
| templates[].template_str | string | 模板字符串（`<*>` 为变量占位符） |
| templates[].hit_count | int | 累计命中次数 |
| templates[].source | string | 来源：`seed` / `llm` / `drain3` |
| templates[].created_at | float | 创建时间（Unix timestamp） |

---

## 5. DELETE /diagnose/lilac/cache

清空所有缓存模板和示例数据。

### 请求

无参数。

### 请求示例

```bash
curl -X DELETE http://localhost:7861/diagnose/lilac/cache
```

### 响应

```json
{
  "code": 200,
  "msg": "缓存已清空",
  "data": null
}
```

---

## 6. POST /diagnose/lilac/seed

从 SunDB 样本日志目录提取模板，预填充到缓存中。填充后 SunDB 格式日志可 100% 命中缓存，无需 LLM 调用。

### 请求

- **Content-Type**: `application/json`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sample_dir | string | 是 | SunDB 样本日志所在目录的绝对路径 |

### 请求示例

```bash
curl -X POST http://localhost:7861/diagnose/lilac/seed \
  -H "Content-Type: application/json" \
  -d '{"sample_dir": "/opt/sundb-ai-ops/tests/lilac/sample_logs"}'
```

### 响应

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "templates_added": 5,
    "sample_dir": "/opt/sundb-ai-ops/tests/lilac/sample_logs"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| templates_added | int | 新增的种子模板数量（重复的不计入） |
| sample_dir | string | 回显输入的目录路径 |

---

## 数据结构

### Entry（日志条目）

每个解析出的日志条目包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| timestamp | string | 时间戳（格式由原始日志决定） |
| level | string | 日志级别（INFO / WARNING / ERROR / FATAL 等） |
| message | string | 日志正文（剥离 header 后的内容） |
| raw_text | string | 原始日志行（仅 parse 文件接口返回） |
| template | string \| null | 匹配到的模板（`<*>` 为变量），未匹配时为 null |
| template_source | string \| null | 模板来源：`seed` / `llm` / `drain3` / `cache`，未匹配时为 null |
| parameters | array[string] | 从日志中提取的变量值列表 |

### 模板占位符

模板中使用 `<*>` 表示动态参数位置：

```
原始日志：User alice logged in from 192.168.1.1
模板：    User <*> logged in from <*>
参数：    ["alice", "192.168.1.1"]
```

---

## 支持的日志格式

| 格式 | 示例 | 自动识别 |
|------|------|----------|
| SunDB system.trc | `[2024-03-12 15:49:05 INSTANCE(G1N1) THREAD(...)] [INFORMATION]` | 是（含多行合并） |
| SunDB listener/CDC | `[2024-02-05 16:18:28 THREAD(1347044,...)]` | 是 |
| Syslog | `Mar 15 10:23:01 hostname prog[pid]: msg` | 是 |
| ISO8601 + Level | `2024-03-15 10:23:01 INFO message` | 是 |
| ISO8601 Only | `2024-03-15T10:23:01.123 message` | 是 |
| 未知格式 | 任意文本 | 是（作为 message 整行处理） |

---

## 配置

通过环境变量控制行为：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LILAC_CACHE_DB_PATH` | `data/lilac_cache.db` | SQLite 缓存文件路径 |
| `LILAC_CACHE_SIMILARITY_THRESHOLD` | `0.85` | 缓存匹配相似度阈值 |
| `LILAC_LLM_TEMPERATURE` | `0.0` | LLM 输出温度 |
| `LILAC_LLM_TIMEOUT` | `10.0` | LLM 调用超时（秒） |
| `LILAC_DEMO_POOL_MAX` | `500` | ICL 示例池上限 |
| `LILAC_DEMO_SAMPLE_K` | `8` | 每次采样示例数 |
| `LILAC_ENABLE_LLM` | `true` | 是否启用 LLM 路径 |
| `LILAC_ENABLE_DRAIN3` | `true` | 是否启用 Drain3 兜底 |

---

## 错误响应

所有端点在异常时返回统一格式：

```json
{
  "code": 500,
  "msg": "解析失败: <错误详情>",
  "data": null
}
```

---

## 典型使用流程

```
1. POST /diagnose/lilac/seed          ← 首次部署，预填充 SunDB 模板
2. POST /diagnose/lilac/parse         ← 上传日志文件解析
3. GET  /diagnose/lilac/cache/stats   ← 查看命中率
4. GET  /diagnose/lilac/cache/templates ← 查看学到了哪些模板
```

**首次解析未知格式日志时**：第一次走 LLM 提取模板并自动缓存，后续相同模式的日志直接命中缓存（< 0.1ms），无需再调用 LLM。
