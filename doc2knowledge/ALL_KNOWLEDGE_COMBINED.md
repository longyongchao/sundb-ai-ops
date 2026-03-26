# DB-GPT 数据库诊断专家知识库汇总

> 本文件整合了项目中的所有核心知识，可直接上传到知识库使用
> 生成时间：2026年3月

---

## 一、根因诊断知识（来自 root_causes_dbmind.jsonl）

### 1. large_table - 大表问题
- **描述**：检查查询相关表是否因表大小或元组数量过多而成为性能问题的根因。如果表的存活元组和死元组数量超过阈值，或表大小超过总大小阈值，则被认为是大型表。
- **相关指标**：live_tuples, dead_tuples, table_size

### 2. many_dead_tuples - 大量死元组
- **描述**：检查查询相关表是否存在过多死元组，这可能导致表膨胀并影响查询性能。如果表的死元组率超过阈值，则被认为是根因。
- **建议**：及时清理死元组以避免影响查询性能。
- **相关指标**：dead_rate, live_tuples, dead_tuples, table_size

### 3. heavy_scan_operator - 重扫描算子
- **描述**：诊断查询相关表是否存在重扫描算子。如果表有大量获取的元组且命中率低，或存在昂贵的顺序扫描、索引扫描或堆扫描，则被认为是根因。
- **建议**：调整以避免大扫描，确认内表是否有索引，避免count操作，考虑索引过滤能力。
- **相关指标**：hit_rate, n_tuples_fetched, n_tuples_returned, total_cost

### 4. abnormal_plan_time - 异常计划时间
- **描述**：检查慢SQL实例中是否存在异常的执行计划生成。如果计划时间与执行时间的比率超过阈值，且硬解析次数大于软解析次数，则表示计划时间异常。
- **建议**：修改业务以支持PBE。
- **相关指标**：n_soft_parse, n_hard_parse, plan_time, exc_time

### 5. unused_and_redundant_index - 无用或冗余索引
- **描述**：检查查询相关表中是否存在未使用或冗余的索引。未使用的索引是长时间未被使用的索引，冗余索引是查询不需要的索引。
- **建议**：清理无用或冗余索引。
- **相关指标**：Large table, Unused index info, Redundant index info

### 6. update_large_data - 大量数据更新
- **描述**：检查表是否有大量元组被更新。如果更新的元组数量超过阈值，则被认为是根因。
- **建议**：根据业务需求进行调整。
- **相关指标**：n_tuples_updated, updated_tuples_threshold, live_tuples, rows

### 7. insert_large_data - 大量数据插入
- **描述**：检查查询相关表是否有大量元组被插入。如果插入的元组数量超过阈值，则被认为是根因。
- **建议**：根据业务需求进行调整。
- **相关指标**：n_tuples_inserted, inserted_tuples_threshold, live_tuples, rows

### 8. delete_large_data - 大量数据删除
- **描述**：检查表是否有大量元组待删除。如果删除的元组数量超过阈值，则被认为是根因。
- **建议**：根据业务需求进行调整。
- **相关指标**：n_tuples_deleted, deleted_tuples_threshold, live_tuples, rows

### 9. too_many_index - 索引过多
- **描述**：检查表中是否存在过多索引，这可能对插入和更新操作的性能产生负面影响。
- **建议**：过多的索引会减慢insert、delete和update语句。
- **相关指标**：index_number_threshold, len(table.index)

### 10. disk_spill - 磁盘溢出
- **描述**：检查SQL执行过程中是否可能发生磁盘溢出。如果排序溢出计数或哈希溢出计数超过阈值，则表示SORT/HASH操作可能溢出到磁盘。
- **建议**：分析业务是否需要调整work_mem和shared_buffers等参数。
- **相关指标**：sort_spill_count, hash_spill_count, sort_rate_threshold, cost_rate_threshold

### 11. vacuum_event - VACUUM事件
- **描述**：检查查询相关表是否进行了VACUUM操作，这可能是慢SQL查询的潜在根因。
- **相关指标**：table_structure, slow_sql_param, vacuum_delay, start_at, duration_time

### 12. analyze_event - ANALYZE事件
- **描述**：检查查询相关表是否进行了ANALYZE操作。
- **相关指标**：table_structure, slow_sql_param, analyze_delay, start_at, duration_time

### 13. workload_contention - 工作负载竞争
- **描述**：诊断数据库系统中的工作负载竞争问题，包括异常的CPU和内存资源使用、数据库数据目录空间不足、连接或线程池使用过多等。
- **相关指标**：process_used_memory, max_process_memory, tps, max_connections, db_cpu_usage, db_mem_usage

### 14. cpu_resource_contention - CPU资源竞争
- **描述**：检查是否存在其他进程对CPU资源的竞争。如果这些进程的最大CPU使用率超过阈值，则被认为是根因。
- **建议**：处理系统中的异常进程。
- **相关指标**：user_cpu_usage, system_cpu_contention

### 15. io_resource_contention - IO资源竞争
- **描述**：检查系统中的IO资源竞争。如果每个设备的最大IO利用率超过阈值，则存在竞争。
- **建议**：检查数据库外的竞争进程和数据库内的长事务。
- **相关指标**：IO utilization (IO-Utils)

### 16. memory_resource_contention - 内存资源竞争
- **描述**：检查是否存在其他进程对内存资源的竞争。如果最大系统内存使用率超过阈值，则被认为是根因。
- **建议**：检查可能消耗资源的外部进程。
- **相关指标**：system_mem_usage, system_mem_contention

### 17. abnormal_network_status - 异常网络状态
- **描述**：通过分析丢包率和带宽使用情况检查异常网络状态。
- **相关指标**：package_drop_rate_threshold, network_bandwidth_usage_threshold

### 18. os_resource_contention - 操作系统资源竞争
- **描述**：检查数据库外的其他进程是否占用了过多的句柄资源。如果系统文件描述符占用率超过阈值，则被认为是根因。
- **相关指标**：process_fds_rate, handler_occupation_threshold

### 19. database_wait_event - 数据库等待事件
- **描述**：检查数据库中是否存在等待事件。
- **相关指标**：wait_event_info, wait_status, wait_event

### 20. lack_of_statistics - 统计信息缺失
- **描述**：检查业务表中是否存在更新的统计信息。如果统计信息长时间未更新，可能导致执行计划严重下降。
- **建议**：及时更新统计信息以帮助规划器选择最合适的计划。
- **相关指标**：data_changed_delay, tuples_diff, schema_name, table_name

### 21. missing_index - 缺失索引
- **描述**：使用workload-index-recommend接口检查是否存在所需的索引。
- **建议**：如果推荐索引信息可用，则表示缺少所需索引。

### 22. poor_join_performance - 连接性能差
- **描述**：诊断连接操作的性能问题。主要原因包括：1) GUC参数enable_hashjoin设置为off；2) 优化器错误选择NestLoop算子；3) 连接操作涉及大量数据；4) 连接算子代价昂贵。
- **建议**：设置enable_hashjoin为on，优化SQL结构以减少JOIN代价，使用临时表过滤数据。
- **相关指标**：total_cost, cost_rate_threshold, nestloop_rows_threshold, large_join_threshold

### 23. complex_boolean_expression - 复杂布尔表达式
- **描述**：检查SQL查询中是否存在"in"子句过长的问题，这可能导致查询执行缓慢。
- **建议**：如果"in"子句长度超过阈值，考虑重写查询。
- **相关指标**：slow_sql_instance.query, expression_number, large_in_list_threshold

### 24. string_matching - 字符串匹配
- **描述**：检查可能导致索引列失效的某些条件，包括使用某些函数或正则表达式选择列，以及使用"order by random()"操作。
- **建议**：避免在索引列上使用函数或表达式操作，或为其创建表达式索引。
- **相关指标**：existing_functions, matching_results, seq_scan_properties

### 25. complex_execution_plan - 复杂执行计划
- **描述**：检查SQL语句中的复杂执行计划。两种情况可能导致复杂执行计划：1) 大量join或group操作；2) 基于高度的非常复杂的执行计划。
- **相关指标**：plan_parse_info, plan_height, join_operator

### 26. correlated_subquery - 关联子查询
- **描述**：检查SQL执行中是否存在无法提升的子查询。如果执行计划包含'SubPlan'关键字且SQL结构不支持Sublink-Release，则需要重写SQL。
- **建议**：重写语句以支持sublink-release。
- **相关指标**：SubPlan, exists_subquery

### 27. poor_aggregation_performance - 聚合性能差
- **描述**：诊断SQL查询中的聚合性能问题。四个潜在根因：1) GUC参数enable_hashagg设置为off；2) 查询包含count(distinct col)等场景；3) GroupAgg算子代价昂贵；4) HashAgg算子代价昂贵。
- **相关指标**：total_cost, cost_rate_threshold, enable_hashagg, GroupAggregate, HashAggregate

### 28. abnormal_sql_structure - 异常SQL结构
- **描述**：检查SQL结构中可能导致性能问题的特定问题。如果存在重写的SQL信息，则表示SQL结构异常。
- **相关指标**：rewritten_sql_info

### 29. timed_task_conflict - 定时任务冲突
- **描述**：后台定时任务（如统计信息收集、数据清理、备份作业等）与业务查询在同一时段运行，导致资源竞争。

---

## 二、慢SQL诊断专家知识

### 锁竞争 (LOCK_CONTENTION)
当多个数据库会话尝试同时访问或修改相同的数据资源（如表、行）时，可能会发生锁竞争，导致其中一个或多个会话被阻塞，从而引起查询变慢。

### 大量死元组 (MANY_DEAD_TUPLES)
当表中存在大量已删除或更新后留下的旧版本行（死元组）时，会导致表膨胀，增加查询时需要扫描的数据量，从而降低查询性能。

### 大数据量查询 (FETCH_LARGE_DATA)
当SQL执行计划需要扫描大量元组时，会导致查询性能显著下降。这通常发生在全表扫描或索引效率低下的场景中。

### 无用或冗余索引
当SQL查询执行计划扫描大量元组时，可能是因为存在无用或冗余的索引。这些索引未被查询使用，但会增加数据库的维护开销。

### 批量插入数据
当数据库执行批量插入大量数据时，可能导致表膨胀、统计信息过时，并显著增加后续查询的执行时间。

### work_mem设置过低导致算子落盘
当work_mem参数设置过低时，数据库在执行SORT或HASH等需要内存的操作时，可能因内存不足而将中间结果写入磁盘（DISK_SPILL），这会显著降低查询性能。

### 外部进程导致的高磁盘I/O
数据库服务器上的外部进程（如使用`dd`命令进行文件读写）可能大量消耗磁盘I/O资源，导致数据库查询的I/O等待时间增加。

### 统计信息缺失
当数据库表的统计信息过时或缺失时，查询优化器无法准确评估不同执行计划的成本，可能导致选择不当的执行计划。

### 连接性能问题 (POOR_JOIN_PERFORMANCE)
当SQL查询涉及连接操作时，可能出现连接性能问题，这通常源于未选用最优连接算子（如hash join）或涉及大量元组的连接操作。

### 禁用哈希连接影响
通过设置数据库参数`enable_hashjoin`为off，可以禁用哈希连接方法，从而影响查询优化器对多表连接查询的连接策略选择。

### NOT IN子句元素过多
当SQL查询中的NOT IN子句包含过多元素时，会导致查询性能显著下降。

### 函数导致索引失效
在查询的WHERE子句中对索引列使用函数（例如lower(column)）会阻止数据库使用该列上的现有B树索引，导致查询执行计划从高效的索引扫描退化为低效的全表扫描。

### 复杂执行计划优化
对于涉及多表连接（JOIN）或包含子查询的复杂查询，其执行计划可能效率低下，导致查询性能缓慢。

### 聚合算子选择不当
SQL查询的聚合性能问题可能源于优化器选择了低效的聚合算子，例如使用了排序+GroupAgg而非更高效的HashAgg。

### COUNT(DISTINCT)导致的低效聚合
在SQL查询中使用COUNT(DISTINCT)子句可能导致优化器选择低效的排序+GroupAgg聚合算子，而不是更高效的HashAgg算子。

### EXISTS子查询性能优化
对于包含EXISTS子查询的语句，如果子查询中的表缺少合适的索引，可能导致全表扫描，从而严重影响查询性能。

---

## 三、诊断方法与步骤

### 如何诊断SQL执行计划中扫描大量元组导致的性能问题？
当SQL执行计划显示扫描了大量元组时，可能的原因包括：
1. 存在无用或冗余索引 - 通过查询pg_stat_user_indexes检查索引使用情况
2. 近期进行了批量数据插入 - 检查插入操作的执行时间并分析影响
3. 表上索引过多 - 过多的索引会增加维护开销并可能误导查询优化器

诊断步骤：
- 首先检查索引使用情况，识别并移除无用索引
- 其次分析是否有大规模数据操作，并考虑在操作后更新统计信息
- 最后评估索引数量，优化索引策略

### 如何诊断由外部进程导致的磁盘I/O资源紧张问题？
当SQL执行时间异常延长时：
1. 检查磁盘I/O利用率
2. 如果IO利用率超过预设阈值（如持续高于80%），则表明存在I/O资源紧张
3. 排查系统上是否有外部进程正在大量占用I/O资源
4. 确认后，停止该占用进程，并观察SQL执行时间是否显著恢复

### 如何诊断复杂查询的性能问题？
对于涉及多表连接和聚合的复杂查询：
1. 分析查询执行计划
2. 检查连接顺序是否高效
3. 评估是否使用了合适的连接算法
4. 确认在连接键和过滤条件上是否有有效的索引

### 如何诊断和解决因函数导致索引失效的查询性能问题？
1. 使用诊断工具检查查询，确认是否因在WHERE子句中对索引列使用了函数而导致索引扫描变为全表扫描
2. 如果确认是此原因，解决方案是创建一个表达式索引

### 如何诊断和优化SQL查询中的聚合性能问题？
1. 检查查询是否包含COUNT(DISTINCT)等可能导致低效操作的子句
2. 重写查询，例如将COUNT(DISTINCT)改写为使用子查询或窗口函数
3. 调整数据库参数，如设置enable_hashagg为on

---

## 四、监控部署指南

### Prometheus 部署
```bash
# 下载
wget https://github.com/prometheus/prometheus/releases/download/v2.25.0/prometheus-2.25.0.linux-amd64.tar.gz -P /tmp
tar -zxpvf prometheus-2.25.0.linux-amd64.tar.gz
cd prometheus-2.25.0.linux-amd64/
cp prometheus /usr/local/bin
cp promtool /usr/local/bin
mkdir /etc/prometheus/
cp prometheus.yml /etc/prometheus/
```

### Grafana 部署
```bash
# 安装
wget https://dl.grafana.com/oss/release/grafana-7.4.3-1.x86_64.rpm
sudo yum install grafana-7.4.3-1.x86_64.rpm

# 设置服务
systemctl daemon-reload
systemctl enable grafana-server.service
systemctl start grafana-server.service
```

### Node Exporter 部署
```bash
wget https://github.com/prometheus/node_exporter/releases/download/v1.1.1/node_exporter-1.1.1.linux-amd64.tar.gz
tar -xvzf node_exporter-1.6.0.linux-amd64.tar.gz
cd node_exporter-1.6.0.linux-amd64
cp -r node_exporter /usr/local/bin/
chmod +x /usr/local/bin/node_exporter
```

### PostgreSQL Exporter 部署
```bash
wget https://github.com/prometheus-community/postgres_exporter/releases/download/v0.11.1/postgres_exporter-0.11.1.linux-amd64.tar.gz
tar -xvzf postgres_exporter-0.11.1.linux-amd64.tar.gz
cd postgres_exporter-0.11.1.linux-amd64/
cp -r postgres_exporter /usr/local/bin/
chmod +x /usr/local/bin/postgres_exporter
```

---

## 五、性能优化建议

### 索引优化
- 定期检查并清理无用或冗余索引
- 为常用查询条件创建合适的索引
- 避免在索引列上使用函数
- 考虑创建表达式索引以支持特定查询模式

### 内存参数调优
- 根据系统内存大小调整work_mem参数
- 确保shared_buffers设置合理
- 监控内存使用情况，避免磁盘溢出

### 统计信息维护
- 定期执行ANALYZE更新统计信息
- 在大批量数据操作后手动更新统计信息
- 监控统计信息的时效性

### 查询优化
- 避免使用SELECT *
- 合理使用索引
- 优化JOIN顺序
- 避免在WHERE子句中对索引列使用函数
- 考虑使用EXISTS替代IN

### 系统资源监控
- 监控CPU、内存、I/O使用率
- 检查是否有外部进程占用资源
- 监控数据库连接数和会话数
- 定期检查锁等待情况

---
