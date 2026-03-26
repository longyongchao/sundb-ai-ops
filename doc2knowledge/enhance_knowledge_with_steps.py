#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库增强工具 - 为 root_causes_dbmind.jsonl 添加诊断步骤 (steps) 字段
Reference: D-Bot Paper Section 4.1 - Knowledge Extraction

这个脚本为每个根因知识添加具体的诊断步骤，帮助 LLM 模仿 DBA 行为
"""
import json
import os

# 定义每个根因的诊断步骤
STEPS_MAPPING = {
    "large_table": [
        "1. 查询 pg_stat_user_tables 获取表统计信息",
        "2. 检查表的 live_tuples 和 dead_tuples 数量",
        "3. 使用 pg_total_relation_size() 获取表总大小",
        "4. 评估是否需要分区或归档历史数据",
        "5. 建议创建合适的索引优化查询"
    ],
    "many_dead_tuples": [
        "1. 查询 pg_stat_user_tables 计算 dead_tuple 比例",
        "2. 检查表的膨胀率 (bloat ratio)",
        "3. 分析最后 vacuum 时间",
        "4. 评估是否需要手动执行 VACUUM",
        "5. 建议调整 autovacuum 参数"
    ],
    "heavy_scan_operator": [
        "1. 使用 EXPLAIN ANALYZE 获取查询执行计划",
        "2. 识别 Seq Scan、Index Scan、Bitmap Heap Scan 操作",
        "3. 检查扫描行数与返回行数比例",
        "4. 分析缓存命中率 (heap_blks_hit / heap_blks_read)",
        "5. 建议创建索引或优化查询条件"
    ],
    "abnormal_plan_time": [
        "1. 查询 pg_stat_statements 获取 plan_time 统计",
        "2. 计算 plan_time / execution_time 比例",
        "3. 检查 n_hard_parse 与 n_soft_parse 比例",
        "4. 分析是否存在大量硬解析",
        "5. 建议使用 PBE (Prepared Statement) 减少解析开销"
    ],
    "unused_and_redundant_index": [
        "1. 查询 pg_stat_user_indexes 获取索引使用统计",
        "2. 识别 idx_scan = 0 的未使用索引",
        "3. 检查重复或冗余索引 (相同列组合)",
        "4. 评估索引大小和维护开销",
        "5. 建议删除未使用或冗余索引"
    ],
    "update_large_data": [
        "1. 查询 pg_stat_statements 获取更新语句统计",
        "2. 分析 n_tuples_updated 与执行时间关系",
        "3. 检查是否存在全表更新操作",
        "4. 评估是否需要分批处理",
        "5. 建议优化更新条件或使用批量操作"
    ],
    "insert_large_data": [
        "1. 监控 pg_stat_user_tables 的 n_tup_ins 增长",
        "2. 检查批量插入操作的频率和大小",
        "3. 分析 WAL 写入量和 checkpoint 频率",
        "4. 评估是否需要调整 shared_buffers",
        "5. 建议使用 COPY 或批量插入优化"
    ],
    "delete_large_data": [
        "1. 查询 pg_stat_user_tables 的 n_tup_del 统计",
        "2. 分析删除操作产生的 dead tuples 数量",
        "3. 检查删除后是否及时执行 VACUUM",
        "4. 评估是否需要 TRUNCATE 替代 DELETE",
        "5. 建议分批删除并定期清理"
    ],
    "too_many_index": [
        "1. 统计表的索引数量 (pg_indexes)",
        "2. 检查索引与列的比例",
        "3. 分析索引维护对写入性能的影响",
        "4. 评估索引的实际使用情况",
        "5. 建议合并或删除低效索引"
    ],
    "disk_spill": [
        "1. 检查 work_mem 配置参数",
        "2. 分析 EXPLAIN 中的 Temp File 使用",
        "3. 监控 pg_stat_statements 的 sort_spill_count",
        "4. 识别 hash_spill_count 高的查询",
        "5. 建议增加 work_mem 或优化查询"
    ],
    "vacuum_event": [
        "1. 查询 pg_stat_user_tables 的 last_vacuum 时间",
        "2. 检查 autovacuum 是否正常工作",
        "3. 分析 vacuum 与慢查询的时间关联",
        "4. 评估 vacuum 对 I/O 的影响",
        "5. 建议调整 autovacuum_vacuum_scale_factor"
    ],
    "analyze_event": [
        "1. 查询 pg_stat_user_tables 的 last_analyze 时间",
        "2. 检查统计信息是否过期",
        "3. 分析执行计划是否因统计信息不准而变差",
        "4. 评估 ANALYZE 对查询性能的影响",
        "5. 建议定期执行 ANALYZE 更新统计信息"
    ],
    "workload_contention": [
        "1. 监控 pg_stat_activity 的活跃连接数",
        "2. 分析 CPU、内存、I/O 资源使用率",
        "3. 检查是否有资源争抢现象",
        "4. 识别异常进程或长事务",
        "5. 建议优化连接池或扩容资源"
    ],
    "cpu_resource_contention": [
        "1. 监控数据库进程的 CPU 使用率",
        "2. 分析系统整体 CPU 负载",
        "3. 检查是否有 CPU 密集型查询",
        "4. 识别外部进程对 CPU 的争抢",
        "5. 建议优化查询或增加 CPU 资源"
    ],
    "io_resource_contention": [
        "1. 监控磁盘 I/O 利用率 (iostat)",
        "2. 分析 pg_statio_user_tables 的块读取",
        "3. 检查是否有全表扫描导致的高 I/O",
        "4. 识别 I/O 密集型查询",
        "5. 建议创建索引或优化存储"
    ],
    "memory_resource_contention": [
        "1. 监控 shared_buffers 使用率",
        "2. 分析系统内存和 swap 使用",
        "3. 检查是否有内存泄漏",
        "4. 评估工作集大小与内存配置",
        "5. 建议调整 shared_buffers 或 effective_cache_size"
    ],
    "abnormal_network_status": [
        "1. 检查网络带宽使用率",
        "2. 监控网络丢包率 (ifconfig/ip -s link)",
        "3. 分析连接延迟和响应时间",
        "4. 识别网络瓶颈",
        "5. 建议优化网络配置或增加带宽"
    ],
    "os_resource_contention": [
        "1. 监控文件描述符使用情况",
        "2. 检查系统句柄限制 (ulimit -n)",
        "3. 分析进程资源占用",
        "4. 识别资源泄漏",
        "5. 建议调整系统参数或重启服务"
    ],
    "database_wait_event": [
        "1. 查询 pg_stat_activity 的 wait_event",
        "2. 分析等待事件类型和分布",
        "3. 检查锁等待和 I/O 等待",
        "4. 识别热点资源和瓶颈",
        "5. 建议优化锁策略或资源分配"
    ],
    "lack_of_statistics": [
        "1. 查询 pg_stat_user_tables 的 last_analyze",
        "2. 检查统计信息的新鲜度",
        "3. 分析执行计划是否准确",
        "4. 评估统计信息对性能的影响",
        "5. 建议执行 ANALYZE 更新统计信息"
    ],
    # 添加更多通用步骤
    "default": [
        "1. 收集系统指标和数据库统计信息",
        "2. 分析 pg_stat_activity 查看活跃会话",
        "3. 检查 pg_stat_statements 获取慢查询",
        "4. 识别异常模式和根因",
        "5. 提供针对性的优化建议"
    ]
}


def enhance_knowledge_with_steps(input_file: str, output_file: str):
    """
    为知识库添加 steps 字段
    
    Args:
        input_file: 原始知识库文件路径
        output_file: 增强后的知识库文件路径
    """
    print(f"📚 开始增强知识库: {input_file}")
    
    # 读取原始知识库
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    enhanced_count = 0
    default_count = 0
    
    # 为每个知识块添加 steps
    for item in data:
        cause_name = item.get('cause_name', '')
        
        # 查找对应的 steps
        if cause_name in STEPS_MAPPING:
            item['steps'] = STEPS_MAPPING[cause_name]
            enhanced_count += 1
            print(f"  ✅ {cause_name}: 添加 {len(STEPS_MAPPING[cause_name])} 个步骤")
        else:
            # 使用默认步骤
            item['steps'] = STEPS_MAPPING['default']
            default_count += 1
            print(f"  ⚠️  {cause_name}: 使用默认步骤")
    
    # 保存增强后的知识库
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ 知识库增强完成!")
    print(f"   总知识数: {len(data)}")
    print(f"   增强步骤: {enhanced_count}")
    print(f"   默认步骤: {default_count}")
    print(f"   输出文件: {output_file}")
    print(f"{'='*60}\n")
    
    return output_file


def verify_enhanced_knowledge(file_path: str):
    """验证增强后的知识库"""
    print(f"🔍 验证增强后的知识库: {file_path}\n")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("知识库样本（前3条）:\n")
    for i, item in enumerate(data[:3], 1):
        print(f"{i}. {item['cause_name']}")
        print(f"   描述: {item['desc'][:80]}...")
        print(f"   指标: {item['metrics'][:60]}...")
        print(f"   步骤:")
        for step in item.get('steps', [])[:3]:
            print(f"      - {step}")
        if len(item.get('steps', [])) > 3:
            print(f"      ... 共 {len(item['steps'])} 个步骤")
        print()
    
    # 统计信息
    has_steps = sum(1 for item in data if 'steps' in item and item['steps'])
    print(f"统计: {has_steps}/{len(data)} 条知识包含 steps 字段")


if __name__ == "__main__":
    # 文件路径
    input_file = "root_causes_dbmind.jsonl"
    output_file = "root_causes_dbmind_enhanced.jsonl"
    
    # 执行增强
    enhance_knowledge_with_steps(input_file, output_file)
    
    # 验证结果
    verify_enhanced_knowledge(output_file)
    
    print("\n💡 使用建议:")
    print("   1. 检查增强后的知识库内容")
    print("   2. 如满意，替换原文件: cp root_causes_dbmind_enhanced.jsonl root_causes_dbmind.jsonl")
    print("   3. 重启服务加载新知识库")
