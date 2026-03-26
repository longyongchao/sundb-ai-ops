# 诊断测试文件库

## 概述

本测试文件库为 D-Bot 数据库智能诊断系统提供标准化的测试用例，用于验证诊断引擎的准确性和有效性。共包含 **7 大场景分类**，**19 个测试用例**，覆盖数据库运维中常见的性能异常问题。

## 目录结构

```
diagnostic_test_cases/
├── 01_cpu_high/              # CPU 高负载场景 (2个用例)
│   ├── README.md
│   ├── case_01_sensors.json  # 98个传感器并发插入
│   └── case_02_compute.json  # 复杂计算导致CPU飙升
├── 02_slow_queries/          # 慢查询场景 (2个用例)
│   ├── README.md
│   ├── case_03_full_scan.json    # 全表扫描
│   └── case_04_missing_index.json # 缺失索引
├── 03_lock_contention/       # 锁竞争场景 (1个用例)
│   ├── README.md
│   └── case_05_deadlock.json # 死锁问题
├── 04_memory_high/           # 内存高使用场景 (1个用例)
│   ├── README.md
│   └── case_06_sort_mem.json # 排序内存溢出
├── 05_io_bottleneck/         # IO 瓶颈场景 (1个用例)
│   ├── README.md
│   └── case_07_checkpoint.json   # 检查点风暴
├── 06_mixed_scenarios/       # 混合场景 (11个用例)
│   ├── README.md
│   ├── case_08_cpu_mem.json      # CPU+内存双高
│   ├── case_09_query_io.json     # 慢查询+IO瓶颈
│   ├── case_10_full_stack.json   # 全栈性能问题
│   ├── case_11_vacuum.json       # VACUUM操作异常
│   ├── case_12_connection.json   # 连接池耗尽
│   ├── case_13_temp_file.json    # 临时文件过多
│   ├── case_14_replication.json  # 复制延迟
│   ├── case_15_index_bloat.json  # 索引膨胀
│   ├── case_16_table_bloat.json  # 表膨胀
│   ├── case_17_stats_stale.json  # 统计信息过期
│   └── case_18_subquery.json     # 子查询性能问题
└── 07_edge_cases/            # 边界场景 (1个用例)
    ├── README.md
    └── case_19_idle.json     # 空闲系统误报测试
```

## 测试用例格式规范

每个测试用例 JSON 文件包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `case_id` | string | 是 | 用例唯一标识，格式：case_{序号}_{简短描述} |
| `case_name` | string | 是 | 用例中文名称 |
| `case_description` | string | 是 | 场景详细描述 |
| `category` | string | 是 | 场景分类 |
| `difficulty` | string | 是 | 难度等级 (easy/medium/hard) |
| `alert_type` | string | 是 | 告警类型 |
| `severity` | string | 是 | 严重程度 (critical/warning/info) |
| `start_time` | string | 是 | 异常开始时间戳 |
| `end_time` | string | 是 | 异常结束时间戳 |
| `metrics` | object | 是 | 模拟的监控指标数据 |
| `alerts` | array | 是 | 模拟的告警信息列表 |
| `labels` | array | 是 | 异常标签列表 |
| `expected_root_causes` | array | 是 | 预期根因列表 |
| `expected_solutions` | array | 是 | 预期解决方案列表 |

## 使用方法

### 1. 通过前端界面选择

1. 打开诊断页面
2. 点击「从测试文件库选择」按钮
3. 选择场景分类和具体用例
4. 查看场景说明和预期结果
5. 点击「使用此文件」进行诊断

### 2. 通过 API 调用

```bash
# 获取测试用例列表
GET /api/testcases/list

# 获取单个测试用例详情
GET /api/testcases/{case_id}

# 获取场景分类列表
GET /api/testcases/categories

# 使用测试用例进行诊断
POST /api/diagnose/testcase
{
    "case_id": "case_01_sensors"
}
```

## 统计信息

| 指标 | 数值 |
|------|------|
| 总用例数 | 19 |
| 场景分类 | 7 类 |
| Easy | 3 个 |
| Medium | 11 个 |
| Hard | 5 个 |

## 场景覆盖

| 场景 | 用例数 | 难度分布 |
|------|--------|----------|
| CPU 高负载 | 2 | Easy(1), Medium(1) |
| 慢查询 | 2 | Medium(1), Hard(1) |
| 锁竞争 | 1 | Hard(1) |
| 内存高负载 | 1 | Medium(1) |
| IO 瓶颈 | 1 | Hard(1) |
| 混合场景 | 11 | Easy(2), Medium(7), Hard(2) |
| 边界场景 | 1 | Easy(1) |

## 维护说明

1. 新增用例时，请遵循命名规范: `case_{序号}_{简短描述}.json`
2. 每个用例必须包含完整的 `expected_root_causes` 和 `expected_solutions`
3. 定期运行批量诊断验证用例有效性
4. 更新用例后需同步更新本 README 的统计信息
