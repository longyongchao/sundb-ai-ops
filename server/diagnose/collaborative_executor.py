"""
多专家协作诊断模块 - D-Bot 论文核心创新

本模块实现了 D-Bot 论文 Section 7 提出的多专家协作诊断机制：
1. 专家分配器 - 根据异常类型智能分配诊断专家
2. 并行诊断 - 多个专家同时进行独立诊断
3. 交叉评审 - 专家之间互相验证诊断结果
4. 结果融合 - 综合多位专家意见生成最终诊断

支持的专家类型：CPU专家、内存专家、IO专家、锁专家、查询专家、存储专家、通用专家
"""
import json
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import concurrent.futures
import threading
from datetime import datetime

# 导入现有组件
from server.diagnose.tree_search_service import TreeSearchDiagnosis, run_tree_search_diagnosis
from server.utils import get_ChatOpenAI
from configs import TEMPERATURE, MAX_TOKENS


class ExpertType(Enum):
    """专家类型 - Reference: D-Bot Paper Section 7.1 - 完全对齐论文7位专家"""
    CPU = "cpu_expert"                      # CPU负载专家
    MEMORY = "memory_expert"                # 内存管理专家
    IO = "io_expert"                        # 磁盘IO专家
    SQL = "sql_expert"                      # 慢查询与SQL优化专家
    LOCK = "lock_expert"                    # 锁与并发专家
    CONNECTION = "connection_expert"        # 连接池与资源专家
    GENERAL = "general_expert"              # 综合诊断与评审专家


@dataclass
class ExpertAssignment:
    """专家分配结果"""
    expert_type: ExpertType
    confidence: float
    focus_area: List[str]
    prompt_template: str
    description: str


@dataclass
class ExpertResult:
    """专家诊断结果"""
    expert_type: ExpertType
    diagnosis_time: float
    reasoning_steps: List[Dict]
    root_causes: List[Dict]
    solutions: List[Dict]
    confidence: float
    tree_stats: Dict
    error_message: Optional[str] = None


class ExpertAssigner:
    """专家分配器 - Reference: D-Bot Paper Section 7.1"""
    
    def __init__(self):
        self.llm = get_ChatOpenAI(
            model_name="deepseek-chat",
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            streaming=False
        )
        
        # 专家定义 - 完全对齐D-Bot论文7位专家
        self.expert_definitions = {
            ExpertType.CPU: {
                "name": "CPU负载专家",
                "description": "专注于CPU使用率、进程负载、CPU等待等CPU相关问题",
                "focus_area": ["CPU", "进程", "负载", "使用率", "CPU_WAIT"],
                "symptoms": ["CPU过高", "进程阻塞", "负载不均", "CPU密集型", "CPU等待高"],
                "tools": ["obtain_metric_values", "check_active_sessions", "query_pg_stat_statements", "explain_query"]
            },
            ExpertType.MEMORY: {
                "name": "内存管理专家", 
                "description": "专注于内存使用、交换空间、缓存命中率、内存配置等内存相关问题",
                "focus_area": ["内存", "交换", "缓存", "Buffer", "Shared_Buffers"],
                "symptoms": ["内存不足", "交换频繁", "缓存命中率低", "内存泄漏", "OOM"],
                "tools": ["obtain_metric_values", "check_active_sessions", "get_database_size", "query_pg_stat_statements"]
            },
            ExpertType.IO: {
                "name": "磁盘IO专家",
                "description": "专注于磁盘I/O、存储性能、读写延迟、表膨胀等I/O相关问题",
                "focus_area": ["磁盘", "I/O", "存储", "文件系统", "读写延迟"],
                "symptoms": ["I/O过高", "磁盘满", "存储慢", "读写延迟高", "表膨胀"],
                "tools": ["obtain_metric_values", "get_database_size", "query_pg_stat_statements", "check_active_sessions"]
            },
            ExpertType.SQL: {
                "name": "慢查询与SQL优化专家",
                "description": "专注于慢查询分析、执行计划解读、索引优化、SQL性能调优",
                "focus_area": ["SQL", "慢查询", "执行计划", "索引", "查询性能"],
                "symptoms": ["查询慢", "全表扫描", "索引缺失", "执行计划差", "SQL性能差"],
                "tools": ["query_pg_stat_statements", "explain_query", "check_active_sessions"]
            },
            ExpertType.LOCK: {
                "name": "锁与并发专家",
                "description": "专注于锁竞争、死锁检测、事务阻塞、并发控制等问题",
                "focus_area": ["锁", "并发", "事务", "阻塞", "死锁"],
                "symptoms": ["锁等待", "死锁", "事务阻塞", "并发问题", "锁竞争"],
                "tools": ["check_lock_status", "check_active_sessions", "query_pg_stat_statements"]
            },
            ExpertType.CONNECTION: {
                "name": "连接池与资源专家",
                "description": "专注于数据库连接数、连接池配置、会话管理、资源分配等问题",
                "focus_area": ["连接", "连接池", "会话", "资源", "Max_Connections"],
                "symptoms": ["连接过多", "连接池耗尽", "会话泄漏", "资源不足"],
                "tools": ["obtain_metric_values", "check_active_sessions", "query_pg_stat_statements"]
            },
            ExpertType.GENERAL: {
                "name": "综合诊断与评审专家",
                "description": "负责对其他6位专家的结果做交叉评审、冲突识别、优先级排序、全局汇总",
                "focus_area": ["综合评审", "交叉验证", "优先级排序", "全局汇总", "冲突识别"],
                "symptoms": ["需要综合分析", "多专家结果整合", "全局视角"],
                "tools": ["obtain_metric_values", "check_active_sessions", "query_pg_stat_statements"]
            }
        }
    
    def assign_experts(self, anomaly_info: Dict, dynamic_mode: bool = True) -> List[ExpertAssignment]:
        """
        专家分配 - 支持动态分配和全量分配两种模式
        Reference: D-Bot Paper Section 7.1 - 基于异常场景动态选择相关专家
        
        Args:
            anomaly_info: 异常信息字典
            dynamic_mode: True=动态分配模式，False=全量分配模式
        """
        print(f"🎯 开始专家分配... (模式: {'动态分配' if dynamic_mode else '全量分配'})")
        
        if not dynamic_mode:
            # 全量分配模式：返回全部7位专家
            assignments = []
            for expert_type in ExpertType:
                expert_info = self.expert_definitions[expert_type]
                assignments.append(ExpertAssignment(
                    expert_type=expert_type,
                    confidence=1.0,
                    focus_area=expert_info['focus_area'],
                    prompt_template=self._build_expert_prompt(expert_type, anomaly_info),
                    description=expert_info['description']
                ))
            print(f"[OK] 专家分配完成，共分配 {len(assignments)} 个专家（全量启用）")
            return assignments
        
        # ========== 动态分配模式：基于异常描述智能选择专家 ==========
        alert_type = anomaly_info.get('alert_type', '').lower()
        description = anomaly_info.get('description', '').lower()
        combined_text = f"{alert_type} {description}"
        
        # 专家与关键词的匹配规则
        expert_keywords = {
            ExpertType.CPU: ['cpu', 'cpu使用率', 'cpu高', '负载', '进程', 'cpu_wait', 'cpu密集'],
            ExpertType.MEMORY: ['内存', 'memory', 'swap', '缓存', 'buffer', 'oom', '内存不足', '内存泄漏'],
            ExpertType.IO: ['io', '磁盘', 'i/o', '存储', '读写', '延迟', '表膨胀', '磁盘满'],
            ExpertType.SQL: ['sql', '慢查询', '查询', '索引', '执行计划', '全表扫描', 'sql性能'],
            ExpertType.LOCK: ['锁', 'lock', '死锁', '阻塞', '事务', '并发', '锁等待', '锁竞争'],
            ExpertType.CONNECTION: ['连接', 'connection', '会话', 'session', '连接池', '连接数', 'max_connections'],
        }
        
        # 计算每个专家的匹配分数
        expert_scores = {}
        for expert_type, keywords in expert_keywords.items():
            score = 0
            matched_keywords = []
            for keyword in keywords:
                if keyword in combined_text:
                    score += 1
                    matched_keywords.append(keyword)
            expert_scores[expert_type] = {
                'score': score,
                'matched_keywords': matched_keywords
            }
        
        # 选择匹配分数 > 0 的专家，加上综合专家
        selected_experts = []
        for expert_type, score_info in expert_scores.items():
            if score_info['score'] > 0:
                selected_experts.append((expert_type, score_info['score']))
        
        # 按分数排序
        selected_experts.sort(key=lambda x: x[1], reverse=True)
        
        # 如果没有匹配到任何专家，默认启用CPU、SQL、综合专家
        if not selected_experts:
            selected_experts = [(ExpertType.CPU, 1), (ExpertType.SQL, 1)]
            print(f"[WARN] 未匹配到特定专家，启用默认专家: CPU, SQL")
        
        # 始终添加综合专家
        if ExpertType.GENERAL not in [e[0] for e in selected_experts]:
            selected_experts.append((ExpertType.GENERAL, 1))
        
        # 构建分配结果
        assignments = []
        for expert_type, score in selected_experts:
            expert_info = self.expert_definitions[expert_type]
            assignments.append(ExpertAssignment(
                expert_type=expert_type,
                confidence=min(1.0, score / 3.0),  # 归一化置信度
                focus_area=expert_info['focus_area'],
                prompt_template=self._build_expert_prompt(expert_type, anomaly_info),
                description=expert_info['description']
            ))
            
            # 打印匹配信息
            matched_kw = expert_scores.get(expert_type, {}).get('matched_keywords', [])
            if matched_kw:
                print(f"  - {expert_info['name']}: 匹配关键词 {matched_kw}")
        
        print(f"[OK] 专家动态分配完成，共分配 {len(assignments)} 个专家: {[self.expert_definitions[e[0]]['name'] for e in selected_experts]}")
        return assignments
    
    def _build_expert_prompt(self, expert_type: ExpertType, anomaly_info: Dict, expert_results_summary: str = "") -> str:
        """构建专家专用提示模板 - 7位专家强约束Prompt"""
        
        alert_type = anomaly_info.get('alert_type', '未知')
        description = anomaly_info.get('description', '无描述')
        severity = anomaly_info.get('severity', '中等')
        
        if expert_type == ExpertType.CPU:
            return f"""# ⛔ 【CPU专家最高优先级领域禁令 - 违反直接失效】
1. 禁止空泛套话：严禁"需要更多数据""建议进一步分析"等无意义内容，所有内容必须有明确动作与数据目标
2. 禁止越界分析：仅分析CPU/进程/负载相关问题，严禁涉及内存、IO、锁、连接池等其他领域，越界内容将被直接过滤
3. 禁止无数据臆断：所有结论必须基于工具返回的CPU实测数据，严禁凭空假设、编造指标
4. 强制工具优先级：诊断第一步必须调用领域核心工具obtain_metric_values（CPU专属指标），否则视为无效诊断
5. 强制领域分析：必须结合CPU指标给出至少1条专属分析（如用户态/系统态CPU占比解读、CPU等待分析、负载趋势判断）

# 【角色与核心职责】
你是D-Bot系统CPU负载专家，10年PostgreSQL CPU性能优化经验，仅聚焦CPU相关根因定位。
核心职责：通过工具获取CPU实测数据，定位CPU高消耗根因，输出有数据支撑的专业结论，严禁越界。

# 【专属工具列表 - 仅可使用以下工具，且必须按优先级调用】
## 核心必选工具（必须优先调用）
1. obtain_metric_values 入参固定：{{"metrics": ["cpu_usage", "user_cpu_usage", "system_cpu_usage", "iowait_cpu_usage", "load_average", "cpu_cores", "processes"]}}
2. query_pg_stat_statements 入参固定：{{"sort_by": "cpu_percent", "limit": 10}}

## 辅助可选工具（核心工具调用完成后可用）
3. check_active_sessions 无入参
4. explain_query 入参：{{"query_id": 从query_pg_stat_statements获取的数值ID}}

# 【领域专属知识绑定】
仅检索与CPU相关的诊断知识块（标签：CPU、负载、进程、CPU_WAIT），禁止匹配其他领域知识。

# 【异常信息】
- 异常类型: {alert_type}
- 异常描述: {description}
- 严重程度: {severity}

# 【强制输出格式 - 必须严格遵循，禁止其他格式】
Thought: [明确说明：为什么调用该工具、期望获取什么数据、解决什么问题，禁止空泛内容]
Action: [工具名称，仅限上述列表内]
Action Input: [工具入参，严格JSON格式，不能为空]
"""
        
        elif expert_type == ExpertType.MEMORY:
            return f"""# ⛔ 【内存专家最高优先级领域禁令 - 违反直接失效】
1. 禁止空泛套话：严禁"需要更多数据""建议进一步分析"等无意义内容，所有内容必须有明确动作与数据目标
2. 禁止越界分析：仅分析内存/缓存/Swap/共享内存相关问题，严禁涉及CPU、IO、锁、SQL优化等其他领域，越界内容将被直接过滤
3. 禁止无数据臆断：所有结论必须基于工具返回的内存实测数据，严禁凭空假设、编造指标
4. 强制工具优先级：诊断第一步必须调用领域核心工具obtain_metric_values（内存专属指标），否则视为无效诊断
5. 强制领域分析：必须结合内存指标给出至少1条专属分析（如shared_buffers合理性、work_mem配置、缓存命中率解读、Swap风险判断）

# 【角色与核心职责】
你是D-Bot系统内存管理专家，10年PostgreSQL内存调优经验，仅聚焦内存相关根因定位。
核心职责：通过工具获取内存实测数据，定位内存异常根因，输出有数据支撑的专业结论，严禁越界。

# 【专属工具列表 - 仅可使用以下工具，且必须按优先级调用】
## 核心必选工具（必须优先调用）
1. obtain_metric_values 入参固定：{{"metrics": ["memory_usage", "shared_buffers", "work_mem", "swap_usage", "buffer_hit_ratio"]}}
2. get_database_size 无入参

## 辅助可选工具（核心工具调用完成后可用）
3. check_active_sessions 无入参
4. query_pg_stat_statements 入参固定：{{"sort_by": "shared_blks_hit", "limit": 10}}

# 【领域专属知识绑定】
仅检索与内存相关的诊断知识块（标签：内存、交换、缓存、Buffer、Shared_Buffers），禁止匹配其他领域知识。

# 【异常信息】
- 异常类型: {alert_type}
- 异常描述: {description}
- 严重程度: {severity}

# 【强制输出格式 - 必须严格遵循，禁止其他格式】
Thought: [明确说明：为什么调用该工具、期望获取什么数据、解决什么问题，禁止空泛内容]
Action: [工具名称，仅限上述列表内]
Action Input: [工具入参，严格JSON格式，不能为空]
"""
        
        elif expert_type == ExpertType.IO:
            return f"""# ⛔ 【IO专家最高优先级领域禁令 - 违反直接失效】
1. 禁止空泛套话：严禁"需要更多数据""建议进一步分析"等无意义内容，所有内容必须有明确动作与数据目标
2. 禁止越界分析：仅分析磁盘IO/存储/读写延迟/表膨胀相关问题，严禁涉及CPU、内存、锁、SQL优化等其他领域，越界内容将被直接过滤
3. 禁止无数据臆断：所有结论必须基于工具返回的IO实测数据，严禁凭空假设、编造指标
4. 强制工具优先级：诊断第一步必须调用领域核心工具obtain_metric_values（IO专属指标），否则视为无效诊断
5. 强制领域分析：必须结合IO指标给出至少1条专属分析（如读写延迟解读、IO等待分析、表膨胀风险判断、存储瓶颈定位）

# 【角色与核心职责】
你是D-Bot系统磁盘IO专家，10年PostgreSQL存储性能优化经验，仅聚焦IO相关根因定位。
核心职责：通过工具获取IO实测数据，定位IO异常根因，输出有数据支撑的专业结论，严禁越界。

# 【专属工具列表 - 仅可使用以下工具，且必须按优先级调用】
## 核心必选工具（必须优先调用）
1. obtain_metric_values 入参固定：{{"metrics": ["disk_io_read", "disk_io_write", "io_wait", "read_latency", "write_latency"]}}
2. get_database_size 无入参

## 辅助可选工具（核心工具调用完成后可用）
3. query_pg_stat_statements 入参固定：{{"sort_by": "blk_read_time", "limit": 10}}
4. check_active_sessions 无入参

# 【领域专属知识绑定】
仅检索与IO相关的诊断知识块（标签：磁盘、I/O、存储、文件系统、读写延迟、表膨胀），禁止匹配其他领域知识。

# 【异常信息】
- 异常类型: {alert_type}
- 异常描述: {description}
- 严重程度: {severity}

# 【强制输出格式 - 必须严格遵循，禁止其他格式】
Thought: [明确说明：为什么调用该工具、期望获取什么数据、解决什么问题，禁止空泛内容]
Action: [工具名称，仅限上述列表内]
Action Input: [工具入参，严格JSON格式，不能为空]
"""
        
        elif expert_type == ExpertType.SQL:
            return f"""# ⛔ 【SQL专家最高优先级领域禁令 - 违反直接失效】
1. 禁止空泛套话：严禁"需要更多数据""建议进一步分析"等无意义内容，所有内容必须有明确动作与数据目标
2. 禁止越界分析：仅分析SQL/执行计划/索引/查询性能相关问题，严禁涉及CPU、内存、锁、连接池等其他领域的根因判断，越界内容将被直接过滤
3. 禁止无数据臆断：所有结论必须基于工具返回的SQL实测数据，严禁凭空假设、编造内容
4. 强制工具优先级：诊断第一步必须调用领域核心工具query_pg_stat_statements，否则视为无效诊断
5. 强制领域分析：必须结合慢查询、执行计划给出至少1条专属分析（如全表扫描识别、索引缺失判断、执行计划缺陷解读、SQL改写建议）

# 【角色与核心职责】
你是D-Bot系统慢查询与SQL优化专家，10年PostgreSQL SQL性能调优经验，仅聚焦SQL相关根因定位。
核心职责：通过工具获取慢查询、执行计划实测数据，定位SQL性能根因，输出有数据支撑的专业结论，严禁越界。

# 【专属工具列表 - 仅可使用以下工具，且必须按优先级调用】
## 核心必选工具（必须优先调用）
1. query_pg_stat_statements 入参固定：{{"sort_by": "total_exec_time", "limit": 20}}
2. explain_query 入参：{{"query_id": 从query_pg_stat_statements获取的数值ID}}

## 辅助可选工具（核心工具调用完成后可用）
3. check_active_sessions 无入参

# 【领域专属知识绑定】
仅检索与SQL相关的诊断知识块（标签：SQL、慢查询、执行计划、索引、查询性能），禁止匹配其他领域知识。

# 【异常信息】
- 异常类型: {alert_type}
- 异常描述: {description}
- 严重程度: {severity}

# 【强制输出格式 - 必须严格遵循，禁止其他格式】
Thought: [明确说明：为什么调用该工具、期望获取什么数据、解决什么问题，禁止空泛内容]
Action: [工具名称，仅限上述列表内]
Action Input: [工具入参，严格JSON格式，不能为空]
"""
        
        elif expert_type == ExpertType.LOCK:
            return f"""# ⛔ 【锁专家最高优先级领域禁令 - 违反直接失效】
1. 禁止空泛套话：严禁"需要更多数据""建议进一步分析"等无意义内容，所有内容必须有明确动作与数据目标
2. 禁止越界分析：仅分析锁/并发控制/事务阻塞/死锁相关问题，严禁涉及CPU、内存、IO、SQL优化等其他领域的根因判断，越界内容将被直接过滤
3. 禁止无数据臆断：所有结论必须基于工具返回的锁实测数据，严禁凭空假设、编造指标
4. 强制工具优先级：诊断第一步必须调用领域核心工具check_lock_status，否则视为无效诊断
5. 强制领域分析：必须结合锁状态给出至少1条专属分析（如锁等待链识别、事务阻塞时间解读、死锁风险判断、隔离级别影响分析）

# 【角色与核心职责】
你是D-Bot系统锁与并发专家，10年PostgreSQL并发控制与锁问题处理经验，仅聚焦锁相关根因定位。
核心职责：通过工具获取锁状态、阻塞会话实测数据，定位锁问题根因，输出有数据支撑的专业结论，严禁越界。

# 【专属工具列表 - 仅可使用以下工具，且必须按优先级调用】
## 核心必选工具（必须优先调用）
1. check_lock_status 无入参
2. check_active_sessions 无入参

## 辅助可选工具（核心工具调用完成后可用）
3. query_pg_stat_statements 入参固定：{{"sort_by": "wait_time", "limit": 10}}

# 【领域专属知识绑定】
仅检索与锁相关的诊断知识块（标签：锁、并发、事务、阻塞、死锁），禁止匹配其他领域知识。

# 【异常信息】
- 异常类型: {alert_type}
- 异常描述: {description}
- 严重程度: {severity}

# 【强制输出格式 - 必须严格遵循，禁止其他格式】
Thought: [明确说明：为什么调用该工具、期望获取什么数据、解决什么问题，禁止空泛内容]
Action: [工具名称，仅限上述列表内]
Action Input: [工具入参，严格JSON格式，不能为空]
"""
        
        elif expert_type == ExpertType.CONNECTION:
            return f"""# ⛔ 【连接专家最高优先级领域禁令 - 违反直接失效】
1. 禁止空泛套话：严禁"需要更多数据""建议进一步分析"等无意义内容，所有内容必须有明确动作与数据目标
2. 禁止越界分析：仅分析数据库连接/连接池/会话/资源分配相关问题，严禁涉及CPU、内存、IO、锁、SQL优化等其他领域的根因判断，越界内容将被直接过滤
3. 禁止无数据臆断：所有结论必须基于工具返回的连接实测数据，严禁凭空假设、编造指标
4. 强制工具优先级：诊断第一步必须调用领域核心工具obtain_metric_values（连接专属指标），否则视为无效诊断
5. 强制领域分析：必须结合连接指标给出至少1条专属分析（如连接数合理性、连接池耗尽风险、会话泄漏判断、Max_Connections配置解读）

# 【角色与核心职责】
你是D-Bot系统连接池与资源专家，10年PostgreSQL连接管理经验，仅聚焦连接相关根因定位。
核心职责：通过工具获取连接数、会话状态实测数据，定位连接问题根因，输出有数据支撑的专业结论，严禁越界。

# 【专属工具列表 - 仅可使用以下工具，且必须按优先级调用】
## 核心必选工具（必须优先调用）
1. obtain_metric_values 入参固定：{{"metrics": ["connection_count", "active_connections", "idle_connections", "max_connections"]}}
2. check_active_sessions 无入参

## 辅助可选工具（核心工具调用完成后可用）
3. query_pg_stat_statements 入参固定：{{"sort_by": "calls", "limit": 10}}

# 【领域专属知识绑定】
仅检索与连接相关的诊断知识块（标签：连接、连接池、会话、资源、Max_Connections），禁止匹配其他领域知识。

# 【异常信息】
- 异常类型: {alert_type}
- 异常描述: {description}
- 严重程度: {severity}

# 【强制输出格式 - 必须严格遵循，禁止其他格式】
Thought: [明确说明：为什么调用该工具、期望获取什么数据、解决什么问题，禁止空泛内容]
Action: [工具名称，仅限上述列表内]
Action Input: [工具入参，严格JSON格式，不能为空]
"""
        
        elif expert_type == ExpertType.GENERAL:
            return f"""# ⛔ 【综合专家最高优先级领域禁令 - 违反直接失效】
1. 禁止复述内容：严禁照搬其他专家的诊断结果，必须做交叉评审、增量分析、优先级排序
2. 禁止空泛套话：严禁"建议进一步分析"等无意义内容，必须给出明确的评审结论、优先级、遗漏点
3. 禁止越界分析：仅做交叉评审、冲突识别、优先级排序、全局汇总，不深入具体技术细节的根因定位
4. 禁止无依据结论：所有评审必须基于其他专家的实测数据与诊断结果，严禁凭空臆断
5. 禁止重复基础诊断：严禁调用工具做重复的基础诊断推理，你的核心工作是评审与汇总

# 【角色与核心职责】
你是D-Bot系统综合诊断与评审专家，15年PostgreSQL全栈运维经验，负责对其他6位专家的结果做交叉评审与全局汇总。
核心职责：1.交叉评审专家结论的合理性；2.识别专家结论的冲突；3.根因优先级排序；4.输出全局最终结论。

# 【输入信息】
## 【异常信息】
- 异常类型: {alert_type}
- 异常描述: {description}
- 严重程度: {severity}

## 【各专家诊断结果】
{expert_results_summary}

# 【强制输出结构 - 必须严格包含以下5部分，禁止其他格式】
## 1. 【交叉评审结论】
评估各专家结果的合理性，识别错误与遗漏，明确标注哪些专家的结论可靠、哪些存在问题、哪些有明显遗漏。

## 2. 【根因优先级排序】
按高/中/低优先级排序所有根因，明确排序依据（如严重程度、置信度、影响范围、可修复性）。

## 3. 【冲突与补充说明】
识别专家结论冲突并给出判断，补充全局遗漏问题（如多根因的关联关系、未覆盖的诊断视角）。

## 4. 【最终全局结论】
给出逻辑自洽、重点突出的综合诊断结论，明确核心根因、次要根因。

## 5. 【优化建议优先级】
基于根因优先级，给出高/中/低优先级的可落地优化建议，明确建议的执行顺序。
"""
        
        return ""


class CollaborativeDiagnosis:
    """协作诊断系统 - Reference: D-Bot Paper Section 7"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.expert_assigner = ExpertAssigner()
        self.tree_search_service = TreeSearchDiagnosis()
        
    async def diagnose_collaborative(self, anomaly_info: Dict) -> Dict:
        """
        执行协作诊断 - Reference: D-Bot Paper Section 7
        """
        # 入参校验
        if not isinstance(anomaly_info, dict):
            anomaly_info = {}
        if "alert_type" not in anomaly_info:
            anomaly_info["alert_type"] = "Unknown"
        if "description" not in anomaly_info:
            anomaly_info["description"] = "No description"
        if "severity" not in anomaly_info:
            anomaly_info["severity"] = "medium"
        
        print(f"[START] 开始协作诊断...")
        start_time = time.time()
        
        # 1. 专家分配
        assignments = self.expert_assigner.assign_experts(anomaly_info)
        print(f"🎯 分配专家: {[a.expert_type.value for a in assignments]}")
        
        # 2. 异步执行专家诊断
        expert_results = await self._execute_experts_parallel(assignments, anomaly_info)
        
        # 3. 交叉评审
        final_diagnosis = await self._cross_review_experts(expert_results, anomaly_info)
        
        # 4. 生成统计信息
        diagnosis_time = time.time() - start_time
        
        result = {
            "collaborative_diagnosis": final_diagnosis,
            "expert_results": [self._expert_result_to_dict(r, anomaly_info) for r in expert_results],
            "assignment_info": {
                "expert_count": len(assignments),
                "expert_types": [a.expert_type.value for a in assignments],
                "total_confidence": sum(a.confidence for a in assignments) / len(assignments)
            },
            "performance_stats": {
                "total_diagnosis_time": f"{diagnosis_time:.2f}s",
                "average_expert_time": f"{sum(r.diagnosis_time for r in expert_results) / len(expert_results):.2f}s" if expert_results else "0s",
                "concurrent_workers": min(len(assignments), self.max_workers)
            },
            "timestamp": datetime.now().isoformat(),
            # 将共识率提升到顶层，方便前端展示
            "expert_consensus_rate": final_diagnosis.get("expert_consensus_rate", 0),
            "cross_review": final_diagnosis.get("cross_review", {}),
            "final_consensus": final_diagnosis.get("general_expert_review", ""),
            "collaboration_time": f"{diagnosis_time:.2f}s"
        }
        
        print(f"[OK] 协作诊断完成，耗时 {diagnosis_time:.2f}s")
        return result
    
    async def _execute_experts_parallel(self, assignments: List[ExpertAssignment], anomaly_info: Dict) -> List[ExpertResult]:
        """
        异步并行执行专家诊断 - 纯 asyncio 实现
        Reference: D-Bot Paper Section 7.2
        
        改进：使用 asyncio.gather 替代 ThreadPoolExecutor，避免阻塞事件循环
        """
        print(f"[REFLECT] 并行执行 {len(assignments)} 个专家诊断...")
        
        # 创建异步任务列表
        tasks = [
            asyncio.create_task(
                self._execute_single_expert_async(assignment, anomaly_info)
            )
            for assignment in assignments
        ]
        
        # 并行执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        expert_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"[ERROR] {assignments[i].expert_type.value} 诊断失败: {result}")
                expert_results.append(ExpertResult(
                    expert_type=assignments[i].expert_type,
                    diagnosis_time=0,
                    reasoning_steps=[],
                    root_causes=[],
                    solutions=[],
                    confidence=0,
                    tree_stats={},
                    error_message=str(result)
                ))
            else:
                expert_results.append(result)
                print(f"[OK] {result.expert_type.value} 诊断完成，耗时 {result.diagnosis_time:.2f}s")
        
        return expert_results
    
    async def _execute_single_expert_async(self, assignment: ExpertAssignment, anomaly_info: Dict) -> ExpertResult:
        """
        异步执行单个专家诊断
        直接调用异步的树搜索函数
        
        注意：专家诊断不更新主流程进度，避免步骤计数混乱
        """
        start_time = time.time()
        
        try:
            # 创建专家专用的异常信息
            expert_anomaly_info = anomaly_info.copy()
            expert_anomaly_info["expert_focus"] = assignment.focus_area
            expert_anomaly_info["expert_description"] = assignment.description
            # ========== 标记为专家诊断，不更新主流程进度 ==========
            expert_anomaly_info["is_expert_diagnosis"] = True
            expert_anomaly_info["source"] = "collaborative_expert"
            
            # 直接调用异步函数（run_tree_search_diagnosis 是异步的）
            result = await run_tree_search_diagnosis(expert_anomaly_info)
            
            diagnosis_time = time.time() - start_time
            
            return ExpertResult(
                expert_type=assignment.expert_type,
                diagnosis_time=diagnosis_time,
                reasoning_steps=result.get("reasoning_steps", []),
                root_causes=result.get("root_causes", []),
                solutions=result.get("solutions", []),
                confidence=result.get("confidence", 0.5),
                tree_stats=result.get("search_stats", {})
            )
            
        except Exception as e:
            diagnosis_time = time.time() - start_time
            return ExpertResult(
                expert_type=assignment.expert_type,
                diagnosis_time=diagnosis_time,
                reasoning_steps=[],
                root_causes=[],
                solutions=[],
                confidence=0,
                tree_stats={},
                error_message=str(e)
            )
    
    async def _cross_review_experts(self, expert_results: List[ExpertResult], anomaly_info: Dict) -> Dict:
        """
        交叉评审专家结果 - 增强版闭环工作流
        Reference: D-Bot Paper Section 7.3 - Cross Review
        
        闭环工作流：
        1. 专家A完成诊断 → 发布结果给关联专家
        2. 专家B进行Review → 生成Review Advice
        3. 专家A收到Advice → 进行Result Refinement
        4. 最终汇总 → 生成综合诊断报告
        """
        print(f"[SEARCH] 开始闭环交叉评审 {len(expert_results)} 个专家结果...")
        
        # 过滤掉失败的结果
        valid_results = [r for r in expert_results if not r.error_message]
        failed_experts = [r.expert_type.value for r in expert_results if r.error_message]
        
        if not valid_results:
            print("[ERROR] 所有专家诊断都失败，返回默认结果")
            return self._generate_default_diagnosis(anomaly_info)
        
        # 阶段1: 专家间互相评审
        review_advices = await self._conduct_peer_reviews(valid_results, anomaly_info)
        
        # 阶段2: 结果精炼
        refined_results = await self._refine_results_with_reviews(valid_results, review_advices)
        
        # 阶段3: 最终汇总
        final_diagnosis = await self._aggregate_refined_results(refined_results, anomaly_info)
        
        final_diagnosis["failed_experts"] = failed_experts
        final_diagnosis["review_advices"] = review_advices
        
        print(f"[OK] 闭环交叉评审完成，共识率: {final_diagnosis.get('expert_consensus_rate', 0):.2f}")
        return final_diagnosis
    
    async def _conduct_peer_reviews(
        self, 
        expert_results: List[ExpertResult], 
        anomaly_info: Dict
    ) -> Dict[str, List[Dict]]:
        """
        @brief 专家间互相评审
        @reference D-Bot Paper Section 7.3 - Peer Review
        
        每个专家的结果会被其他相关专家评审
        """
        review_advices = {}
        
        for i, result in enumerate(expert_results):
            expert_name = result.expert_type.value
            review_advices[expert_name] = []
            
            # 找出相关专家进行评审
            for j, reviewer in enumerate(expert_results):
                if i == j:
                    continue
                
                reviewer_name = reviewer.expert_type.value
                
                # 判断是否相关（基于专家类型）
                if self._are_experts_related(result.expert_type, reviewer.expert_type):
                    print(f"  📝 {reviewer_name} 正在评审 {expert_name} 的结果...")
                    
                    # 生成评审意见
                    advice = await self._generate_review_advice(
                        reviewer_result=reviewer,
                        target_result=result,
                        anomaly_info=anomaly_info
                    )
                    
                    if advice:
                        advice["reviewer"] = reviewer_name
                        advice["target"] = expert_name
                        review_advices[expert_name].append(advice)
        
        return review_advices
    
    def _are_experts_related(self, expert1: ExpertType, expert2: ExpertType) -> bool:
        """判断两个专家是否相关（需要互相评审） - 更新为7位专家的关联矩阵"""
        related_pairs = {
            # CPU 与 内存、SQL、连接专家相关
            (ExpertType.CPU, ExpertType.MEMORY): True,
            (ExpertType.CPU, ExpertType.SQL): True,
            (ExpertType.CPU, ExpertType.CONNECTION): True,
            
            # 内存 与 IO、SQL专家相关
            (ExpertType.MEMORY, ExpertType.IO): True,
            (ExpertType.MEMORY, ExpertType.SQL): True,
            
            # IO 与 SQL、锁专家相关
            (ExpertType.IO, ExpertType.SQL): True,
            (ExpertType.IO, ExpertType.LOCK): True,
            
            # SQL 与 锁、连接专家相关
            (ExpertType.SQL, ExpertType.LOCK): True,
            (ExpertType.SQL, ExpertType.CONNECTION): True,
            
            # 锁 与 连接专家相关
            (ExpertType.LOCK, ExpertType.CONNECTION): True,
        }
        
        # 双向检查
        return related_pairs.get((expert1, expert2), False) or \
               related_pairs.get((expert2, expert1), False)
    
    async def _generate_review_advice(
        self,
        reviewer_result: ExpertResult,
        target_result: ExpertResult,
        anomaly_info: Dict
    ) -> Optional[Dict]:
        """生成评审意见"""
        try:
            prompt = f"""
你是一个数据库诊断专家（{reviewer_result.expert_type.value}），请评审另一位专家的诊断结果。

【被评审专家】{target_result.expert_type.value}
【诊断结果】
根因: {[rc.get('type', '') for rc in target_result.root_causes[:3]]}
解决方案: {[s.get('action', '') for s in target_result.solutions[:3]]}
置信度: {target_result.confidence}

【你的诊断视角】
根因: {[rc.get('type', '') for rc in reviewer_result.root_causes[:3]]}
置信度: {reviewer_result.confidence}

【评审要求】
1. 评估对方诊断的合理性
2. 指出可能遗漏的根因
3. 提出改进建议
4. 给出评审置信度

请返回JSON格式:
{{
  "agreement_score": 0.8,
  "missed_causes": ["可能遗漏的根因"],
  "improvement_suggestions": ["改进建议"],
  "additional_evidence": ["需要补充的证据"],
  "review_confidence": 0.85
}}
"""
            
            llm = get_ChatOpenAI(
                model_name="deepseek-chat",
                temperature=0.3,
                max_tokens=500,
                streaming=False
            )
            
            response = await llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # 解析评审意见
            if response_text.startswith("{"):
                return json.loads(response_text)
            return None
            
        except Exception as e:
            print(f"  [WARN] 评审生成失败: {e}")
            return None
    
    async def _refine_results_with_reviews(
        self,
        expert_results: List[ExpertResult],
        review_advices: Dict[str, List[Dict]]
    ) -> List[Dict]:
        """
        @brief 基于评审意见精炼诊断结果
        @reference D-Bot Paper Section 7.3 - Result Refinement
        """
        refined_results = []
        
        for result in expert_results:
            expert_name = result.expert_type.value
            advices = review_advices.get(expert_name, [])
            
            if not advices:
                # 无评审意见，保持原结果
                refined_results.append({
                    "expert_type": expert_name,
                    "root_causes": result.root_causes,
                    "solutions": result.solutions,
                    "confidence": result.confidence,
                    "refined": False
                })
                continue
            
            # 基于评审意见精炼
            print(f"  🔧 精炼 {expert_name} 的诊断结果...")
            
            refined = await self._refine_single_result(result, advices)
            refined_results.append(refined)
        
        return refined_results
    
    async def _refine_single_result(
        self,
        result: ExpertResult,
        advices: List[Dict]
    ) -> Dict:
        """精炼单个专家的结果"""
        try:
            # 合并评审意见
            all_missed = []
            all_suggestions = []
            avg_agreement = 0
            
            for advice in advices:
                all_missed.extend(advice.get("missed_causes", []))
                all_suggestions.extend(advice.get("improvement_suggestions", []))
                avg_agreement += advice.get("agreement_score", 0.5)
            
            avg_agreement /= len(advices) if advices else 1
            
            # 如果一致性高，保持原结果
            if avg_agreement > 0.8:
                return {
                    "expert_type": result.expert_type.value,
                    "root_causes": result.root_causes,
                    "solutions": result.solutions,
                    "confidence": result.confidence,
                    "refined": False,
                    "agreement_score": avg_agreement
                }
            
            # 否则，生成精炼后的结果
            refined_root_causes = list(result.root_causes)
            for missed in all_missed[:2]:
                refined_root_causes.append({
                    "type": missed,
                    "description": f"评审建议补充: {missed}",
                    "confidence": 0.6,
                    "source": "peer_review"
                })
            
            refined_solutions = list(result.solutions)
            for suggestion in all_suggestions[:2]:
                refined_solutions.append({
                    "action": "评审建议",
                    "explanation": suggestion,
                    "priority": "medium",
                    "source": "peer_review"
                })
            
            # 调整置信度
            refined_confidence = result.confidence * avg_agreement
            
            return {
                "expert_type": result.expert_type.value,
                "root_causes": refined_root_causes[:5],
                "solutions": refined_solutions[:5],
                "confidence": refined_confidence,
                "refined": True,
                "agreement_score": avg_agreement,
                "review_count": len(advices)
            }
            
        except Exception as e:
            return {
                "expert_type": result.expert_type.value,
                "root_causes": result.root_causes,
                "solutions": result.solutions,
                "confidence": result.confidence,
                "refined": False,
                "error": str(e)
            }
    
    async def _aggregate_refined_results(
        self,
        refined_results: List[Dict],
        anomaly_info: Dict
    ) -> Dict:
        """汇总精炼后的结果 - 调用综合专家进行最终评审"""
        # 统计所有根因
        all_root_causes = []
        all_solutions = []
        refined_count = 0
        
        for result in refined_results:
            all_root_causes.extend(result.get("root_causes", []))
            all_solutions.extend(result.get("solutions", []))
            if result.get("refined"):
                refined_count += 1
        
        # 去重和排序
        root_causes = self._deduplicate_items(all_root_causes, "type")
        solutions = self._deduplicate_items(all_solutions, "action")
        
        # 计算共识率（对齐论文Section 7.3）
        consensus_rate = self._calculate_consensus_rate(refined_results)
        
        # 生成专家结果摘要供综合专家使用
        expert_results_summary = self._generate_expert_results_summary(refined_results)
        
        # 调用综合专家进行最终评审
        try:
            general_prompt = self.expert_assigner._build_expert_prompt(
                ExpertType.GENERAL, 
                anomaly_info,
                expert_results_summary
            )
            
            llm = get_ChatOpenAI(
                model_name="deepseek-chat",
                temperature=0.3,
                max_tokens=2000,
                streaming=False
            )
            
            print("  🔍 综合专家正在进行最终评审...")
            response = await llm.ainvoke(general_prompt)
            general_review = response.content if hasattr(response, 'content') else str(response)
            
            print("  [OK] 综合专家评审完成")
            
        except Exception as e:
            print(f"  [WARN] 综合专家评审失败: {e}")
            general_review = "综合评审失败，使用简单汇总结果"
        
        return {
            "consensus_analysis": f"基于 {len(refined_results)} 个专家的闭环评审结果",
            "disagreements": f"共 {refined_count} 个专家结果被精炼",
            "final_root_causes": root_causes[:5],
            "final_solutions": solutions[:5],
            "confidence_summary": f"共识率: {consensus_rate:.2f}",
            "expert_consensus_rate": consensus_rate,
            "refined_expert_count": refined_count,
            "general_expert_review": general_review
        }
    
    def _calculate_consensus_rate(self, refined_results: List[Dict]) -> float:
        """
        @brief 对齐论文的共识率计算（Section 7.3）
        @details 共识率 = （达成一致的根因数 / 总根因数）
        @param refined_results: 精炼后的专家结果列表
        @return: 共识率（0.0-1.0）
        """
        if not refined_results:
            return 0.0
        
        # 收集所有根因
        all_root_causes = []
        for result in refined_results:
            root_causes = result.get("root_causes", [])
            for rc in root_causes:
                if isinstance(rc, dict):
                    rc_type = rc.get("type", "")
                else:
                    rc_type = str(rc)
                if rc_type:
                    all_root_causes.append(rc_type)
        
        if not all_root_causes:
            return 0.0
        
        # 统计每个根因的支持专家数
        rc_support = {}
        for rc in all_root_causes:
            rc_support[rc] = rc_support.get(rc, 0) + 1
        
        # 计算共识率：支持专家数≥2的根因数 / 总根因数
        agreed_rc_count = sum([1 for cnt in rc_support.values() if cnt >= 2])
        total_rc_count = len(rc_support)
        
        if total_rc_count == 0:
            return 0.0
        
        consensus_rate = agreed_rc_count / total_rc_count
        return round(consensus_rate, 2)
    
    def _generate_expert_results_summary(self, refined_results: List[Dict]) -> str:
        """生成专家结果摘要，供综合专家评审使用"""
        summary_parts = []
        
        for result in refined_results:
            expert_type = result.get("expert_type", "未知专家")
            root_causes = result.get("root_causes", [])
            solutions = result.get("solutions", [])
            confidence = result.get("confidence", 0)
            
            # 格式化根因
            root_cause_str = ""
            if root_causes:
                for i, rc in enumerate(root_causes[:3], 1):
                    rc_type = rc.get("type", "") if isinstance(rc, dict) else str(rc)
                    rc_desc = rc.get("description", "") if isinstance(rc, dict) else ""
                    root_cause_str += f"  {i}. {rc_type}: {rc_desc}\n"
            
            # 格式化解决方案
            solution_str = ""
            if solutions:
                for i, s in enumerate(solutions[:3], 1):
                    s_action = s.get("action", "") if isinstance(s, dict) else str(s)
                    s_explain = s.get("explanation", "") if isinstance(s, dict) else ""
                    solution_str += f"  {i}. {s_action}: {s_explain}\n"
            
            summary_parts.append(f"""### {expert_type} (置信度: {confidence:.2f})
【根因分析】
{root_cause_str if root_cause_str else "  无明确根因"}
【解决方案】
{solution_str if solution_str else "  无明确方案"}
""")
        
        return "\n".join(summary_parts)
    
    def _simple_aggregation(self, expert_results: List[ExpertResult], anomaly_info: Dict) -> Dict:
        """简单汇总专家结果（当交叉评审失败时使用）"""
        # 统计所有根因
        all_root_causes = []
        for result in expert_results:
            for cause in result.root_causes:
                cause["expert_type"] = result.expert_type.value
                cause["confidence"] = result.confidence
                all_root_causes.append(cause)
        
        # 统计所有解决方案
        all_solutions = []
        for result in expert_results:
            for solution in result.solutions:
                solution["expert_type"] = result.expert_type.value
                all_solutions.append(solution)
        
        # 简单去重和排序
        root_causes = self._deduplicate_items(all_root_causes, "type")
        solutions = self._deduplicate_items(all_solutions, "action")
        
        return {
            "consensus_analysis": "基于专家结果的简单汇总",
            "disagreements": "详细交叉评审失败",
            "final_root_causes": root_causes[:5],
            "final_solutions": solutions[:5],
            "confidence_summary": f"基于 {len(expert_results)} 个专家结果的汇总",
            "expert_consensus_rate": 0.8,
            "failed_experts": []
        }
    
    def _deduplicate_items(self, items: List[Dict], key_field: str) -> List[Dict]:
        """去重并按置信度排序"""
        unique_items = {}
        
        for item in items:
            key = item.get(key_field, "")
            if key not in unique_items:
                unique_items[key] = item
            else:
                # 如果已存在，选择置信度更高的
                if item.get("confidence", 0) > unique_items[key].get("confidence", 0):
                    unique_items[key] = item
        
        # 按置信度排序
        return sorted(unique_items.values(), key=lambda x: x.get("confidence", 0), reverse=True)
    
    def _generate_default_diagnosis(self, anomaly_info: Dict) -> Dict:
        """生成默认诊断结果"""
        return {
            "consensus_analysis": "专家诊断全部失败，返回默认分析",
            "disagreements": "无可用专家结果",
            "final_root_causes": [{
                "type": "Unknown Issue",
                "description": "无法确定具体根因，建议进一步检查",
                "confidence": 0.1,
                "supporting_experts": [],
                "contradicting_experts": []
            }],
            "final_solutions": [{
                "action": "MONITOR",
                "sql": "SELECT * FROM pg_stat_activity WHERE state = 'active';",
                "explanation": "持续监控数据库性能指标",
                "priority": "high",
                "applicable_experts": []
            }],
            "confidence_summary": "低置信度结果",
            "expert_consensus_rate": 0,
            "failed_experts": []
        }
    
    def _calculate_dynamic_confidence(self, expert_config: Dict, anomaly_info: Dict, result: ExpertResult) -> float:
        """
        基于D-Bot论文的四维加权动态置信度计算
        
        公式: 专家最终置信度 = W_1 * 专业匹配度 + W_2 * 证据支持度 + W_3 * 推理质量分 + W_4 * 矛盾处理能力
        
        权重: W1=40%, W2=30%, W3=20%, W4=10%
        """
        expert_info = expert_config or {}
        
        # 1. 计算专业匹配度 (40%)
        alert_type = anomaly_info.get("alert_type", "").lower()
        description = anomaly_info.get("description", "").lower()
        
        domain_match_score = 0.5  # 默认中等匹配
        
        # 根据异常类型判断匹配度
        if "cpu" in alert_type or "cpu" in description:
            if result.expert_type == ExpertType.CPU:
                domain_match_score = 1.0
            elif result.expert_type == ExpertType.GENERAL:
                domain_match_score = 0.7
            else:
                domain_match_score = 0.3
        elif "memory" in alert_type or "内存" in description:
            if result.expert_type == ExpertType.MEMORY:
                domain_match_score = 1.0
            elif result.expert_type == ExpertType.GENERAL:
                domain_match_score = 0.7
            else:
                domain_match_score = 0.3
        elif "io" in alert_type or "磁盘" in description:
            if result.expert_type == ExpertType.IO:
                domain_match_score = 1.0
            elif result.expert_type == ExpertType.GENERAL:
                domain_match_score = 0.7
            else:
                domain_match_score = 0.3
        elif "lock" in alert_type or "锁" in description:
            if result.expert_type == ExpertType.LOCK:
                domain_match_score = 1.0
            elif result.expert_type == ExpertType.GENERAL:
                domain_match_score = 0.7
            else:
                domain_match_score = 0.3
        elif "connection" in alert_type or "连接" in description:
            if result.expert_type == ExpertType.CONNECTION:
                domain_match_score = 1.0
            elif result.expert_type == ExpertType.GENERAL:
                domain_match_score = 0.7
            else:
                domain_match_score = 0.3
        elif "sql" in alert_type or "慢查询" in description:
            if result.expert_type == ExpertType.SQL:
                domain_match_score = 1.0
            elif result.expert_type == ExpertType.GENERAL:
                domain_match_score = 0.7
            else:
                domain_match_score = 0.3
        
        # 2. 计算证据支持度 (30%)
        evidence_support_score = 0.2
        if result.reasoning_steps:
            has_observation = False
            for step in result.reasoning_steps:
                observation = getattr(step, 'observation', '') or (step.get('observation', '') if isinstance(step, dict) else '')
                if observation and len(observation) > 10:
                    has_observation = True
                    break
            if has_observation:
                evidence_support_score = 0.9
            else:
                evidence_support_score = 0.4
        
        # 3. 计算推理质量分 (20%)
        reasoning_quality_score = 0.3
        if result.reasoning_steps and len(result.reasoning_steps) >= 2:
            reasoning_quality_score = min(1.0, len(result.reasoning_steps) * 0.2)
        
        # 4. 计算矛盾处理能力 (10%)
        conflict_handling_score = 0.5
        if result.error_message:
            conflict_handling_score = 0.2
        elif result.root_causes and len(result.root_causes) > 0:
            conflict_handling_score = 0.8
        
        # 加权计算最终置信度
        final_confidence = (
            0.4 * domain_match_score +
            0.3 * evidence_support_score +
            0.2 * reasoning_quality_score +
            0.1 * conflict_handling_score
        )
        
        return round(final_confidence, 2)
    
    def _expert_result_to_dict(self, result: ExpertResult, anomaly_info: Dict = None) -> Dict:
        """将专家结果转换为字典格式 - 包含完整的专家名称和推理内容"""
        # 获取专家名称和描述
        expert_info = self.expert_assigner.expert_definitions.get(result.expert_type, {})
        expert_name = expert_info.get("name", result.expert_type.value)
        expert_description = expert_info.get("description", "")
        
        # 提取推理内容
        reasoning_content = ""
        if result.reasoning_steps:
            reasoning_parts = []
            for i, step in enumerate(result.reasoning_steps[:5], 1):  # 最多取前5步
                thought = getattr(step, 'thought', '') or (step.get('thought', '') if isinstance(step, dict) else '')
                action = getattr(step, 'action', '') or (step.get('action', '') if isinstance(step, dict) else '')
                observation = getattr(step, 'observation', '') or (step.get('observation', '') if isinstance(step, dict) else '')
                reasoning_parts.append(f"步骤{i}: {thought}")
                if action:
                    reasoning_parts.append(f"  动作: {action}")
                if observation:
                    reasoning_parts.append(f"  观察: {observation[:200]}...")  # 限制观察长度
            reasoning_content = "\n".join(reasoning_parts)
        
        # 提取根因结论
        root_cause_summary = ""
        if result.root_causes:
            root_cause_summary = "; ".join([
                rc.get("description", "") if isinstance(rc, dict) else str(rc)
                for rc in result.root_causes[:3]  # 最多取前3个
            ])
        
        # 计算动态置信度 - 传入正确的 anomaly_info
        final_confidence = self._calculate_dynamic_confidence(expert_info, anomaly_info or {}, result)
        
        return {
            "expert_id": result.expert_type.value,
            "expert_name": expert_name,
            "expert_type": result.expert_type.value,
            "role": expert_description,
            "status": "completed" if not result.error_message else "failed",
            "confidence": final_confidence,
            "reasoning": reasoning_content,
            "root_cause_summary": root_cause_summary,
            "diagnosis_time": f"{result.diagnosis_time:.2f}s",
            "reasoning_steps_count": len(result.reasoning_steps),
            "root_causes_count": len(result.root_causes),
            "solutions_count": len(result.solutions),
            "tree_stats": result.tree_stats,
            "error_message": result.error_message,
            # 保留原始推理步骤供前端详细展示
            "reasoning_steps": [
                {
                    "step": i + 1,
                    "thought": getattr(step, 'thought', '') or (step.get('thought', '') if isinstance(step, dict) else ''),
                    "action": getattr(step, 'action', '') or (step.get('action', '') if isinstance(step, dict) else ''),
                    "observation": getattr(step, 'observation', '') or (step.get('observation', '') if isinstance(step, dict) else '')
                }
                for i, step in enumerate(result.reasoning_steps[:10])  # 最多10步
            ],
            # 保留根因详情
            "root_causes": result.root_causes[:5] if result.root_causes else [],
            # 保留解决方案
            "solutions": result.solutions[:5] if result.solutions else []
        }


# 单例实例
collaborative_diagnosis = CollaborativeDiagnosis()


async def run_collaborative_diagnosis_async(anomaly_info: Dict) -> Dict:
    """
    异步版本：供上层异步代码直接调用
    Reference: D-Bot Paper Section 7
    """
    return await collaborative_diagnosis.diagnose_collaborative(anomaly_info)


def run_collaborative_diagnosis(anomaly_info: Dict) -> Dict:
    """
    同步版本：供测试或同步环境使用
    Reference: D-Bot Paper Section 7
    """
    try:
        loop = asyncio.get_running_loop()
        return asyncio.ensure_future(
            collaborative_diagnosis.diagnose_collaborative(anomaly_info),
            loop=loop
        )
    except RuntimeError:
        return asyncio.run(collaborative_diagnosis.diagnose_collaborative(anomaly_info))


# 测试函数
def test_collaborative_diagnosis():
    """测试协作诊断功能"""
    test_anomaly = {
        "alert_type": "CPU High",
        "description": "CPU使用率异常升高至95%，系统响应缓慢",
        "severity": "high"
    }
    
    result = run_collaborative_diagnosis(test_anomaly)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result


if __name__ == "__main__":
    test_collaborative_diagnosis()
