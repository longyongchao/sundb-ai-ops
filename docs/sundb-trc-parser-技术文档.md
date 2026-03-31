# SunDB .trc 日志解析器 — 技术文档

> 版本: 1.0
> 日期: 2026-04-03
> 模块路径: `server/diagnose/sundb_trc_parser.py`, `server/diagnose/sundb_batch_parser.py`

---

## 1. 概述

本模块为 DB-GPT 诊断子系统提供 SunDB 数据库 `.trc` 日志的结构化解析能力，将非结构化的 trace 日志转换为可供下游检索、故障诊断和 Citation 引用的原子依据单元 (AEU)。

**处理流程:**

```
.trc 原始文件
    │
    ▼
┌──────────────────────┐
│  sundb_trc_parser.py │   正则匹配 → SunDBLogEntry 列表
│  (4 种格式解析器)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────┐
│  sundb_batch_parser.py   │   批量解析 → 时间线 → 故障提取 → AEU
│  (批量 + 故障 + AEU)     │
└──────────┬───────────────┘
           │
           ▼
   AEU 列表 → 知识库索引 → 诊断 Agent 检索
```

**核心指标:**

| 项目 | 数据 |
|------|------|
| 支持文件格式 | 4 种 (system / listener / CDC / gmon) |
| 代码总行数 | 596 行 (trc_parser: 350, batch_parser: 246) |
| 测试用例数 | 89 个 (20 个测试类) |
| 测试通过率 | 100% |
| Python 兼容性 | ≥ 3.9 |

---

## 2. 目标集群拓扑

本解析器针对 SunDB 多节点集群，测试数据来自以下 4 节点拓扑：

```
        ┌─── Group 1 ───┐    ┌─── Group 2 ───┐
        │  G1N1   G1N2   │    │  G2N1   G2N2   │
        └────────────────┘    └────────────────┘
```

每个节点的 `trc/` 目录包含：
- `system.trc` — 数据库核心日志（含轮转文件 `system.trc.1`, `system.trc.2`）
- `listener.trc` — 监听器日志
- `cyrmte_<ID>.trc` — CDC 变更数据捕获日志
- `gmon.trc` — 集群监控日志

---

## 3. 模块一: `sundb_trc_parser.py`

### 3.1 数据结构

#### `SunDBLogEntry`

单条日志条目的结构化表示。

```python
@dataclass
class SunDBLogEntry:
    timestamp: str       # "2024-03-12 15:49:05.591941"
    instance: str        # "G1N1" (仅 system.trc 有值)
    thread_pid: int      # 进程 ID
    thread_tid: int      # 线程 ID
    level: str           # "INFORMATION" / "WARNING" / "FATAL" (仅 system.trc)
    message: str         # 消息正文 (多行合并，空行过滤)
    category: str        # "[DEADLOCK]" / "[SESSION]" 等类别标签
    error_code: str      # "ERR-HY000(11000)" 等
    error_message: str   # 错误码对应的描述文本
    source_file: str     # 来源文件路径 (parse_file 时填充)
    raw_text: str        # 原始文本块
```

**字段填充规则:**

| 字段 | system.trc | listener.trc | cyrmte_*.trc | gmon.trc |
|------|-----------|-------------|-------------|---------|
| `instance` | 从 `INSTANCE(X)` 提取 | 空字符串 | 空字符串 | 空字符串 |
| `level` | `INFORMATION` / `WARNING` / `FATAL` | 空字符串 | 空字符串 | 空字符串 |
| `category` | 从 `[TAG]` 提取 | 含 `LISTENER` 则为 `"LISTENER"` | 空字符串 | 空字符串 |
| `error_code` | 双模式提取 | standalone 模式 | standalone 模式 | 不提取 |

#### `SunDBFileHeader`

trc 文件头元信息。

```python
@dataclass
class SunDBFileHeader:
    instance_name: str   # "G1N1" (仅 system.trc 文件头包含)
    timestamp: str       # "2024-03-12 15:49:05.624850"
    version: str         # "Release 5.0 22.1.3 revision(7f23c84d0b)"
```

### 3.2 正则表达式

模块使用 5 个预编译正则匹配日志结构：

#### `_RE_SYSTEM_ENTRY` — system.trc 条目头

匹配格式：`[2024-03-12 15:49:05.591941 INSTANCE(G1N1) THREAD(2586375,281464209690016)] [INFORMATION]`

```python
_RE_SYSTEM_ENTRY = re.compile(
    r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)'  # group(1): timestamp
    r'\s+INSTANCE\((\w+)\)'                                 # group(2): instance
    r'\s+THREAD\((\d+),(\d+)\)\]'                           # group(3,4): pid, tid
    r'\s+\[(\w+)\]',                                        # group(5): level
    re.MULTILINE,
)
```

#### `_RE_SIMPLE_ENTRY` — listener / CDC / gmon 条目头

匹配格式：`[2024-02-05 16:18:28.406162 THREAD(1347044,281465167431120)]`

```python
_RE_SIMPLE_ENTRY = re.compile(
    r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)'  # group(1): timestamp
    r'\s+THREAD\((\d+),(\d+)\)\]',                         # group(2,3): pid, tid
    re.MULTILINE,
)
```

#### `_RE_ERROR_CODE` — 带实例名的错误码

匹配格式：`(G1N1) ERR-HY000(11000) : message`

```python
_RE_ERROR_CODE = re.compile(r'\((\w+)\)\s+(ERR-[\w]+\(\d+\))\s*[:\s]\s*(.*)')
```

#### `_RE_ERROR_CODE_STANDALONE` — 独立错误码

匹配格式：`ERR-28000(16004) : message`

```python
_RE_ERROR_CODE_STANDALONE = re.compile(r'(ERR-[\w]+\(\d+\))\s*[:\s]\s*(.*)')
```

#### `_RE_HEADER_BLOCK` — 文件头块

匹配 `======` 包围的文件头信息块。

```python
_RE_HEADER_BLOCK = re.compile(r'={10,}\s*\n(.*?)={10,}', re.DOTALL)
```

### 3.3 解析器类层次

```
_BaseTrcParser (基类)
├── parse_header(content) → Optional[SunDBFileHeader]
├── parse(content) → List[SunDBLogEntry]          # 抽象方法
└── parse_file(path) → List[SunDBLogEntry]        # 读文件 + 填充 source_file
    │
    ├── SunDBSystemTrcParser      使用 _RE_SYSTEM_ENTRY
    │   ├── _extract_category()   从首行提取 [TAG]
    │   └── _extract_error()      双模式错误码提取
    │
    ├── SunDBListenerTrcParser    使用 _RE_SIMPLE_ENTRY
    │                              category 根据 LISTENER 关键字判定
    │
    ├── SunDBCdcTrcParser         使用 _RE_SIMPLE_ENTRY
    │                              提取 standalone 错误码
    │
    └── SunDBGmonTrcParser        使用 _RE_SIMPLE_ENTRY
                                   不提取错误码
```

### 3.4 多行条目解析算法

所有解析器使用相同的多行拼接策略：

```
1. regex.finditer(content) → 获取所有匹配位置列表 matches
2. 对每个 match[i]:
   - 条目范围 = match[i].start() ~ match[i+1].start()  (最后一个到 EOF)
   - raw_block = content[start:end].strip()
   - body = content[match[i].end() : end].strip()
3. message = body 各行过滤空行后用 \n 拼接
```

这种「相邻 match 定界」的方法确保多行消息体（如 DEADLOCK 的事务链信息）被完整保留。

### 3.5 类别 (Category) 提取逻辑

仅 `SunDBSystemTrcParser` 提取类别，优先级：

1. 首行开头匹配 `[TAG]` → 返回 `TAG`
2. 首行任意位置匹配 `[TAG]` → 返回 `TAG`（覆盖 `[SESSION:123][DEADLOCK]` 格式）
3. 均无匹配 → 返回空字符串

TAG 要求：全大写字母 + 下划线/空格，最少 2 个字符（如 `DEADLOCK`, `SESSION`, `LC`）。

### 3.6 错误码提取逻辑

**system.trc (`_extract_error`)**:
1. 逐行扫描 body
2. 优先匹配 `(INSTANCE) ERR-XXX(NNN) : msg`
3. 回退匹配 `ERR-XXX(NNN) : msg`

**listener.trc / CDC (`_extract_simple_error`)**:
1. 逐行扫描 body
2. 优先匹配 standalone 格式
3. 回退匹配带实例名格式

已覆盖的错误码类型：

| 错误码 | 含义 | 来源文件 |
|--------|------|---------|
| `ERR-HY000(11000)` | 通用内部错误 | system.trc |
| `ERR-42000(15017)` | DDL 语法/权限错误 | system.trc |
| `ERR-42000(16032)` | DDL 执行错误 | system.trc |
| `ERR-RD000(13041)` | 复制域错误 | system.trc |
| `ERR-28000(16004)` | 认证失败 | cyrmte_*.trc |

---

## 4. 模块二: `sundb_batch_parser.py`

### 4.1 数据结构

#### `FaultEvent`

故障事件，由日志条目分类提取。

```python
@dataclass
class FaultEvent:
    event_type: str                    # "FATAL" / "DEADLOCK" / "DDL_FAILURE" / "AUTH_FAILURE" / "LISTENER_FAILURE"
    timestamp: str                     # 时间戳
    instance: str                      # 实例名
    description: str                   # 故障描述 (= entry.message)
    error_code: str                    # 错误码
    related_entries: List[SunDBLogEntry]  # 关联日志条目
    severity: str                      # "critical" / "high" / "medium" / "low"
```

#### `AEU` (Atomic Evidence Unit / 原子依据单元)

面向 Citation 检索的最小证据单元。

```python
@dataclass
class AEU:
    event_id: str              # "{TYPE}-{INSTANCE}-{TS_COMPACT}-{UUID6}"
    timestamp: str             # 原始时间戳
    event_type: str            # 故障类型
    key_fields: Dict[str, str] # 结构化关键字段
    raw_log_snippet: str       # 原始日志片段
```

**`event_id` 生成规则:**

```
{event_type}-{instance|UNKNOWN}-{YYYYMMDDHHmmss}-{uuid4_hex[:6]}
```

示例: `FATAL-G2N2-20240312180026-a3f1c2`

### 4.2 `SunDBBatchParser` 类

#### 4.2.1 批量解析 `parse_directory(directory)`

```python
def parse_directory(self, directory: str) -> List[SunDBLogEntry]:
```

遍历目录内所有文件，根据文件名自动路由到对应解析器：

| 文件名模式 | 匹配条件 | 路由解析器 |
|-----------|---------|-----------|
| `system.trc`, `system.trc.1`, ... | `basename.startswith("system.trc")` | `SunDBSystemTrcParser` |
| `listener.trc` | `basename == "listener.trc"` | `SunDBListenerTrcParser` |
| `cyrmte_*.trc` | `startswith("cyrmte_")` and `endswith(".trc")` | `SunDBCdcTrcParser` |
| `gmon.trc` | `basename == "gmon.trc"` | `SunDBGmonTrcParser` |
| 其他 | — | 跳过 |

**特性:**
- 文件名匹配不区分大小写
- 单文件解析异常被静默跳过 (不中断整批)
- 支持 system.trc 轮转文件 (`.1`, `.2`, ...)
- 非文件项 (子目录) 自动跳过

#### 4.2.2 时间线构建 `build_timeline(entries)`

```python
def build_timeline(self, entries: List[SunDBLogEntry]) -> List[SunDBLogEntry]:
```

按 `timestamp` 字符串排序（ISO 格式天然支持字典序排序）。用于构建跨文件的统一时间线。

#### 4.2.3 故障事件提取 `extract_fault_events(entries)`

```python
def extract_fault_events(self, entries: List[SunDBLogEntry]) -> List[FaultEvent]:
```

对每条日志调用 `_classify_fault()` 进行分类。分类规则按优先级：

| 优先级 | 条件 | event_type | severity |
|--------|------|-----------|----------|
| 1 | `entry.level == "FATAL"` | `FATAL` | critical |
| 2 | `entry.category == "DEADLOCK"` | `DEADLOCK` | high |
| 3 | `"DDL failure" in entry.message` | `DDL_FAILURE` | medium |
| 4 | `entry.error_code.startswith("ERR-28000")` | `AUTH_FAILURE` | high |
| 5 | `"failed to create listener" in message.lower()` | `LISTENER_FAILURE` | high |

不满足任何条件的条目返回 `None`，不产生故障事件。

#### 4.2.4 AEU 转换 `to_aeu_list(faults)`

```python
def to_aeu_list(self, faults: List[FaultEvent]) -> List[AEU]:
```

**`key_fields` 构成:**

| 字段 | 所有类型 | DEADLOCK 专有 |
|------|---------|-------------|
| `instance` | 实例名 | — |
| `error_code` | 错误码 | — |
| `session_id` | — | 从 `SESSION_ID : N` 提取 |
| `sql` | — | 从 `SQL : ...` 提取 |

**`raw_log_snippet` 构成:**

对 `related_entries` 中每个条目拼接：
1. `entry.message`
2. 如有 `error_code`: `"{error_code}: {error_message}"`

---

## 5. 完整处理流水线示例

```python
from server.diagnose.sundb_batch_parser import SunDBBatchParser

bp = SunDBBatchParser()

# 1. 批量解析一个节点的所有 trc 文件
entries = bp.parse_directory("/data/sundb/g1n1/trc/")

# 2. 按时间排序
timeline = bp.build_timeline(entries)

# 3. 提取故障事件
faults = bp.extract_fault_events(timeline)

# 4. 转换为 AEU
aeu_list = bp.to_aeu_list(faults)

# 5. 查看结果
for aeu in aeu_list:
    print(f"[{aeu.event_type}] {aeu.event_id}")
    print(f"  时间: {aeu.timestamp}")
    print(f"  关键字段: {aeu.key_fields}")
    print(f"  日志片段: {aeu.raw_log_snippet[:100]}...")
```

---

## 6. 测试覆盖

### 6.1 测试概览

测试文件: `tests/test_sundb_parser.py` (1260 行, 20 个测试类, 89 个测试方法)

```bash
python3 -m pytest tests/test_sundb_parser.py -v
# 89 passed in 6.22s
```

### 6.2 测试类清单

| # | 测试类 | 方法数 | 测试范围 |
|---|-------|--------|---------|
| 1 | `TestSunDBLogEntry` | 3 | 数据结构创建与字段验证 |
| 2 | `TestSunDBFileHeader` | 5 | 文件头解析 (system / listener / gmon / 完整内容 / 无头) |
| 3 | `TestSystemTrcInformation` | 4 | INFORMATION 级别日志解析 (rebalance / build_gsi / deadlock / SQL提取) |
| 4 | `TestSystemTrcWarning` | 4 | WARNING 级别日志解析 (sniped session / cleanup / DDL failure / ERR-RD000) |
| 5 | `TestSystemTrcFatal` | 2 | FATAL 级别日志解析 + 错误码 |
| 6 | `TestErrorCodeExtraction` | 5 | 5 种错误码格式提取验证 |
| 7 | `TestSystemTrcMultiEntries` | 4 | 多条目解析 (数量 / 顺序 / 时间戳 / 实例名) |
| 8 | `TestListenerTrcParser` | 4 | listener.trc 解析 (启动 / 失败 / 多条目 / 多行配置) |
| 9 | `TestCdcTrcParser` | 6 | CDC 日志解析 (连接串 / 认证失败 / LSN / 表添加 / 捕获配置 / 多条目) |
| 10 | `TestGmonTrcParser` | 3 | gmon.trc 解析 (warmup / init / 完整内容) |
| 11 | `TestFileLevel` | 7 | 文件级操作 (system / listener / CDC 文件 / 不存在 / 空 / 仅头 / 轮转) |
| 12 | `TestBatchParser` | 5 | 批量解析 (目录 / 自动检测 / 非trc忽略 / 轮转文件 / 不存在目录) |
| 13 | `TestTimeline` | 3 | 时间线构建 (排序 / 跨文件 / 空列表) |
| 14 | `TestFaultEventExtraction` | 8 | 故障提取 (FATAL / DEADLOCK / DDL / AUTH / LISTENER / 正常 / 多故障 / 关联条目) |
| 15 | `TestFaultEvent` | 1 | FaultEvent 数据结构验证 |
| 16 | `TestAEUConversion` | 5 | AEU 转换 (FATAL / 唯一ID / 原始片段 / DEADLOCK字段 / 空列表) |
| 17 | `TestAEUDataClass` | 1 | AEU 数据结构验证 |
| 18 | `TestRealFiles` | 10 | 真实集群日志集成测试 (4 节点, 需 `测试文件/trc/extracted/`) |
| 19 | `TestEdgeCases` | 6 | 边界情况 (畸形时间戳 / 截断 / 编码 / 空行 / 超长消息 / 连续头) |
| 20 | `TestStatistics` | 3 | 统计功能 (按级别 / 按类别 / 按错误码计数) |

### 6.3 测试数据来源

所有测试常量均从真实 SunDB 集群日志中提取，保留了原始格式：

| 常量名 | 来源 | 描述 |
|--------|------|------|
| `SYSTEM_TRC_HEADER` | g1n1/system.trc | 文件头 (含 INSTANCE NAME) |
| `SIMPLE_TRC_HEADER` | g1n1/listener.trc | 文件头 (无 INSTANCE NAME) |
| `SYSTEM_ENTRY_INFORMATION` | g1n1/system.trc | INFORMATION 级别日志 |
| `SYSTEM_ENTRY_DEADLOCK` | g2n1/system.trc | DEADLOCK 事件 (含 SESSION_ID + SQL) |
| `SYSTEM_ENTRY_FATAL` | g2n2/system.trc | FATAL undo semaphore 错误 |
| `SYSTEM_ENTRY_DDL_FAILURE` | g1n1/system.trc | DDL failure WARNING |
| `CDC_ENTRY_AUTH_FAILURE` | g1n1/cyrmte_*.trc | ERR-28000 认证失败 |
| `LISTENER_ENTRY_FAILED` | g1n1/listener.trc | listener 创建失败 |

### 6.4 集成测试

`TestRealFiles` 类的 10 个测试直接读取 `测试文件/trc/extracted/` 下的真实集群日志。通过 `@pytest.mark.skipif` 在文件不存在时自动跳过：

```python
REAL_TRC_BASE = ROOT_PATH / "测试文件" / "trc" / "extracted"
SKIP_REAL = not REAL_TRC_BASE.exists()

@pytest.mark.skipif(SKIP_REAL, reason="真实测试文件目录不存在")
class TestRealFiles:
    ...
```

---

## 7. 依赖关系

```
sundb_batch_parser.py
    ├── import → sundb_trc_parser.py
    │              ├── SunDBLogEntry
    │              ├── SunDBSystemTrcParser
    │              ├── SunDBListenerTrcParser
    │              ├── SunDBCdcTrcParser
    │              └── SunDBGmonTrcParser
    │
    └── stdlib: os, re, uuid, dataclasses, typing

sundb_trc_parser.py
    └── stdlib: re, dataclasses, typing
```

无第三方依赖。测试仅需 `pytest`。

---

## 8. 已知限制与扩展方向

### 8.1 已知限制

| 限制 | 说明 |
|------|------|
| 单线程解析 | 大文件 (>100MB) 时性能受限，未引入并行 |
| 字符串排序 | `build_timeline` 基于时间戳字典序，跨年时需确认格式一致 |
| 错误码单次匹配 | 每个 body 仅提取首个错误码，同一条目内多个错误码会丢失后续 |
| 无增量解析 | 每次 `parse_file` 全量读入内存，不支持流式处理 |
| DEADLOCK 字段提取 | 仅提取 `SESSION_ID` 和 `SQL`，未覆盖完整事务链 |

### 8.2 扩展方向

1. **知识库对接** — 将 AEU 的 `raw_log_snippet` 生成语义向量，接入 BM25 + 向量双路检索
2. **跨节点关联** — 利用 `build_timeline` 的跨文件时间线，实现故障传播链分析
3. **更多故障类型** — 扩展 `_classify_fault` 覆盖 OOM、磁盘满、网络分区等场景
4. **性能优化** — 对 >50MB 文件引入 mmap 或分块读取
5. **增量解析** — 支持日志轮转后仅解析新增部分

---

## 9. API 接口文档

本节定义 SunDB trc 解析器暴露给前端的 REST API。所有接口遵循现有项目约定：统一返回 `BaseResponse` 格式。

### 9.1 响应格式

所有接口统一使用 `server.utils.BaseResponse`:

```json
{
  "code": 200,
  "msg": "Success",
  "data": { ... }
}
```

### 9.2 接口清单

#### `POST /diagnose/upload_trc`

上传 `.trc` 文件并解析为结构化日志条目。

**请求:** `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | `UploadFile` | 是 | 单个 `.trc` 文件 |

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "filename": "system.trc",
    "parser_type": "system",
    "header": {
      "instance_name": "G1N1",
      "timestamp": "2024-03-12 15:49:05.624850",
      "version": "Release 5.0 22.1.3 revision(7f23c84d0b)"
    },
    "total_entries": 1523,
    "entries_by_level": {
      "INFORMATION": 1400,
      "WARNING": 120,
      "FATAL": 3
    },
    "fault_count": 18,
    "entries": [
      {
        "timestamp": "2024-03-12 15:49:05.591941",
        "instance": "G1N1",
        "level": "INFORMATION",
        "message": "[LC] Rebalance complete ...",
        "category": "LC",
        "error_code": "",
        "error_message": ""
      }
    ]
  }
}
```

---

#### `POST /diagnose/upload_trc_directory`

上传 `.tar.gz` 压缩包（包含一个节点的完整 `trc/` 目录），批量解析所有文件。

**请求:** `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | `UploadFile` | 是 | `.tar.gz` 压缩包（内含 `*.trc` 文件） |

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "filename": "g1n1_trc.tar.gz",
    "files_parsed": ["system.trc", "system.trc.1", "listener.trc", "cyrmte_SLWDLCVK.trc", "gmon.trc"],
    "total_entries": 5200,
    "timeline_range": {
      "earliest": "2024-02-05 16:18:28.406162",
      "latest": "2024-04-25 11:42:56.829139"
    },
    "fault_summary": {
      "total": 32,
      "by_type": {
        "FATAL": 3,
        "DEADLOCK": 5,
        "DDL_FAILURE": 12,
        "AUTH_FAILURE": 8,
        "LISTENER_FAILURE": 4
      },
      "by_severity": {
        "critical": 3,
        "high": 17,
        "medium": 12
      }
    },
    "aeu_list": [
      {
        "event_id": "FATAL-G2N2-20240312180026-a3f1c2",
        "timestamp": "2024-03-12 18:00:26.123456",
        "event_type": "FATAL",
        "key_fields": {
          "instance": "G2N2",
          "error_code": "ERR-HY000(11000)"
        },
        "raw_log_snippet": "undo tablespace semaphore timeout\nERR-HY000(11000): ..."
      }
    ]
  }
}
```

---

#### `GET /diagnose/trc/fault_events`

获取最近一次 trc 解析的故障事件列表（用于前端故障面板展示）。

**请求:** Query Parameters

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `severity` | `string` | 否 | 全部 | 按严重程度过滤: `critical` / `high` / `medium` |
| `event_type` | `string` | 否 | 全部 | 按事件类型过滤: `FATAL` / `DEADLOCK` / `DDL_FAILURE` / `AUTH_FAILURE` / `LISTENER_FAILURE` |
| `limit` | `int` | 否 | 100 | 返回条数上限 |

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total": 32,
    "faults": [
      {
        "event_type": "FATAL",
        "timestamp": "2024-03-12 18:00:26.123456",
        "instance": "G2N2",
        "description": "undo tablespace semaphore timeout ...",
        "error_code": "ERR-HY000(11000)",
        "severity": "critical"
      }
    ]
  }
}
```

---

#### `GET /diagnose/trc/timeline`

获取跨文件统一时间线。

**请求:** Query Parameters

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `start_time` | `string` | 否 | — | 起始时间过滤 (ISO 格式) |
| `end_time` | `string` | 否 | — | 结束时间过滤 |
| `level` | `string` | 否 | 全部 | `INFORMATION` / `WARNING` / `FATAL` |
| `instance` | `string` | 否 | 全部 | 按节点过滤: `G1N1` / `G1N2` / `G2N1` / `G2N2` |
| `limit` | `int` | 否 | 200 | 返回条数上限 |

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total": 5200,
    "returned": 200,
    "entries": [
      {
        "timestamp": "2024-02-05 16:18:28.406162",
        "instance": "",
        "level": "",
        "message": "[LISTENER] LISTENER started ...",
        "category": "LISTENER",
        "error_code": "",
        "source_file": "listener.trc"
      }
    ]
  }
}
```

---

#### `GET /diagnose/trc/aeu_list`

获取 AEU (原子依据单元) 列表，供 Citation 检索模块使用。

**请求:** Query Parameters

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `event_type` | `string` | 否 | 全部 | 按事件类型过滤 |

**响应:**

```json
{
  "code": 200,
  "msg": "Success",
  "data": {
    "total": 32,
    "aeu_list": [
      {
        "event_id": "DEADLOCK-G2N1-20240405100530-b7e2d1",
        "timestamp": "2024-04-05 10:05:30.456789",
        "event_type": "DEADLOCK",
        "key_fields": {
          "instance": "G2N1",
          "error_code": "",
          "session_id": "42",
          "sql": "UPDATE EMPLOYEE SET SALARY = ..."
        },
        "raw_log_snippet": "[DEADLOCK] SESSION_ID : 42\nSQL : UPDATE ..."
      }
    ]
  }
}
```

### 9.3 后端路由注册位置

所有新接口需在 `server/api.py` 的 `mount_diagnose_routes()` 中注册:

```python
# server/api.py — mount_diagnose_routes() 内追加:
from server.diagnose.sundb_trc_api import (
    upload_trc, upload_trc_directory,
    get_trc_fault_events, get_trc_timeline, get_trc_aeu_list
)

app.post("/diagnose/upload_trc", tags=["SunDB TRC"])(upload_trc)
app.post("/diagnose/upload_trc_directory", tags=["SunDB TRC"])(upload_trc_directory)
app.get("/diagnose/trc/fault_events", tags=["SunDB TRC"])(get_trc_fault_events)
app.get("/diagnose/trc/timeline", tags=["SunDB TRC"])(get_trc_timeline)
app.get("/diagnose/trc/aeu_list", tags=["SunDB TRC"])(get_trc_aeu_list)
```

### 9.4 后端待新增文件

| 文件 | 说明 |
|------|------|
| `server/diagnose/sundb_trc_api.py` | API handler 函数，调用 `SunDBBatchParser` 和各解析器 |

---

## 10. 前端集成 TODO

基于当前项目前端架构（React 18 + Ant Design 5 + Axios），以下是集成 SunDB trc 解析功能所需的修改清单。

### 10.1 涉及文件总览

```
webui-react/src/
├── utils/api.jsx                          # [修改] 新增 sundbTrcAPI
├── pages/Diagnosis/index.jsx              # [修改] 扩展文件上传支持 .trc/.tar.gz
├── components/
│   ├── TrcFaultPanel/index.jsx            # [新增] 故障事件面板
│   ├── TrcTimelinePanel/index.jsx         # [新增] 跨文件时间线视图
│   └── Charts/TrcFaultSummaryChart.jsx    # [新增] 故障统计图表
└── context/DiagnosisContext.jsx           # [修改] 新增 trc 解析相关状态
```

### 10.2 TODO 详细清单

#### TODO-1: `webui-react/src/utils/api.jsx` — 新增 API 调用

在现有 `diagnoseAPI` 对象之后新增 `sundbTrcAPI`:

```javascript
// TODO: 新增 SunDB TRC API 调用
export const sundbTrcAPI = {
  // 上传单个 .trc 文件
  uploadTrc: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/diagnose/upload_trc', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
  },

  // 上传 .tar.gz 目录压缩包
  uploadTrcDirectory: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/diagnose/upload_trc_directory', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
  },

  // 获取故障事件列表
  getFaultEvents: async (params = {}) => {
    return api.get('/diagnose/trc/fault_events', { params });
  },

  // 获取时间线
  getTimeline: async (params = {}) => {
    return api.get('/diagnose/trc/timeline', { params });
  },

  // 获取 AEU 列表
  getAEUList: async (params = {}) => {
    return api.get('/diagnose/trc/aeu_list', { params });
  },
};
```

---

#### TODO-2: `webui-react/src/pages/Diagnosis/index.jsx` — 扩展文件上传

**修改点 1:** Upload 组件 `accept` 属性添加 `.trc` 和 `.tar.gz`

```diff
 <Upload
   beforeUpload={handleUpload}
-  accept=".json,.yaml,.yml"
+  accept=".json,.yaml,.yml,.trc,.tar.gz"
 >
```

**修改点 2:** `handleUpload` 函数增加 .trc 文件分支

```javascript
// TODO: handleUpload 中增加 trc 判断
const handleUpload = async (file) => {
  setLocalUploadFile(file);
  resetDiagnosis();

  if (file.name.endsWith('.trc')) {
    // 单文件 trc 上传 → 走 sundbTrcAPI.uploadTrc
    message.info(`检测到 SunDB 日志文件: ${file.name}，将进行 trc 解析`);
    setUploadMode('trc_single');
  } else if (file.name.endsWith('.tar.gz')) {
    // 目录打包上传 → 走 sundbTrcAPI.uploadTrcDirectory
    message.info(`检测到 trc 压缩包: ${file.name}，将进行批量解析`);
    setUploadMode('trc_batch');
  } else {
    // 原有 JSON 逻辑
    setUploadMode('json');
  }

  message.success(`已选择文件: ${file.name}`);
  return false;
};
```

**修改点 3:** `handleStartDiagnosis` 根据 `uploadMode` 走不同流程

```javascript
// TODO: 在 handleStartDiagnosis 中增加 trc 分支
if (uploadMode === 'trc_single') {
  const result = await sundbTrcAPI.uploadTrc(localUploadFile);
  setTrcParseResult(result);
  // 展示 TrcFaultPanel 而非 Tree Search 结果
} else if (uploadMode === 'trc_batch') {
  const result = await sundbTrcAPI.uploadTrcDirectory(localUploadFile);
  setTrcParseResult(result);
} else {
  // 原有 quick_diagnose 流程
  ...
}
```

---

#### TODO-3: `webui-react/src/context/DiagnosisContext.jsx` — 新增状态

```javascript
// TODO: 在 DiagnosisContext reducer 中新增
case 'SET_TRC_PARSE_RESULT':
  return { ...state, trcParseResult: action.payload };
case 'SET_TRC_FAULT_EVENTS':
  return { ...state, trcFaultEvents: action.payload };
case 'SET_TRC_TIMELINE':
  return { ...state, trcTimeline: action.payload };
case 'SET_TRC_AEU_LIST':
  return { ...state, trcAEUList: action.payload };
case 'SET_UPLOAD_MODE':
  return { ...state, uploadMode: action.payload };  // 'json' | 'trc_single' | 'trc_batch'
```

---

#### TODO-4: `webui-react/src/components/TrcFaultPanel/index.jsx` — 新增组件

故障事件面板，以表格 + Tag 形式展示：

```
┌─ SunDB 故障事件 ──────────────────────────────────────────┐
│                                                            │
│  筛选: [severity ▼] [event_type ▼]                         │
│                                                            │
│  ┌────────┬────────────────────┬──────┬──────┬──────────┐  │
│  │ 严重度  │ 时间               │ 节点  │ 类型  │ 错误码    │  │
│  ├────────┼────────────────────┼──────┼──────┼──────────┤  │
│  │🔴 critical│ 2024-03-12 18:00 │ G2N2 │ FATAL│ERR-HY000 │  │
│  │🟠 high   │ 2024-04-05 10:05 │ G2N1 │DEAD- │          │  │
│  │          │                  │      │ LOCK │          │  │
│  │🟡 medium │ 2024-03-15 09:30 │ G1N1 │ DDL  │ERR-42000 │  │
│  └────────┴────────────────────┴──────┴──────┴──────────┘  │
│                                                            │
│  展开行 → 显示 raw_log_snippet + related_entries           │
└────────────────────────────────────────────────────────────┘
```

使用 Ant Design `<Table>` + `<Tag>` + 可展开行。

---

#### TODO-5: `webui-react/src/components/TrcTimelinePanel/index.jsx` — 新增组件

跨文件时间线视图:

```
┌─ SunDB 日志时间线 ────────────────────────────────────────┐
│                                                            │
│  筛选: [instance ▼] [level ▼] [时间范围 ────────]          │
│                                                            │
│  ● 2024-02-05 16:18:28  listener.trc                       │
│  │  [LISTENER] LISTENER started on port 5236               │
│  │                                                         │
│  ● 2024-03-12 15:49:05  system.trc     G1N1                │
│  │  [INFORMATION] [LC] Rebalance complete                   │
│  │                                                         │
│  ●🔴 2024-03-12 18:00:26  system.trc   G2N2                │
│  │  [FATAL] undo tablespace semaphore timeout               │
│  │  ERR-HY000(11000)                                        │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

使用 Ant Design `<Timeline>` + `<Tag>` 按级别着色。

---

#### TODO-6: `webui-react/src/components/Charts/TrcFaultSummaryChart.jsx` — 新增组件

故障统计图表，包含：
- 饼图: 按 `event_type` 分布 (复用现有 `AnomalyPieChart` 模式)
- 柱状图: 按 `severity` 分布
- 柱状图: 按 `instance` 分布 (展示各节点故障密度)

使用现有的 `recharts` 或 `echarts` 依赖。

---

#### TODO-7: `webui-react/src/pages/Diagnosis/index.jsx` — 结果展示区域

在诊断结果渲染区新增 trc 解析结果的条件分支:

```javascript
// TODO: 在结果渲染区增加 trc 模式判断
{uploadMode?.startsWith('trc') && trcParseResult ? (
  <Row gutter={16}>
    <Col span={24}>
      <TrcFaultSummaryChart data={trcParseResult.fault_summary} />
    </Col>
    <Col span={24}>
      <TrcFaultPanel faults={trcParseResult.aeu_list} />
    </Col>
    <Col span={24}>
      <TrcTimelinePanel />
    </Col>
  </Row>
) : (
  // 原有 Tree Search 结果渲染
  ...
)}
```

---

#### TODO-8: `webui-react/src/pages/Diagnosis/index.jsx` — `buildAnomalyInfo()` 扩展

现有 `buildAnomalyInfo()` 函数 (行 88-194) 用于从文件内容推断异常类型，需增加 SunDB trc 格式识别:

```javascript
// TODO: 在 buildAnomalyInfo 中增加 trc 识别
const isSunDBTrc = (
  content.includes('INSTANCE(') ||
  content.includes('THREAD(') ||
  content.includes('[INFORMATION]') ||
  content.includes('[FATAL]')
);
if (isSunDBTrc) {
  return {
    alert_type: "SunDB TRC Log",
    description: "检测到 SunDB 数据库 trace 日志，将进行结构化解析和故障提取",
    severity: "medium",
    timestamp: new Date().toISOString(),
    source: "sundb_trc"
  };
}
```

### 10.3 修改量评估

| 类型 | 文件 | 预估工作量 |
|------|------|-----------|
| 修改 | `utils/api.jsx` | ~30 行 |
| 修改 | `pages/Diagnosis/index.jsx` | ~80 行 |
| 修改 | `context/DiagnosisContext.jsx` | ~20 行 |
| 新增 | `components/TrcFaultPanel/index.jsx` | ~150 行 |
| 新增 | `components/TrcTimelinePanel/index.jsx` | ~120 行 |
| 新增 | `components/Charts/TrcFaultSummaryChart.jsx` | ~100 行 |
| 新增 | `server/diagnose/sundb_trc_api.py` (后端) | ~120 行 |
| 修改 | `server/api.py` (路由注册) | ~10 行 |
| **合计** | | **~630 行** |

### 10.4 集成后完整数据流

```
用户上传 .trc / .tar.gz
      │
      ▼
Diagnosis/index.jsx
├── handleUpload() 识别文件类型 → setUploadMode('trc_*')
└── handleStartDiagnosis()
      │
      ├── [trc_single] sundbTrcAPI.uploadTrc(file)
      │       │
      │       ▼
      │   POST /diagnose/upload_trc
      │       │
      │       ▼
      │   sundb_trc_api.py → SunDBSystemTrcParser / ListenerTrcParser / ...
      │       │
      │       ▼
      │   返回 { entries, fault_count, header }
      │
      └── [trc_batch] sundbTrcAPI.uploadTrcDirectory(file)
              │
              ▼
          POST /diagnose/upload_trc_directory
              │
              ▼
          sundb_trc_api.py → 解压 → SunDBBatchParser.parse_directory()
              │
              ▼
          build_timeline() → extract_fault_events() → to_aeu_list()
              │
              ▼
          返回 { timeline_range, fault_summary, aeu_list }
              │
              ▼
      前端渲染:
      ├── TrcFaultSummaryChart (饼图 + 柱状图)
      ├── TrcFaultPanel (故障事件表格)
      └── TrcTimelinePanel (时间线视图)
              │
              ▼
      AEU → 知识库索引 → 诊断 Agent Citation 引用
```

---

## 11. Git 提交历史

| 日期 | Commit | 说明 |
|------|--------|------|
| 2026-03-30 | `f1f498b` | 数据结构定义 + 文件头解析 + 测试骨架 |
| 2026-03-31 | `bc8c558` | system.trc 核心解析器 (正则 + 多行拼接 + 错误码提取) |
| 2026-04-01 | `76fe941` | listener / CDC / gmon 三种解析器实现 |
| 2026-04-02 | `3fb9f72` | 批量解析器 + 故障事件提取 + AEU 转换 |
| 2026-04-03 | `492d5bc` | 真实文件集成测试 + 边界情况 + 统计测试 (89/89 pass) |
