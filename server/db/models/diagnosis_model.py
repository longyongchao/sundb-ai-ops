#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : diagnosis_model.py
@Author  : LI
@Date    : 2026
@Desc    : 诊断相关数据库模型
            Reference: D-Bot Paper - Diagnosis Records & Reports
            
            包含：
            1. DiagnosisRecord - 诊断过程记录表
            2. DiagnosisReport - 诊断报告表
            3. DiagnosisTool - 诊断工具表
            4. TestAnomalyCase - 测试异常案例表
"""
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from server.db.base import Base
from datetime import datetime


class DiagnosisRecord(Base):
    """
    诊断过程记录表
    @reference D-Bot Paper Section 6 - Diagnosis Process Trace
    
    存储每次诊断的完整过程数据，包括：
    - 异常信息输入
    - 树搜索Trace（Thought→Action→Observation迭代）
    - 根因分析结果
    - 解决方案建议
    - DeepSeek Token消耗统计
    """
    __tablename__ = 'diagnosis_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='诊断记录ID')
    user_id = Column(Integer, nullable=True, comment='用户ID（预留字段，暂不关联外键）')
    
    anomaly_type = Column(String(100), nullable=False, comment='异常类型，如CPU High、Slow Query等')
    anomaly_description = Column(Text, nullable=False, comment='异常详细描述')
    anomaly_severity = Column(String(20), default='medium', comment='异常严重程度：low/medium/high/critical')
    anomaly_metadata = Column(JSON, nullable=True, comment='异常元数据（JSON格式），如时间戳、来源等')
    
    tree_search_trace = Column(Text, nullable=True, comment='树搜索完整Trace（JSON格式），包含所有推理步骤')
    reasoning_steps_count = Column(Integer, default=0, comment='推理步骤数量')
    max_search_depth = Column(Integer, default=0, comment='树搜索最大深度')
    pruned_nodes_count = Column(Integer, default=0, comment='剪枝节点数量')
    reflection_count = Column(Integer, default=0, comment='反思次数')
    
    root_causes = Column(Text, nullable=True, comment='根因列表（JSON格式）')
    solutions = Column(Text, nullable=True, comment='解决方案列表（JSON格式）')
    confidence = Column(Float, default=0.0, comment='诊断置信度（0-1）')
    
    deepseek_tokens_input = Column(Integer, default=0, comment='DeepSeek输入Token数')
    deepseek_tokens_output = Column(Integer, default=0, comment='DeepSeek输出Token数')
    deepseek_tokens_total = Column(Integer, default=0, comment='DeepSeek总Token消耗')
    
    diagnosis_time = Column(Float, default=0.0, comment='诊断耗时（秒）')
    status = Column(String(20), default='completed', comment='诊断状态：running/completed/failed')
    error_message = Column(Text, nullable=True, comment='错误信息（如果诊断失败）')
    
    knowledge_chunks_used = Column(Integer, default=0, comment='使用的知识块数量')
    tools_called = Column(Text, nullable=True, comment='调用的工具列表（JSON格式）')
    
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    report = relationship("DiagnosisReport", back_populates="record", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<DiagnosisRecord(id={self.id}, anomaly_type='{self.anomaly_type}', status='{self.status}', confidence={self.confidence})>"
    
    def to_dict(self):
        import json
        return {
            "id": self.id,
            "user_id": self.user_id,
            "anomaly_type": self.anomaly_type,
            "anomaly_description": self.anomaly_description,
            "anomaly_severity": self.anomaly_severity,
            "anomaly_metadata": self.anomaly_metadata,
            "reasoning_steps_count": self.reasoning_steps_count,
            "max_search_depth": self.max_search_depth,
            "pruned_nodes_count": self.pruned_nodes_count,
            "reflection_count": self.reflection_count,
            "root_causes": json.loads(self.root_causes) if self.root_causes else [],
            "solutions": json.loads(self.solutions) if self.solutions else [],
            "confidence": self.confidence,
            "deepseek_tokens_total": self.deepseek_tokens_total,
            "diagnosis_time": self.diagnosis_time,
            "status": self.status,
            "knowledge_chunks_used": self.knowledge_chunks_used,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "update_time": self.update_time.isoformat() if self.update_time else None
        }


class DiagnosisReport(Base):
    """
    诊断报告表
    @reference D-Bot Paper Section 6 - Diagnosis Report Generation
    
    存储诊断完成后生成的完整报告，与诊断记录一对一关联
    """
    __tablename__ = 'diagnosis_reports'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='报告ID')
    record_id = Column(Integer, ForeignKey('diagnosis_records.id'), nullable=False, unique=True, comment='关联的诊断记录ID')
    
    report_title = Column(String(255), nullable=True, comment='报告标题')
    report_content = Column(Text, nullable=False, comment='完整报告内容（Markdown格式）')
    report_summary = Column(Text, nullable=True, comment='报告摘要')
    report_format = Column(String(20), default='markdown', comment='报告格式：markdown/html/json')
    
    root_cause_summary = Column(Text, nullable=True, comment='根因摘要')
    solution_summary = Column(Text, nullable=True, comment='解决方案摘要')
    risk_assessment = Column(String(50), nullable=True, comment='风险评估：low/medium/high')
    
    is_exported = Column(Boolean, default=False, comment='是否已导出')
    export_time = Column(DateTime, nullable=True, comment='导出时间')
    export_format = Column(String(20), nullable=True, comment='导出格式')
    
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    record = relationship("DiagnosisRecord", back_populates="report")
    
    def __repr__(self):
        return f"<DiagnosisReport(id={self.id}, record_id={self.record_id}, title='{self.report_title}')>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "report_title": self.report_title,
            "report_content": self.report_content,
            "report_summary": self.report_summary,
            "report_format": self.report_format,
            "root_cause_summary": self.root_cause_summary,
            "solution_summary": self.solution_summary,
            "risk_assessment": self.risk_assessment,
            "is_exported": self.is_exported,
            "create_time": self.create_time.isoformat() if self.create_time else None
        }


class DiagnosisTool(Base):
    """
    诊断工具表
    @reference D-Bot Paper Section 5 - Tool Matching
    
    存储可用的诊断工具信息，替代硬编码的工具定义
    支持动态扩展诊断工具
    """
    __tablename__ = 'diagnosis_tools'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='工具ID')
    tool_name = Column(String(100), unique=True, nullable=False, comment='工具名称，如obtain_metric_values')
    tool_display_name = Column(String(100), nullable=True, comment='工具显示名称')
    tool_description = Column(Text, nullable=True, comment='工具功能描述')
    tool_category = Column(String(50), default='diagnostic', comment='工具类别：diagnostic/analysis/action')
    
    input_schema = Column(Text, nullable=True, comment='输入参数Schema（JSON格式）')
    output_schema = Column(Text, nullable=True, comment='输出结果Schema（JSON格式）')
    example_usage = Column(Text, nullable=True, comment='使用示例（JSON格式）')
    
    related_metrics = Column(Text, nullable=True, comment='相关指标列表（JSON格式）')
    related_experts = Column(Text, nullable=True, comment='关联专家列表（JSON格式），如["cpu_expert", "memory_expert"]')
    
    execution_sql = Column(Text, nullable=True, comment='执行的SQL模板')
    execution_function = Column(String(100), nullable=True, comment='执行的Python函数名')
    
    is_active = Column(Boolean, default=True, comment='是否启用')
    priority = Column(Integer, default=0, comment='优先级，数字越大优先级越高')
    
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f"<DiagnosisTool(id={self.id}, name='{self.tool_name}', category='{self.tool_category}')>"
    
    def to_dict(self):
        import json
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "tool_display_name": self.tool_display_name,
            "tool_description": self.tool_description,
            "tool_category": self.tool_category,
            "input_schema": json.loads(self.input_schema) if self.input_schema else None,
            "output_schema": json.loads(self.output_schema) if self.output_schema else None,
            "related_metrics": json.loads(self.related_metrics) if self.related_metrics else [],
            "related_experts": json.loads(self.related_experts) if self.related_experts else [],
            "is_active": self.is_active,
            "priority": self.priority
        }


class TestAnomalyCase(Base):
    """
    测试异常案例表
    @reference D-Bot Paper Section 8 - Experiments
    
    存储用于验证诊断准确性的测试案例
    包含模拟的异常场景和预期的根因/解决方案
    """
    __tablename__ = 'test_anomaly_cases'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='案例ID')
    case_name = Column(String(100), nullable=False, comment='案例名称')
    case_description = Column(Text, nullable=True, comment='案例描述')
    
    anomaly_type = Column(String(100), nullable=False, comment='异常类型')
    anomaly_description = Column(Text, nullable=False, comment='异常详细描述')
    anomaly_severity = Column(String(20), default='medium', comment='异常严重程度')
    anomaly_metadata = Column(JSON, nullable=True, comment='异常元数据（如模拟的指标数据）')
    
    expected_root_cause = Column(String(200), nullable=False, comment='预期根因')
    expected_root_cause_type = Column(String(100), nullable=True, comment='预期根因类型')
    expected_solution = Column(Text, nullable=True, comment='预期解决方案')
    
    setup_sql = Column(Text, nullable=True, comment='环境准备SQL（用于模拟异常）')
    cleanup_sql = Column(Text, nullable=True, comment='环境清理SQL')
    
    tags = Column(Text, nullable=True, comment='标签（JSON格式），如["cpu", "production"]')
    difficulty_level = Column(String(20), default='medium', comment='难度等级：easy/medium/hard')
    
    is_active = Column(Boolean, default=True, comment='是否启用')
    run_count = Column(Integer, default=0, comment='执行次数')
    success_count = Column(Integer, default=0, comment='成功诊断次数')
    avg_diagnosis_time = Column(Float, default=0.0, comment='平均诊断耗时')
    
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f"<TestAnomalyCase(id={self.id}, name='{self.case_name}', type='{self.anomaly_type}')>"
    
    def to_dict(self):
        import json
        return {
            "id": self.id,
            "case_name": self.case_name,
            "case_description": self.case_description,
            "anomaly_type": self.anomaly_type,
            "anomaly_description": self.anomaly_description,
            "anomaly_severity": self.anomaly_severity,
            "expected_root_cause": self.expected_root_cause,
            "expected_root_cause_type": self.expected_root_cause_type,
            "expected_solution": self.expected_solution,
            "tags": json.loads(self.tags) if self.tags else [],
            "difficulty_level": self.difficulty_level,
            "is_active": self.is_active,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "accuracy_rate": round(self.success_count / self.run_count, 2) if self.run_count > 0 else 0,
            "avg_diagnosis_time": self.avg_diagnosis_time,
            "create_time": self.create_time.isoformat() if self.create_time else None
        }


class MonitoringHistory(Base):
    """
    监控历史表
    @reference D-Bot Paper Section 4 - Real-time Monitoring
    
    存储系统监控指标的历史数据，用于：
    1. 历史趋势分析
    2. 异常发生前后的指标对比
    3. 性能基线建立
    """
    __tablename__ = 'monitoring_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='记录ID')
    
    timestamp = Column(DateTime, nullable=False, index=True, comment='数据采集时间戳')
    
    cpu_usage = Column(Float, default=0.0, comment='CPU使用率（0-1）')
    cpu_user = Column(Float, default=0.0, comment='CPU用户态使用率')
    cpu_system = Column(Float, default=0.0, comment='CPU内核态使用率')
    cpu_iowait = Column(Float, default=0.0, comment='CPU IO等待率')
    cpu_idle = Column(Float, default=1.0, comment='CPU空闲率')
    
    memory_usage = Column(Float, default=0.0, comment='内存使用率（0-1）')
    memory_used_gb = Column(Float, default=0.0, comment='已用内存（GB）')
    memory_total_gb = Column(Float, default=0.0, comment='总内存（GB）')
    swap_usage = Column(Float, default=0.0, comment='Swap使用率')
    
    disk_io_util = Column(Float, default=0.0, comment='磁盘IO使用率')
    disk_io_read_mb = Column(Float, default=0.0, comment='磁盘读取速率（MB/s）')
    disk_io_write_mb = Column(Float, default=0.0, comment='磁盘写入速率（MB/s）')
    disk_latency_ms = Column(Float, default=0.0, comment='磁盘延迟（毫秒）')
    
    load_1m = Column(Float, default=0.0, comment='1分钟负载')
    load_5m = Column(Float, default=0.0, comment='5分钟负载')
    load_15m = Column(Float, default=0.0, comment='15分钟负载')
    
    active_connections = Column(Integer, default=0, comment='活跃数据库连接数')
    max_connections = Column(Integer, default=100, comment='最大连接数')
    idle_connections = Column(Integer, default=0, comment='空闲连接数')
    waiting_connections = Column(Integer, default=0, comment='等待中的连接数')
    
    slow_query_count = Column(Integer, default=0, comment='慢查询数量')
    avg_query_time = Column(Float, default=0.0, comment='平均查询时间（秒）')
    tps = Column(Integer, default=0, comment='每秒事务数')
    
    cache_hit_ratio = Column(Float, default=0.0, comment='缓存命中率')
    temp_files = Column(Integer, default=0, comment='临时文件数量')
    
    checkpoint_count = Column(Integer, default=0, comment='检查点次数')
    wal_files = Column(Integer, default=0, comment='WAL文件数量')
    
    extra_metrics = Column(JSON, nullable=True, comment='额外指标（JSON格式）')
    
    created_at = Column(DateTime, default=datetime.now, comment='记录创建时间')
    
    def __repr__(self):
        return f"<MonitoringHistory(id={self.id}, timestamp='{self.timestamp}', cpu={self.cpu_usage:.2%})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "disk_io_util": self.disk_io_util,
            "load_1m": self.load_1m,
            "active_connections": self.active_connections,
            "slow_query_count": self.slow_query_count,
            "cache_hit_ratio": self.cache_hit_ratio,
            "tps": self.tps,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class AlertHistory(Base):
    """
    告警历史表
    @reference D-Bot Paper Section 4 - Anomaly Detection
    
    存储系统告警记录，用于：
    1. 告警历史追溯
    2. 告警频率统计
    3. 诊断效果验证
    """
    __tablename__ = 'alert_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='告警ID')
    
    alert_type = Column(String(50), nullable=False, index=True, comment='告警类型：CPU_HIGH/MEMORY_HIGH/DISK_IO_HIGH/SLOW_QUERY/DEADLOCK等')
    alert_level = Column(String(20), default='warning', comment='告警级别：info/warning/critical')
    alert_source = Column(String(100), default='auto_detector', comment='告警来源：auto_detector/manual/testcase')
    
    alert_title = Column(String(255), nullable=True, comment='告警标题')
    alert_message = Column(Text, nullable=True, comment='告警详细信息')
    
    metrics_snapshot = Column(JSON, nullable=True, comment='告警时刻的指标快照（JSON格式）')
    threshold_value = Column(Float, default=0.0, comment='触发阈值')
    actual_value = Column(Float, default=0.0, comment='实际值')
    
    is_diagnosed = Column(Boolean, default=False, comment='是否已触发诊断')
    diagnosis_report_id = Column(Integer, ForeignKey('diagnosis_reports.id'), nullable=True, comment='关联的诊断报告ID')
    diagnosis_triggered_at = Column(DateTime, nullable=True, comment='诊断触发时间')
    
    status = Column(String(20), default='active', comment='告警状态：active/resolved/acknowledged')
    resolved_at = Column(DateTime, nullable=True, comment='告警解决时间')
    resolved_by = Column(String(100), nullable=True, comment='解决者')
    
    tags = Column(JSON, nullable=True, comment='标签（JSON格式）')
    
    created_at = Column(DateTime, default=datetime.now, index=True, comment='告警创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    diagnosis_report = relationship("DiagnosisReport", backref="alerts")
    
    def __repr__(self):
        return f"<AlertHistory(id={self.id}, type='{self.alert_type}', level='{self.alert_level}', diagnosed={self.is_diagnosed})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "alert_level": self.alert_level,
            "alert_source": self.alert_source,
            "alert_title": self.alert_title,
            "alert_message": self.alert_message,
            "metrics_snapshot": self.metrics_snapshot,
            "threshold_value": self.threshold_value,
            "actual_value": self.actual_value,
            "is_diagnosed": self.is_diagnosed,
            "diagnosis_report_id": self.diagnosis_report_id,
            "status": self.status,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


class Notification(Base):
    """
    通知表
    @reference D-Bot Paper Section 6 - User Notification
    
    存储系统通知，用于：
    1. 自动诊断完成通知
    2. 异常告警通知
    3. 系统消息通知
    """
    __tablename__ = 'notifications'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='通知ID')
    
    notification_type = Column(String(50), nullable=False, default='diagnosis', comment='通知类型：diagnosis/alert/system')
    title = Column(String(255), nullable=False, comment='通知标题')
    content = Column(Text, nullable=True, comment='通知内容')
    
    severity = Column(String(20), default='info', comment='严重程度：info/warning/critical')
    
    is_read = Column(Boolean, default=False, comment='是否已读')
    read_at = Column(DateTime, nullable=True, comment='阅读时间')
    
    related_id = Column(Integer, nullable=True, comment='关联ID（如诊断报告ID）')
    related_type = Column(String(50), nullable=True, comment='关联类型：diagnosis_report/alert')
    
    action_url = Column(String(255), nullable=True, comment='点击跳转URL')
    action_text = Column(String(100), nullable=True, comment='操作按钮文字')
    
    extra_data = Column(JSON, nullable=True, comment='额外数据（JSON格式）')
    
    created_at = Column(DateTime, default=datetime.now, index=True, comment='创建时间')
    expires_at = Column(DateTime, nullable=True, comment='过期时间')
    
    def __repr__(self):
        return f"<Notification(id={self.id}, type='{self.notification_type}', title='{self.title}', read={self.is_read})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "notification_type": self.notification_type,
            "title": self.title,
            "content": self.content,
            "severity": self.severity,
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "related_id": self.related_id,
            "related_type": self.related_type,
            "action_url": self.action_url,
            "action_text": self.action_text,
            "extra_data": self.extra_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
