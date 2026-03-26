"""
文件解析模块 - 纯文件解析诊断（不依赖本机数据库）
Reference: D-Bot Paper Section 4.1 - Anomaly Information Extraction

核心功能：
1. 解析上传的JSON日志文件
2. 提取慢查询SQL、执行计划、系统指标、表大小、会话信息
3. 完全脱离本机数据库依赖，支持任意环境的日志文件
"""
import json
import os
import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedAnomalyData:
    """解析后的异常数据结构"""
    alert_type: str = "Database Performance Anomaly"
    description: str = ""
    severity: str = "medium"
    timestamp: str = ""
    source: str = "uploaded_file"
    
    slow_queries: List[Dict] = field(default_factory=list)
    active_sessions: List[Dict] = field(default_factory=list)
    table_sizes: Dict[str, int] = field(default_factory=dict)
    
    cpu_metrics: Dict = field(default_factory=dict)
    memory_metrics: Dict = field(default_factory=dict)
    io_metrics: Dict = field(default_factory=dict)
    
    execution_plans: List[Dict] = field(default_factory=list)
    wait_events: List[Dict] = field(default_factory=list)
    lock_info: List[Dict] = field(default_factory=list)
    
    raw_data: Dict = field(default_factory=dict)
    file_name: str = ""


class FileParser:
    """文件解析器 - 支持多种JSON格式"""
    
    SYSTEM_SQL_PATTERNS = [
        'pg_database', 'pg_stat', 'pg_extension', 'pg_class',
        'information_schema', 'pg_catalog', 'pg_toast',
        'pg_attribute', 'pg_index', 'pg_namespace'
    ]
    
    def __init__(self):
        self.parsed_data: Optional[ParsedAnomalyData] = None
    
    def parse_file(self, file_path: str) -> ParsedAnomalyData:
        """
        解析上传的JSON文件
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            ParsedAnomalyData: 解析后的异常数据
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        
        try:
            raw_json = json.loads(raw_content)
        except json.JSONDecodeError as e:
            raw_json = self._parse_text_content(raw_content)
        
        self.parsed_data = self._extract_all_data(raw_json, os.path.basename(file_path))
        
        logger.info(f"[FileParser] 文件解析完成: {file_path}")
        logger.info(f"[FileParser] 慢查询数: {len(self.parsed_data.slow_queries)}")
        logger.info(f"[FileParser] 活跃会话数: {len(self.parsed_data.active_sessions)}")
        logger.info(f"[FileParser] 表数量: {len(self.parsed_data.table_sizes)}")
        
        return self.parsed_data
    
    def parse_json_dict(self, json_data: Dict) -> ParsedAnomalyData:
        """
        直接解析JSON字典（用于API调用）
        
        Args:
            json_data: JSON数据字典
            
        Returns:
            ParsedAnomalyData: 解析后的异常数据
        """
        self.parsed_data = self._extract_all_data(json_data, "api_input")
        return self.parsed_data
    
    def _extract_all_data(self, raw_json: Dict, file_name: str) -> ParsedAnomalyData:
        """提取所有数据"""
        data = ParsedAnomalyData()
        data.file_name = file_name
        data.raw_data = raw_json
        
        data.alert_type = self._extract_alert_type(raw_json)
        data.description = self._extract_description(raw_json)
        data.severity = self._extract_severity(raw_json)
        data.timestamp = self._extract_timestamp(raw_json)
        
        data.slow_queries = self._extract_slow_queries(raw_json)
        data.active_sessions = self._extract_active_sessions(raw_json)
        data.table_sizes = self._extract_table_sizes(raw_json)
        
        data.cpu_metrics = self._extract_cpu_metrics(raw_json)
        data.memory_metrics = self._extract_memory_metrics(raw_json)
        data.io_metrics = self._extract_io_metrics(raw_json)
        
        data.execution_plans = self._extract_execution_plans(raw_json)
        data.wait_events = self._extract_wait_events(raw_json)
        data.lock_info = self._extract_lock_info(raw_json)
        
        return data
    
    def _extract_alert_type(self, data: Dict) -> str:
        """提取告警类型"""
        if 'alert_type' in data:
            return data['alert_type']
        
        if 'anomaly_type' in data:
            return data['anomaly_type']
        
        content = json.dumps(data).lower()
        if 'slow query' in content or 'slow_query' in content:
            return "Slow Queries"
        if 'cpu' in content and ('high' in content or 'usage' in content):
            return "CPU High"
        if 'memory' in content and ('high' in content or 'usage' in content):
            return "Memory High"
        if 'io' in content and ('high' in content or 'disk' in content):
            return "IO High"
        if 'lock' in content and ('wait' in content or 'deadlock' in content):
            return "Lock Wait"
        
        return "Database Performance Anomaly"
    
    def _extract_description(self, data: Dict) -> str:
        """提取异常描述"""
        if 'description' in data:
            return data['description']
        if 'anomaly_description' in data:
            return data['anomaly_description']
        if 'message' in data:
            return data['message']
        if 'alert_message' in data:
            return data['alert_message']
        
        slow_queries = self._extract_slow_queries(data)
        if slow_queries:
            return f"检测到 {len(slow_queries)} 条慢查询，需要分析优化"
        
        return "数据库性能异常，需要进一步诊断分析"
    
    def _extract_severity(self, data: Dict) -> str:
        """提取严重程度"""
        if 'severity' in data:
            sev = data['severity'].lower()
            if sev in ['high', 'critical', 'error']:
                return 'high'
            elif sev in ['medium', 'warning', 'warn']:
                return 'medium'
            elif sev in ['low', 'info', 'information']:
                return 'low'
        
        if 'level' in data:
            level = str(data['level']).lower()
            if level in ['high', 'critical', 'error']:
                return 'high'
            elif level in ['medium', 'warning']:
                return 'medium'
        
        return 'medium'
    
    def _extract_timestamp(self, data: Dict) -> str:
        """提取时间戳"""
        for key in ['timestamp', 'time', 'created_at', 'datetime', 'date']:
            if key in data:
                return str(data[key])
        
        return datetime.now().isoformat()
    
    def _extract_slow_queries(self, data: Dict) -> List[Dict]:
        """提取慢查询列表"""
        queries = []
        
        if 'slow_queries' in data:
            raw_queries = data['slow_queries']
            if isinstance(raw_queries, list):
                for q in raw_queries:
                    query = self._normalize_slow_query(q)
                    if query:
                        queries.append(query)
        
        if 'queries' in data and not queries:
            raw_queries = data['queries']
            if isinstance(raw_queries, list):
                for q in raw_queries:
                    query = self._normalize_slow_query(q)
                    if query:
                        queries.append(query)
        
        if 'pg_stat_statements' in data and not queries:
            raw_queries = data['pg_stat_statements']
            if isinstance(raw_queries, list):
                for q in raw_queries:
                    query = self._normalize_pg_stat_statement(q)
                    if query:
                        queries.append(query)
        
        return queries
    
    def _normalize_slow_query(self, q: Any) -> Optional[Dict]:
        """标准化慢查询格式"""
        if isinstance(q, str):
            return {
                'query': q,
                'duration_ms': 0,
                'calls': 1,
                'is_system_sql': self._is_system_sql(q)
            }
        
        if isinstance(q, dict):
            query_text = q.get('query') or q.get('sql') or q.get('query_text') or q.get('statement', '')
            
            duration = q.get('duration') or q.get('duration_ms') or q.get('total_time') or q.get('exec_time', 0)
            if isinstance(duration, str):
                duration = self._parse_duration(duration)
            
            return {
                'query': query_text,
                'duration_ms': float(duration),
                'calls': q.get('calls') or q.get('count', 1),
                'mean_time_ms': q.get('mean_time') or q.get('mean_exec_time', 0),
                'rows': q.get('rows') or q.get('rows_affected', 0),
                'is_system_sql': self._is_system_sql(query_text),
                'database': q.get('database') or q.get('dbid', ''),
                'user': q.get('user') or q.get('userid', '')
            }
        
        return None
    
    def _normalize_pg_stat_statement(self, q: Dict) -> Optional[Dict]:
        """标准化pg_stat_statements格式"""
        query_text = q.get('query') or q.get('statement', '')
        
        return {
            'query': query_text,
            'duration_ms': q.get('total_exec_time') or q.get('total_time', 0),
            'calls': q.get('calls', 1),
            'mean_time_ms': q.get('mean_exec_time') or q.get('mean_time', 0),
            'rows': q.get('rows', 0),
            'is_system_sql': self._is_system_sql(query_text),
            'shared_blks_hit': q.get('shared_blks_hit', 0),
            'shared_blks_read': q.get('shared_blks_read', 0)
        }
    
    def _extract_active_sessions(self, data: Dict) -> List[Dict]:
        """提取活跃会话"""
        sessions = []
        
        for key in ['active_sessions', 'sessions', 'pg_stat_activity', 'connections']:
            if key in data:
                raw_sessions = data[key]
                if isinstance(raw_sessions, list):
                    for s in raw_sessions:
                        session = self._normalize_session(s)
                        if session:
                            sessions.append(session)
                break
        
        return sessions
    
    def _normalize_session(self, s: Any) -> Optional[Dict]:
        """标准化会话格式"""
        if isinstance(s, dict):
            return {
                'pid': s.get('pid') or s.get('process_id', 0),
                'database': s.get('database') or s.get('datname', ''),
                'user': s.get('user') or s.get('usename', ''),
                'state': s.get('state') or s.get('status', 'active'),
                'query': s.get('query') or s.get('current_query', ''),
                'duration': s.get('duration') or s.get('query_duration', 0),
                'wait_event': s.get('wait_event') or s.get('wait_event_type', '')
            }
        
        return None
    
    def _extract_table_sizes(self, data: Dict) -> Dict[str, int]:
        """提取表大小信息"""
        sizes = {}
        
        for key in ['table_sizes', 'tables', 'relation_sizes']:
            if key in data:
                raw_sizes = data[key]
                if isinstance(raw_sizes, dict):
                    for table_name, size in raw_sizes.items():
                        sizes[table_name] = self._parse_size(size)
                elif isinstance(raw_sizes, list):
                    for item in raw_sizes:
                        if isinstance(item, dict):
                            name = item.get('table') or item.get('relation') or item.get('name', '')
                            size = item.get('size') or item.get('table_size', 0)
                            if name:
                                sizes[name] = self._parse_size(size)
                break
        
        return sizes
    
    def _extract_cpu_metrics(self, data: Dict) -> Dict:
        """提取CPU指标"""
        cpu = {}
        
        for key in ['cpu', 'cpu_metrics', 'cpu_usage']:
            if key in data:
                raw = data[key]
                if isinstance(raw, dict):
                    cpu = raw
                elif isinstance(raw, (int, float)):
                    cpu['usage_percent'] = float(raw)
                break
        
        if 'metrics' in data and isinstance(data['metrics'], dict):
            metrics = data['metrics']
            if 'cpu_percent' in metrics:
                cpu['usage_percent'] = metrics['cpu_percent']
            if 'cpu_usage' in metrics:
                cpu['usage_percent'] = metrics['cpu_usage']
        
        return cpu
    
    def _extract_memory_metrics(self, data: Dict) -> Dict:
        """提取内存指标"""
        memory = {}
        
        for key in ['memory', 'memory_metrics', 'memory_usage']:
            if key in data:
                raw = data[key]
                if isinstance(raw, dict):
                    memory = raw
                elif isinstance(raw, (int, float)):
                    memory['usage_percent'] = float(raw)
                break
        
        if 'metrics' in data and isinstance(data['metrics'], dict):
            metrics = data['metrics']
            if 'memory_percent' in metrics:
                memory['usage_percent'] = metrics['memory_percent']
            if 'memory_usage' in metrics:
                memory['usage_percent'] = metrics['memory_usage']
        
        return memory
    
    def _extract_io_metrics(self, data: Dict) -> Dict:
        """提取IO指标"""
        io = {}
        
        for key in ['io', 'io_metrics', 'disk_io', 'disk']:
            if key in data:
                raw = data[key]
                if isinstance(raw, dict):
                    io = raw
                elif isinstance(raw, (int, float)):
                    io['usage_percent'] = float(raw)
                break
        
        if 'metrics' in data and isinstance(data['metrics'], dict):
            metrics = data['metrics']
            if 'disk_io' in metrics:
                io.update(metrics['disk_io'] if isinstance(metrics['disk_io'], dict) else {'usage_percent': metrics['disk_io']})
        
        return io
    
    def _extract_execution_plans(self, data: Dict) -> List[Dict]:
        """提取执行计划"""
        plans = []
        
        for key in ['execution_plans', 'explain_plans', 'plans']:
            if key in data:
                raw_plans = data[key]
                if isinstance(raw_plans, list):
                    plans.extend(raw_plans)
                break
        
        return plans
    
    def _extract_wait_events(self, data: Dict) -> List[Dict]:
        """提取等待事件"""
        events = []
        
        for key in ['wait_events', 'pg_wait_events', 'waits']:
            if key in data:
                raw_events = data[key]
                if isinstance(raw_events, list):
                    events.extend(raw_events)
                break
        
        return events
    
    def _extract_lock_info(self, data: Dict) -> List[Dict]:
        """提取锁信息"""
        locks = []
        
        for key in ['locks', 'pg_locks', 'lock_info']:
            if key in data:
                raw_locks = data[key]
                if isinstance(raw_locks, list):
                    locks.extend(raw_locks)
                break
        
        return locks
    
    def _parse_text_content(self, content: str) -> Dict:
        """解析非JSON文本内容"""
        data = {
            'slow_queries': [],
            'description': content[:500]
        }
        
        slow_query_pattern = r'(?:query|sql|statement):\s*(.+?)(?:\n|$)'
        matches = re.findall(slow_query_pattern, content, re.IGNORECASE)
        for match in matches:
            data['slow_queries'].append({'query': match.strip(), 'duration_ms': 0})
        
        duration_pattern = r'(?:duration|time):\s*([\d.]+)\s*(ms|s|sec)?'
        duration_matches = re.findall(duration_pattern, content, re.IGNORECASE)
        if duration_matches:
            for i, (val, unit) in enumerate(duration_matches):
                if i < len(data['slow_queries']):
                    duration = float(val)
                    if unit and unit.lower() in ['s', 'sec']:
                        duration *= 1000
                    data['slow_queries'][i]['duration_ms'] = duration
        
        return data
    
    def _is_system_sql(self, query: str) -> bool:
        """判断是否为系统SQL"""
        if not query:
            return False
        query_lower = query.lower()
        return any(pattern in query_lower for pattern in self.SYSTEM_SQL_PATTERNS)
    
    def _parse_duration(self, duration_str: str) -> float:
        """解析时长字符串"""
        duration_str = str(duration_str).lower().strip()
        
        match = re.match(r'([\d.]+)\s*(ms|s|sec|m|min)?', duration_str)
        if match:
            value = float(match.group(1))
            unit = match.group(2) or 'ms'
            
            if unit in ['s', 'sec']:
                value *= 1000
            elif unit in ['m', 'min']:
                value *= 60000
            
            return value
        
        try:
            return float(duration_str)
        except ValueError:
            return 0
    
    def _parse_size(self, size: Any) -> int:
        """解析大小值（返回字节数）"""
        if isinstance(size, (int, float)):
            return int(size)
        
        size_str = str(size).upper().strip()
        
        match = re.match(r'([\d.]+)\s*(KB|MB|GB|TB|B)?', size_str)
        if match:
            value = float(match.group(1))
            unit = match.group(2) or 'B'
            
            multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
            return int(value * multipliers.get(unit, 1))
        
        try:
            return int(size)
        except ValueError:
            return 0
    
    def get_diagnosis_metrics(self) -> Dict:
        """
        获取诊断所需的指标数据（替代数据库直连）
        
        Returns:
            Dict: 包含所有诊断所需指标的字典
        """
        if not self.parsed_data:
            return {}
        
        data = self.parsed_data
        
        business_slow_queries = [q for q in data.slow_queries if not q.get('is_system_sql')]
        system_slow_queries = [q for q in data.slow_queries if q.get('is_system_sql')]
        
        total_query_duration = sum(q.get('duration_ms', 0) for q in data.slow_queries)
        avg_query_duration = total_query_duration / len(data.slow_queries) if data.slow_queries else 0
        
        max_table_size = max(data.table_sizes.values()) if data.table_sizes else 0
        total_table_size = sum(data.table_sizes.values())
        
        return {
            'slow_queries': {
                'total': len(data.slow_queries),
                'business_count': len(business_slow_queries),
                'system_count': len(system_slow_queries),
                'total_duration_ms': total_query_duration,
                'avg_duration_ms': avg_query_duration,
                'top_queries': sorted(data.slow_queries, key=lambda x: x.get('duration_ms', 0), reverse=True)[:10],
                'business_queries': business_slow_queries[:10],
                'system_queries': system_slow_queries[:10]
            },
            'sessions': {
                'active_count': len(data.active_sessions),
                'sessions': data.active_sessions[:20]
            },
            'tables': {
                'count': len(data.table_sizes),
                'max_size_bytes': max_table_size,
                'total_size_bytes': total_table_size,
                'sizes': data.table_sizes
            },
            'system_metrics': {
                'cpu': data.cpu_metrics,
                'memory': data.memory_metrics,
                'io': data.io_metrics
            },
            'execution_plans': data.execution_plans,
            'wait_events': data.wait_events,
            'lock_info': data.lock_info,
            'anomaly_info': {
                'alert_type': data.alert_type,
                'description': data.description,
                'severity': data.severity,
                'timestamp': data.timestamp,
                'source': data.source,
                'file_name': data.file_name
            }
        }
    
    def has_business_data(self) -> bool:
        """判断是否有业务数据（用于替代环境匹配判断）"""
        if not self.parsed_data:
            return False
        
        business_queries = [q for q in self.parsed_data.slow_queries if not q.get('is_system_sql')]
        if business_queries:
            return True
        
        if self.parsed_data.active_sessions:
            return True
        
        max_table_size = max(self.parsed_data.table_sizes.values()) if self.parsed_data.table_sizes else 0
        if max_table_size > 10 * 1024 * 1024:
            return True
        
        return False


_file_parser_instance: Optional[FileParser] = None

def get_file_parser() -> FileParser:
    """获取文件解析器单例"""
    global _file_parser_instance
    if _file_parser_instance is None:
        _file_parser_instance = FileParser()
    return _file_parser_instance

def parse_diagnosis_file(file_path: str) -> ParsedAnomalyData:
    """解析诊断文件的便捷函数"""
    return get_file_parser().parse_file(file_path)

def parse_diagnosis_json(json_data: Dict) -> ParsedAnomalyData:
    """解析JSON数据的便捷函数"""
    return get_file_parser().parse_json_dict(json_data)

def get_metrics_from_file(file_path: str) -> Dict:
    """从文件获取诊断指标的便捷函数"""
    parser = get_file_parser()
    parser.parse_file(file_path)
    return parser.get_diagnosis_metrics()
