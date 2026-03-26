# 混合场景

## 场景描述

实际生产环境中，数据库性能问题往往是多种因素叠加的结果。本场景模拟多种异常同时发生的复杂情况，验证诊断引擎的综合分析能力。

## 包含用例

| 用例ID | 用例名称 | 难度 | 描述 |
|--------|----------|------|------|
| case_08_cpu_mem | CPU+内存双高 | Medium | CPU和内存同时达到高水位 |
| case_09_query_io | 慢查询+IO瓶颈 | Medium | 慢查询导致IO压力 |
| case_10_full_stack | 全栈性能问题 | Hard | CPU、内存、IO全面告警 |
| case_11_vacuum | VACUUM操作异常 | Medium | VACUUM操作影响性能 |
| case_12_connection | 连接池耗尽 | Medium | 连接数达到上限 |
| case_13_temp_file | 临时文件过多 | Medium | 大量临时文件影响性能 |
| case_14_replication | 复制延迟 | Medium | 主从复制延迟告警 |
| case_15_index_bloat | 索引膨胀 | Medium | 索引空间占用过大 |
| case_16_table_bloat | 表膨胀 | Medium | 表空间碎片化严重 |
| case_17_stats_stale | 统计信息过期 | Easy | 统计信息未及时更新 |
| case_18_subquery | 子查询性能问题 | Medium | 复杂子查询导致性能下降 |

## 典型特征

- 多个指标同时异常
- 问题之间可能存在因果关系
- 需要综合分析找出根本原因

## 诊断要点

1. 识别主要矛盾和次要矛盾
2. 分析指标之间的关联性
3. 找出问题的根本原因
4. 提出综合解决方案
