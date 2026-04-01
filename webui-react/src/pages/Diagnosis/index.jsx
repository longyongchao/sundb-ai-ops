/**
 * 智能诊断页面 - 数据库诊断系统核心交互界面
 * 
 * 功能模块：
 * 1. 异常信息输入 - 支持文件上传和手动输入两种方式
 * 2. 诊断进度展示 - 实时显示 Tree Search 推理过程
 * 3. 诊断结果渲染 - 展示根因分析、优化建议、知识来源
 * 4. 推理可视化 - 以树形图展示完整推理链路
 * 
 * 技术实现：
 * - 轮询机制：每 2 秒查询诊断进度，实时更新界面
 * - 状态管理：使用 Context API 管理全局诊断状态
 * - 防抖处理：避免用户重复点击导致重复诊断
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Row, Col, Card, Button, Upload, message, Spin,
  Timeline, Tag, Descriptions, Divider, Input, Select, Alert, Progress, Tooltip,
  Modal
} from 'antd';
import {
  UploadOutlined, PlayCircleOutlined, FileTextOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined,
  LoadingOutlined, BugOutlined, SyncOutlined, TeamOutlined,
  UserOutlined, MessageOutlined, ThunderboltOutlined, BranchesOutlined,
  TranslationOutlined, StopOutlined, BookOutlined, FileSearchOutlined,
  LineChartOutlined, ToolOutlined, BulbOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { useLocation } from 'react-router-dom';
import { ReasoningTreeChart, MetricLineChart } from '@/components/Charts';
import DiagnosisProgressGraph from '@/components/Charts/DiagnosisProgressGraph';
import ThinkingTerminal from '@/components/ThinkingTerminal';
import EvaluationTable from '@/components/EvaluationTable';
import SqlHighlight from '@/components/SqlHighlight';
import { diagnoseAPI, translateAPI, sundbTrcAPI } from '@/utils/api';
import { useDiagnosis } from '@/context/DiagnosisContext';
import { stripMarkdown, stripMarkdownPreserveCode } from '@/utils/markdownUtils';
import axios from 'axios';
import TrcFaultPanel from '@/components/TrcFaultPanel';
import TrcTimelinePanel from '@/components/TrcTimelinePanel';
import TrcFaultSummaryChart from '@/components/Charts/TrcFaultSummaryChart';

const { TextArea } = Input;
const { Option } = Select;

const ROOT_CAUSE_CN_MAP = {
  'timed_task_conflict': '定时任务冲突',
  'disk_spill': '磁盘溢出',
  'large_table': '大表扫描',
  'lock_contention': '锁争用',
  'memory_resource_contention': '内存资源竞争',
  'cpu_resource_contention': 'CPU资源竞争',
  'io_resource_contention': 'I/O资源竞争',
  'vacuum_event': 'VACUUM事件',
  'analyze_event': 'ANALYZE事件',
  'missing_index': '缺失索引',
  'unused_and_redundant_index': '冗余索引',
  'many_dead_tuples': '大量死元组',
  'heavy_scan_operator': '大量扫描操作',
  'abnormal_plan_time': '异常计划时间',
  'poor_join_performance': '连接性能差',
  'poor_aggregation_performance': '聚合性能差',
  'complex_execution_plan': '复杂执行计划',
  'correlated_subquery': '相关子查询',
  'workload_contention': '工作负载竞争',
  'database_wait_event': '数据库等待事件',
  'lack_of_statistics': '统计信息缺失',
  'abnormal_network_status': '网络状态异常',
  'os_resource_contention': '操作系统资源竞争',
  'slow_sql': '慢SQL查询',
  'cpu_high': 'CPU使用率过高',
  'memory_high': '内存使用率过高',
  'io_high': 'I/O负载过高',
  'lock_wait': '锁等待',
  'deadlock': '死锁',
  'SlowQueries': '慢查询问题',
  'HighCPU': 'CPU使用率过高',
  'HighMemory': '内存使用率过高',
  'HighDiskIO': '磁盘I/O过高',
  'LockWait': '锁等待/死锁',
  'ConnectionExhausted': '连接池耗尽',
  'LowCacheHit': '缓存命中率过低',
  'MissingIndex': '索引缺失',
  'TableBloat': '表膨胀',
  'IdleTransaction': '空闲事务',
  'BlockedSession': '阻塞会话',
  'HighRollback': '高回滚率'
};

const buildAnomalyInfo = (fileContent) => {
  if (!fileContent || typeof fileContent !== 'string') {
    return {
      alert_type: "Database Performance Anomaly",
      description: "数据库性能异常（文件内容为空或无法解析）",
      severity: "medium",
      timestamp: new Date().toISOString(),
      source: "unknown"
    };
  }

  const content = fileContent.toLowerCase();

  const isSunDBTrc = (
    content.includes('instance(') ||
    content.includes('thread(') ||
    content.includes('[information]') ||
    content.includes('[warning]') ||
    content.includes('[fatal]') ||
    content.includes('[deadlock]') ||
    content.includes('err-hy000') ||
    content.includes('err-42000') ||
    content.includes('err-28000')
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

  const isSlowQueryLog = (
    content.includes('slow query') ||
    (content.includes('duration:') && content.includes('ms')) ||
    (content.includes('query_time:') && content.includes('lock_time:'))
  );
  if (isSlowQueryLog) {
    return {
      alert_type: "Slow Queries",
      description: "检测到数据库慢查询异常，存在长时间执行的SQL语句",
      severity: "medium",
      timestamp: new Date().toISOString(),
      source: "slow_query_log"
    };
  }

  const isCpuHigh = (
    content.includes('cpu') && (
      content.includes('high') ||
      content.includes('load average') ||
      content.includes('usage') ||
      content.includes('utilization')
    )
  );
  if (isCpuHigh) {
    return {
      alert_type: "CPU High",
      description: "检测到数据库服务器CPU使用率过高，可能存在计算密集型任务",
      severity: "high",
      timestamp: new Date().toISOString(),
      source: "system_monitor"
    };
  }

  const isMemoryHigh = (
    content.includes('memory') && (
      content.includes('high') ||
      content.includes('swap') ||
      content.includes('oom') ||
      content.includes('out of memory')
    )
  );
  if (isMemoryHigh) {
    return {
      alert_type: "Memory High",
      description: "检测到数据库服务器内存使用率过高，可能存在内存泄漏或大查询",
      severity: "high",
      timestamp: new Date().toISOString(),
      source: "system_monitor"
    };
  }

  const isLockWait = (
    content.includes('lock') && (
      content.includes('wait') ||
      content.includes('deadlock') ||
      content.includes('blocked')
    )
  );
  if (isLockWait) {
    return {
      alert_type: "Lock Wait",
      description: "检测到数据库锁等待或死锁，可能导致事务阻塞",
      severity: "high",
      timestamp: new Date().toISOString(),
      source: "transaction_log"
    };
  }

  const isIoHigh = (
    content.includes('io') && (
      content.includes('high') ||
      content.includes('wait') ||
      content.includes('utilization') ||
      content.includes('disk')
    )
  );
  if (isIoHigh) {
    return {
      alert_type: "IO High",
      description: "检测到数据库磁盘IO负载过高，可能存在大量读写操作",
      severity: "medium",
      timestamp: new Date().toISOString(),
      source: "system_monitor"
    };
  }

  return {
    alert_type: "Database Performance Anomaly",
    description: "检测到数据库性能异常，具体类型需进一步分析",
    severity: "medium",
    timestamp: new Date().toISOString(),
    source: "unknown"
  };
};

// ========== 内联翻译组件（用于 InlineKnowledgePanel） ==========
const InlineTranslatableText = ({ text, style = {} }) => {
  const [translated, setTranslated] = React.useState(text);
  const [isTranslating, setIsTranslating] = React.useState(false);
  const [cached, setCached] = React.useState(false);
  
  React.useEffect(() => {
    if (cached) return;
    
    if (/[\u4e00-\u9fa5]/.test(text)) {
      setTranslated(text);
      setCached(true);
      return;
    }
    
    if (text.length > 10) {
      setIsTranslating(true);
      translateAPI.translateText(text, 'zh').then(result => {
        setTranslated(result);
        setCached(true);
        setIsTranslating(false);
      }).catch(() => {
        setIsTranslating(false);
        setCached(true);
      });
    }
  }, [text, cached]);
  
  if (isTranslating) {
    return (
      <span style={style}>
        <LoadingOutlined style={{ marginRight: '6px' }} spin />
        正在翻译...
      </span>
    );
  }
  return <span style={style}>{translated}</span>;
};

// ========== 内联组件：知识检索面板（修复版） ==========
const InlineKnowledgePanel = ({ data = [], title = '知识检索分析 (BM25)' }) => {
  if (!data || data.length === 0) {
    return (
      <Card 
        title={
          <span>
            <BookOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
            {title}
          </span>
        }
        style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
        headStyle={{ backgroundColor: '#1e1e1e', borderBottom: '1px solid #333' }}
        bodyStyle={{ backgroundColor: '#1e1e1e' }}
      >
        <div style={{ 
          padding: '40px', 
          backgroundColor: '#2d2d2d', 
          borderRadius: '8px', 
          border: '1px solid #444',
          textAlign: 'center',
          color: '#8c8c8c'
        }}>
          <FileSearchOutlined style={{ fontSize: '48px', color: '#555', marginBottom: '16px' }} />
          <div style={{ fontSize: '16px', color: '#b0b0b0' }}>暂无知识检索结果</div>
          <div style={{ fontSize: '14px', color: '#666', marginTop: '8px' }}>BM25算法未匹配到相关知识块，或诊断过程未开始</div>
        </div>
      </Card>
    );
  }

  const getRelevanceColor = (percentage) => {
    if (percentage >= 85) return '#52c41a';
    if (percentage >= 70) return '#1890ff';
    if (percentage >= 50) return '#faad14';
    return '#ff4d4f';
  };

  const getMatchScore = (item) => {
    return item?.vector_score ?? item?.score ?? item?.bm25_score ?? 0;
  };

  const getScoreLabel = (item) => {
    if (item?.vector_score !== undefined) return '向量';
    if (item?.score !== undefined) return '匹配';
    return 'BM25';
  };

  const avgBM25Score = data.reduce((sum, item) => sum + getMatchScore(item), 0) / data.length;
  const highCount = data.filter(item => item.relevance_percentage >= 85).length;
  const mediumCount = data.filter(item => item.relevance_percentage >= 70 && item.relevance_percentage < 85).length;
  const lowCount = data.filter(item => item.relevance_percentage < 70).length;

  return (
    <Card 
      title={
        <span>
          <BookOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
          {title}
        </span>
      }
      extra={
        <Tooltip title={`BM25检索到 ${data.length} 条相关知识`}>
          <Tag color="blue" icon={<FileSearchOutlined />}>
            Top-{data.length} 检索结果
          </Tag>
        </Tooltip>
      }
      style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
      headStyle={{ backgroundColor: '#1e1e1e', borderBottom: '1px solid #333' }}
      bodyStyle={{ backgroundColor: '#1e1e1e', padding: '20px' }}
    >
      <div style={{ 
        marginBottom: '20px', 
        padding: '16px', 
        backgroundColor: '#1a2a3a', 
        borderRadius: '8px', 
        border: '1px solid #2d4a6a',
        display: 'flex',
        alignItems: 'center'
      }}>
        <FileSearchOutlined style={{ color: '#1890ff', fontSize: '20px', marginRight: '12px' }} />
        <div>
          <div style={{ fontSize: '14px', color: '#91d5ff', fontWeight: 'bold' }}>知识检索机制</div>
          <div style={{ fontSize: '13px', color: '#6a9fcf', marginTop: '4px' }}>BM25算法根据异常上下文检索相关知识块，支持跨文档语义匹配</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'row', gap: '20px', overflowX: 'auto', paddingBottom: '12px' }}>
        {data.map((item) => {
          const isTruncated = item.cause_name.length > 15;
          
          return (
            <Card 
              key={item.rank}
              size="small" 
              style={{ 
                minWidth: '380px',
                maxWidth: '450px',
                flex: '0 0 auto',
                borderLeft: `4px solid ${getRelevanceColor(item.relevance_percentage)}`,
                backgroundColor: '#252525',
                border: '1px solid #333'
              }}
              headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333', padding: '16px' }}
              bodyStyle={{ backgroundColor: '#252525', padding: '20px' }}
              title={
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ 
                      backgroundColor: '#1890ff', 
                      color: '#fff', 
                      padding: '4px 10px', 
                      borderRadius: '4px', 
                      fontSize: '13px',
                      fontWeight: 'bold'
                    }}>
                      Rank #{item.rank}
                    </span>
                    <Tooltip title={isTruncated ? item.cause_name : ''}>
                      <span style={{ fontWeight: 'bold', color: '#e6e6e6', fontSize: '14px', cursor: isTruncated ? 'pointer' : 'default' }}>
                        {isTruncated ? item.cause_name.substring(0, 15) + '...' : item.cause_name}
                      </span>
                    </Tooltip>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Tooltip title={`${getScoreLabel(item)}分数: ${getMatchScore(item).toFixed(3)}`}>
                      <span style={{ 
                        backgroundColor: getRelevanceColor(item.relevance_percentage), 
                        color: '#fff', 
                        padding: '4px 8px', 
                        borderRadius: '4px', 
                        fontSize: '12px',
                        fontWeight: 'bold'
                      }}>
                        {getScoreLabel(item)}: {getMatchScore(item).toFixed(2)}
                      </span>
                    </Tooltip>
                    {item?.source && (
                      <Tag color={item.source === '内置专家规则' ? 'blue' : 'green'} style={{ fontSize: '11px' }}>
                        {item.source === '内置专家规则' ? '内置规则' : '向量库'}
                      </Tag>
                    )}
                  </div>
                </div>
              }
              extra={
                <Progress 
                  percent={item.relevance_percentage} 
                  size="small" 
                  strokeColor={getRelevanceColor(item.relevance_percentage)}
                  format={() => `${item.relevance_percentage}%`}
                  style={{ minWidth: '70px' }}
                />
              }
            >
              <div style={{ marginBottom: '16px' }}>
                <div style={{ 
                  fontSize: '13px', 
                  color: '#8c8c8c', 
                  marginBottom: '8px',
                  fontWeight: 'bold'
                }}>
                  问题描述（中文翻译）
                </div>
                <div style={{ 
                  backgroundColor: '#1a2a3a', 
                  padding: '12px', 
                  borderRadius: '6px',
                  fontSize: '14px',
                  lineHeight: '1.6',
                  color: '#91d5ff',
                  border: '1px solid #2d4a6a',
                  wordBreak: 'break-word',
                  maxHeight: '200px',
                  overflowY: 'auto'
                }}>
                  <TranslationOutlined style={{ marginRight: '6px', color: '#1890ff', fontSize: '14px' }} />
                  <InlineTranslatableText text={item.description} />
                </div>
              </div>

              {item.metrics && item.metrics.length > 0 && (
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ 
                    fontSize: '13px', 
                    color: '#8c8c8c', 
                    marginBottom: '8px',
                    fontWeight: 'bold'
                  }}>
                    相关指标
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {item.metrics.slice(0, 4).map((metric, idx) => (
                      <span 
                        key={idx}
                        style={{ 
                          backgroundColor: '#1890ff', 
                          color: '#fff', 
                          padding: '4px 10px', 
                          borderRadius: '4px', 
                          fontSize: '12px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        <LineChartOutlined />
                        {metric}
                      </span>
                    ))}
                    {item.metrics.length > 4 && (
                      <span style={{ 
                        backgroundColor: '#555', 
                        color: '#fff', 
                        padding: '4px 10px', 
                        borderRadius: '4px', 
                        fontSize: '12px' 
                      }}>
                        +{item.metrics.length - 4}
                      </span>
                    )}
                  </div>
                </div>
              )}
              
              {item.actionable_steps && item.actionable_steps.length > 0 && (
                <div style={{ marginBottom: '12px' }}>
                  <div style={{ 
                    fontSize: '13px', 
                    color: '#8c8c8c', 
                    marginBottom: '8px',
                    fontWeight: 'bold'
                  }}>
                    诊断步骤
                  </div>
                  <ul style={{ 
                    margin: 0, 
                    paddingLeft: '20px', 
                    fontSize: '13px', 
                    backgroundColor: '#2d2d2d', 
                    padding: '10px 10px 10px 24px', 
                    borderRadius: '6px', 
                    border: '1px solid #444',
                    lineHeight: '1.8'
                  }}>
                    {item.actionable_steps.slice(0, 3).map((step, idx) => (
                      <li key={idx} style={{ marginBottom: '4px', color: '#e6e6e6' }}>
                        <CheckCircleOutlined style={{ color: '#52c41a', marginRight: '6px' }} />
                        {step.length > 35 ? step.substring(0, 35) + '...' : step}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              
              <div style={{ 
                marginTop: '12px', 
                fontSize: '12px', 
                color: '#666',
                paddingTop: '8px',
                borderTop: '1px solid #333'
              }}>
                知识来源: 数据库维护文档 | 匹配算法: BM25
              </div>
            </Card>
          );
        })}
      </div>

      <div style={{ marginTop: '20px', padding: '16px', backgroundColor: '#252525', borderRadius: '8px', border: '1px solid #333' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '13px', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
            <div>
              <span style={{ color: '#8c8c8c' }}>检索统计:</span>
              <span style={{ marginLeft: '8px', color: '#91d5ff', fontWeight: 'bold', fontSize: '14px' }}>
                平均BM25分数: {avgBM25Score.toFixed(3)}
              </span>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <span style={{ 
                backgroundColor: '#52c41a', 
                color: '#fff', 
                padding: '4px 10px', 
                borderRadius: '4px', 
                fontSize: '12px',
                fontWeight: 'bold'
              }}>
                高相关: {highCount}
              </span>
              <span style={{ 
                backgroundColor: '#1890ff', 
                color: '#fff', 
                padding: '4px 10px', 
                borderRadius: '4px', 
                fontSize: '12px',
                fontWeight: 'bold'
              }}>
                中相关: {mediumCount}
              </span>
              <span style={{ 
                backgroundColor: '#faad14', 
                color: '#fff', 
                padding: '4px 10px', 
                borderRadius: '4px', 
                fontSize: '12px',
                fontWeight: 'bold'
              }}>
                低相关: {lowCount}
              </span>
            </div>
          </div>
          <div>
            <span style={{ color: '#666', fontSize: '12px' }}>
              BM25算法: TF-IDF + 文档长度归一化
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
};

// ========== 内联组件：反思机制面板（修复版） ==========
const InlineReflectionPanel = ({ data = [], title = '反思机制洞察', totalSteps = 7 }) => {
  if (!data || data.length === 0) {
    return (
      <Card 
        title={
          <span>
            <SyncOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
            {title}
          </span>
        }
        style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
        headStyle={{ backgroundColor: '#1e1e1e', borderBottom: '1px solid #333' }}
        bodyStyle={{ backgroundColor: '#1e1e1e' }}
      >
        <div style={{ 
          padding: '20px', 
          backgroundColor: '#2d2d2d', 
          borderRadius: '8px', 
          border: '1px solid #444',
          textAlign: 'center',
          color: '#8c8c8c'
        }}>
          <SyncOutlined style={{ fontSize: '32px', color: '#555', marginBottom: '12px' }} />
          <div style={{ fontSize: '14px', color: '#b0b0b0' }}>暂无反思过程记录</div>
          <div style={{ fontSize: '12px', color: '#666', marginTop: '8px' }}>诊断过程未触发反思机制，或反思数据未生成</div>
        </div>
      </Card>
    );
  }

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.9) return '#52c41a';
    if (confidence >= 0.7) return '#1890ff';
    if (confidence >= 0.5) return '#faad14';
    return '#ff4d4f';
  };

  const getTriggerIcon = (trigger) => {
    if (trigger.includes('Low quality') || trigger.includes('错误')) {
      return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
    }
    if (trigger.includes('Key decision') || trigger.includes('关键')) {
      return <BulbOutlined style={{ color: '#1890ff' }} />;
    }
    return <SyncOutlined style={{ color: '#faad14' }} />;
  };

  const getTriggerTagStyle = (trigger) => {
    let bgColor = '#555';
    let textColor = '#fff';
    
    if (trigger.includes('Low quality') || trigger.includes('错误')) {
      bgColor = '#cf1322';
      textColor = '#fff';
    } else if (trigger.includes('Key decision') || trigger.includes('关键')) {
      bgColor = '#1890ff';
      textColor = '#fff';
    } else if (trigger.includes('Initial')) {
      bgColor = '#13c2c2';
      textColor = '#fff';
    }
    
    return {
      backgroundColor: bgColor,
      color: textColor,
      border: 'none',
      fontSize: '11px',
      padding: '4px 8px',
      borderRadius: '4px'
    };
  };

  const translateRecommendedAction = (action) => {
    if (action === 'Switch to different analysis approach') {
      return '建议切换分析方向，重点排查慢查询执行计划、系统表统计信息等相关问题';
    }
    return action;
  };

  const avgConfidence = data.reduce((sum, item) => sum + item.confidence, 0) / data.length;
  const avgStep = Math.round(data.reduce((sum, item) => sum + item.step, 0) / data.length);
  const lastStep = data[data.length - 1].step;

  return (
    <Card 
      title={
        <span>
          <SyncOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
          {title}
        </span>
      }
      extra={
        <Tooltip title={`共 ${data.length} 次反思触发`}>
          <Tag color="blue" icon={<SyncOutlined />}>
            {data.length} 次反思
          </Tag>
        </Tooltip>
      }
      style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
      headStyle={{ backgroundColor: '#1e1e1e', borderBottom: '1px solid #333' }}
      bodyStyle={{ backgroundColor: '#1e1e1e', padding: '16px' }}
    >
      <div style={{ 
        marginBottom: '16px', 
        padding: '12px', 
        backgroundColor: '#1a2a3a', 
        borderRadius: '8px', 
        border: '1px solid #2d4a6a',
        display: 'flex',
        alignItems: 'center'
      }}>
        <SyncOutlined style={{ color: '#1890ff', fontSize: '18px', marginRight: '12px' }} />
        <div>
          <div style={{ fontSize: '13px', color: '#91d5ff', fontWeight: 'bold' }}>反思机制 (Reflection Mechanism)</div>
          <div style={{ fontSize: '12px', color: '#6a9fcf', marginTop: '4px' }}>当诊断过程遇到低质量观察、决策点或矛盾结果时，系统自动触发反思过程重新评估推理路径</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'row', gap: '16px', overflowX: 'auto', paddingBottom: '8px' }}>
        {data.map((insight, index) => (
          <Card 
            key={index}
            size="small" 
            style={{ 
              minWidth: '300px',
              maxWidth: '360px',
              flex: '0 0 auto',
              borderLeft: `4px solid ${getConfidenceColor(insight.confidence)}`,
              backgroundColor: '#252525',
              border: '1px solid #333'
            }}
            headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333', padding: '12px' }}
            bodyStyle={{ backgroundColor: '#252525', padding: '12px' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                <span style={getTriggerTagStyle(insight.trigger)}>
                  {insight.trigger.length > 15 ? insight.trigger.substring(0, 15) + '...' : insight.trigger}
                </span>
                <span style={{ 
                  backgroundColor: '#722ed1', 
                  color: '#fff', 
                  padding: '2px 6px', 
                  borderRadius: '4px', 
                  fontSize: '11px' 
                }}>
                  步骤 {insight.step}
                </span>
              </div>
              <Tooltip title={`反思置信度: ${insight.confidence.toFixed(3)}`}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Progress 
                    type="circle" 
                    percent={Math.round(insight.confidence * 100)} 
                    size={28} 
                    strokeColor={getConfidenceColor(insight.confidence)}
                    format={() => `${Math.round(insight.confidence * 100)}%`}
                  />
                </div>
              </Tooltip>
            </div>
            
            <Descriptions size="small" column={1} labelStyle={{ color: '#8c8c8c', fontSize: '12px' }}>
              <Descriptions.Item label="反思洞察">
                <div style={{ 
                  backgroundColor: '#2d2d2d', 
                  padding: '8px', 
                  borderRadius: '4px',
                  fontSize: '12px',
                  lineHeight: '1.4',
                  color: '#e6e6e6',
                  border: '1px solid #444',
                  maxHeight: '120px',
                  overflowY: 'auto',
                  wordBreak: 'break-word'
                }}>
                  {getTriggerIcon(insight.trigger)}
                  <span style={{ marginLeft: '4px' }}>
                    {insight.insight}
                  </span>
                </div>
              </Descriptions.Item>
              
              <Descriptions.Item label="修正建议">
                <div style={{ 
                  backgroundColor: '#1a3a1a', 
                  padding: '8px', 
                  borderRadius: '4px',
                  fontSize: '12px',
                  display: 'flex',
                  alignItems: 'flex-start',
                  color: '#a6d6a6',
                  border: '1px solid #2d5a2d',
                  wordBreak: 'break-word',
                  maxHeight: '100px',
                  overflowY: 'auto'
                }}>
                  <CheckCircleOutlined style={{ color: '#52c41a', marginRight: '4px', flexShrink: 0, marginTop: '2px' }} />
                  <span>{translateRecommendedAction(insight.recommended_action)}</span>
                </div>
              </Descriptions.Item>
            </Descriptions>
            
            <div style={{ marginTop: '8px', fontSize: '10px', color: '#666' }}>
              反思算法: Self-Reflection Prompt
            </div>
          </Card>
        ))}
      </div>

      <div style={{ marginTop: '16px', padding: '12px', backgroundColor: '#252525', borderRadius: '8px', border: '1px solid #333' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
            <div>
              <span style={{ color: '#8c8c8c' }}>反思统计:</span>
              <span style={{ marginLeft: '8px', color: '#91d5ff', fontWeight: 'bold' }}>
                {data.length > 1 
                  ? `平均触发间隔: ${Math.round((lastStep - data[0].step) / (data.length - 1))} 步`
                  : '仅触发1次，无间隔数据'}
              </span>
            </div>
            <div>
              <span style={{ color: '#b7eb8f', fontWeight: 'bold' }}>
                平均置信度: {avgConfidence.toFixed(3)}
              </span>
            </div>
          </div>
          <div>
            <span style={{ color: '#666', fontSize: '11px' }}>
              反思机制: 质量评估 + 路径修正
            </span>
          </div>
        </div>
      </div>

      <div style={{ marginTop: '12px' }}>
        <h5 style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '8px' }}>反思类型分布</h5>
        <div style={{ 
          display: 'flex', 
          gap: '8px', 
          padding: '12px', 
          backgroundColor: '#252525', 
          borderRadius: '8px', 
          border: '1px solid #333',
          flexWrap: 'wrap'
        }}>
          {(() => {
            const triggerCounts = {};
            data.forEach(item => {
              triggerCounts[item.trigger] = (triggerCounts[item.trigger] || 0) + 1;
            });
            
            return Object.entries(triggerCounts).map(([trigger, count]) => (
              <span 
                key={trigger} 
                style={getTriggerTagStyle(trigger)}
              >
                {trigger.length > 20 ? trigger.substring(0, 20) + '...' : trigger}: {count}次
              </span>
            ));
          })()}
        </div>
      </div>

      <div style={{ marginTop: '12px' }}>
        <div style={{ 
          padding: '12px', 
          backgroundColor: '#1a3a1a', 
          borderRadius: '8px', 
          border: '1px solid #2d5a2d',
          display: 'flex',
          alignItems: 'center'
        }}>
          <CheckCircleOutlined style={{ color: '#52c41a', fontSize: '18px', marginRight: '12px', flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: '13px', color: '#a6d6a6', fontWeight: 'bold' }}>反思效果评估</div>
            <div style={{ fontSize: '12px', color: '#7ab87a', marginTop: '4px' }}>
              共 {data.length} 次反思触发，平均在步骤 {avgStep} 触发，有效修正推理路径。
            </div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#1a2a3a', borderRadius: '8px', border: '1px solid #2d4a6a' }}>
        <div style={{ fontSize: '12px', color: '#91d5ff' }}>
          <strong>反思闭环说明:</strong> 本次反思于诊断第 {lastStep} 步触发，未触发推理路径重定向，诊断流程已正常完成。
        </div>
      </div>
    </Card>
  );
};

// ========== 内联组件：工具匹配面板（修复版） ==========
const InlineToolMatchPanel = ({ data = [], title = '工具匹配分析' }) => {
  if (!data || data.length === 0) {
    return (
      <Card 
        title={
          <span>
            <ToolOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
            {title}
          </span>
        }
        style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
        headStyle={{ backgroundColor: '#1e1e1e', borderBottom: '1px solid #333' }}
        bodyStyle={{ backgroundColor: '#1e1e1e' }}
      >
        <div style={{ 
          padding: '20px', 
          backgroundColor: '#2d2d2d', 
          borderRadius: '8px', 
          border: '1px solid #444',
          textAlign: 'center',
          color: '#8c8c8c'
        }}>
          <ToolOutlined style={{ fontSize: '32px', color: '#555', marginBottom: '12px' }} />
          <div style={{ fontSize: '14px', color: '#b0b0b0' }}>暂无工具匹配分析结果</div>
          <div style={{ fontSize: '12px', color: '#666', marginTop: '8px' }}>诊断过程中未生成工具匹配数据，或Sentence-BERT匹配未执行</div>
        </div>
      </Card>
    );
  }

  const getConfidenceLevel = (score) => {
    if (score > 0.8) return 'High';
    if (score >= 0.6) return 'Medium';
    return 'Low';
  };

  const getConfidenceColor = (score) => {
    const level = getConfidenceLevel(score);
    if (level === 'High') return '#52c41a';
    if (level === 'Medium') return '#faad14';
    return '#ff4d4f';
  };

  const getScoreColor = (score) => {
    if (score >= 0.8) return '#52c41a';
    if (score >= 0.6) return '#1890ff';
    if (score >= 0.4) return '#faad14';
    return '#ff4d4f';
  };

  const stats = {
    totalSteps: data.length,
    avgScore: data.reduce((sum, item) => sum + item.sentence_bert_score, 0) / data.length,
    highConfidence: data.filter(item => item.sentence_bert_score > 0.8).length,
    mediumConfidence: data.filter(item => item.sentence_bert_score >= 0.6 && item.sentence_bert_score <= 0.8).length,
    lowConfidence: data.filter(item => item.sentence_bert_score < 0.6).length,
  };

  return (
    <Card 
      title={
        <span>
          <ToolOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
          {title}
        </span>
      }
      extra={
        <Tooltip title={`共 ${data.length} 步工具匹配`}>
          <Tag color="blue" icon={<ToolOutlined />}>
            {data.length} 步匹配
          </Tag>
        </Tooltip>
      }
      style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
      headStyle={{ backgroundColor: '#1e1e1e', borderBottom: '1px solid #333' }}
      bodyStyle={{ backgroundColor: '#1e1e1e' }}
    >
      <div style={{ 
        marginBottom: '16px', 
        padding: '12px', 
        backgroundColor: '#1a2a3a', 
        borderRadius: '8px', 
        border: '1px solid #2d4a6a',
        display: 'flex',
        alignItems: 'center'
      }}>
        <ToolOutlined style={{ color: '#1890ff', fontSize: '18px', marginRight: '12px' }} />
        <div>
          <div style={{ fontSize: '13px', color: '#91d5ff', fontWeight: 'bold' }}>工具匹配机制</div>
          <div style={{ fontSize: '12px', color: '#6a9fcf', marginTop: '4px' }}>基于Sentence-BERT模型计算异常描述与工具库的语义相似度，为每一步诊断选择最匹配的工具</div>
        </div>
      </div>

      {stats && (
        <div style={{ 
          marginBottom: '16px', 
          padding: '12px', 
          backgroundColor: '#252525', 
          borderRadius: '8px', 
          border: '1px solid #333' 
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
              <div>
                <span style={{ color: '#8c8c8c' }}>总步骤数:</span>
                <span style={{ marginLeft: '8px', color: '#91d5ff', fontWeight: 'bold' }}>{stats.totalSteps}</span>
              </div>
              <div>
                <span style={{ color: '#8c8c8c' }}>平均匹配分数:</span>
                <Tooltip title={`Sentence-BERT平均分数: ${stats.avgScore.toFixed(4)}`}>
                  <span style={{ marginLeft: '8px', color: '#91d5ff', fontWeight: 'bold' }}>
                    {(stats.avgScore * 100).toFixed(2)}%
                  </span>
                </Tooltip>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <Tag color="#52c41a" style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>高相关: {stats.highConfidence}</Tag>
              <Tag color="#faad14" style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>中相关: {stats.mediumConfidence}</Tag>
              <Tag color="#ff4d4f" style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>低相关: {stats.lowConfidence}</Tag>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'row', gap: '16px', overflowX: 'auto', paddingBottom: '8px' }}>
        {data.map((item, index) => {
          const scorePercent = Math.round(item.sentence_bert_score * 100);
          const confidenceLevel = getConfidenceLevel(item.sentence_bert_score);
          const confidenceColor = getConfidenceColor(item.sentence_bert_score);
          
          return (
            <Card 
              key={index}
              size="small" 
              style={{ 
                minWidth: '280px',
                maxWidth: '340px',
                flex: '0 0 auto',
                borderLeft: `4px solid ${confidenceColor}`,
                backgroundColor: '#252525',
                border: '1px solid #333'
              }}
              headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333' }}
              bodyStyle={{ backgroundColor: '#252525' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div>
                  <Tag color="#1890ff" style={{ fontSize: '11px' }}>
                    步骤 {item.step}
                  </Tag>
                  <Tag color={confidenceColor} style={{ fontSize: '11px', marginLeft: '4px' }}>
                    {confidenceLevel}
                  </Tag>
                </div>
                <Tooltip title={`Sentence-BERT分数: ${item.sentence_bert_score.toFixed(4)}`}>
                  <Progress 
                    type="circle" 
                    percent={scorePercent} 
                    size={28} 
                    strokeColor={getScoreColor(item.sentence_bert_score)}
                    format={() => `${scorePercent}%`}
                  />
                </Tooltip>
              </div>
              
              <Descriptions size="small" column={1} labelStyle={{ color: '#8c8c8c', fontSize: '12px' }}>
                <Descriptions.Item label="匹配动作">
                  <div style={{ 
                    backgroundColor: '#2d2d2d', 
                    padding: '6px', 
                    borderRadius: '4px',
                    fontSize: '12px',
                    color: '#e6e6e6',
                    border: '1px solid #444'
                  }}>
                    <ToolOutlined style={{ color: '#1890ff', marginRight: '4px' }} />
                    {item.action}
                  </div>
                </Descriptions.Item>
                
                <Descriptions.Item label="匹配工具">
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {item.matched_tools?.slice(0, 3).map((tool, idx) => (
                      <Tag 
                        key={idx} 
                        color="blue" 
                        style={{ fontSize: '10px', marginBottom: '2px' }}
                      >
                        {tool}
                      </Tag>
                    ))}
                    {item.matched_tools?.length > 3 && (
                      <Tag style={{ fontSize: '10px' }}>
                        +{item.matched_tools.length - 3}
                      </Tag>
                    )}
                  </div>
                </Descriptions.Item>
                
                <Descriptions.Item label="选择理由">
                  <div style={{ 
                    backgroundColor: '#1a2a3a', 
                    padding: '8px', 
                    borderRadius: '4px',
                    fontSize: '12px',
                    color: '#91d5ff',
                    border: '1px solid #2d4a6a',
                    maxHeight: '100px',
                    overflowY: 'auto',
                    wordBreak: 'break-word',
                    lineHeight: '1.4'
                  }}>
                    <CheckCircleOutlined style={{ color: '#52c41a', marginRight: '4px' }} />
                    匹配分数 {scorePercent}% - {item.selection_reason}
                  </div>
                </Descriptions.Item>
              </Descriptions>
              
              <div style={{ marginTop: '8px', fontSize: '10px', color: '#666' }}>
                匹配算法: Sentence-BERT
              </div>
            </Card>
          );
        })}
      </div>

      <div style={{ marginTop: '16px', padding: '12px', backgroundColor: '#252525', borderRadius: '8px', border: '1px solid #333' }}>
        <div style={{ fontSize: '12px', color: '#8c8c8c' }}>
          <strong style={{ color: '#e6e6e6' }}>工具匹配说明:</strong>
          <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px' }}>
            <li>匹配算法: Sentence-BERT语义相似度计算</li>
            <li>工具库: 数据库诊断专用工具集</li>
            <li>置信度: High (&gt;80%), Medium (60-80%), Low (&lt;60%)</li>
          </ul>
        </div>
      </div>

      {stats && (
        <div style={{ marginTop: '16px' }}>
          <h5 style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '8px' }}>置信度分布</h5>
          <div style={{ display: 'flex', height: '24px', borderRadius: '4px', overflow: 'hidden', backgroundColor: '#2d2d2d' }}>
            {stats.highConfidence > 0 && (
              <Tooltip title={`高置信度: ${stats.highConfidence} 步 (${((stats.highConfidence / stats.totalSteps) * 100).toFixed(1)}%)`}>
                <div 
                  style={{ 
                    width: `${(stats.highConfidence / stats.totalSteps) * 100}%`, 
                    backgroundColor: '#52c41a',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'white',
                    fontSize: '11px'
                  }}
                >
                  {stats.highConfidence}
                </div>
              </Tooltip>
            )}
            {stats.mediumConfidence > 0 && (
              <Tooltip title={`中置信度: ${stats.mediumConfidence} 步 (${((stats.mediumConfidence / stats.totalSteps) * 100).toFixed(1)}%)`}>
                <div 
                  style={{ 
                    width: `${(stats.mediumConfidence / stats.totalSteps) * 100}%`, 
                    backgroundColor: '#faad14',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'white',
                    fontSize: '11px'
                  }}
                >
                  {stats.mediumConfidence}
                </div>
              </Tooltip>
            )}
            {stats.lowConfidence > 0 && (
              <Tooltip title={`低置信度: ${stats.lowConfidence} 步 (${((stats.lowConfidence / stats.totalSteps) * 100).toFixed(1)}%)`}>
                <div 
                  style={{ 
                    width: `${(stats.lowConfidence / stats.totalSteps) * 100}%`, 
                    backgroundColor: '#ff4d4f',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'white',
                    fontSize: '11px'
                  }}
                >
                  {stats.lowConfidence}
                </div>
              </Tooltip>
            )}
          </div>
        </div>
      )}
    </Card>
  );
};

// ========== 诊断流程状态枚举 ==========
const DIAGNOSIS_STATUS = {
  IDLE: 'idle',           // 空闲，未开始
  RUNNING: 'running',     // 诊断中
  COMPLETED: 'completed', // 已完成
  FAILED: 'failed',       // 失败
  TIMEOUT: 'timeout'      // 超时
};

// ========== 全局配置 ==========
const CONFIG = {
  DEBOUNCE_TIME: 3000,           // 防抖时间
  POLL_INTERVAL: 2000,           // 进度轮询间隔
  TERMINAL_POLL_INTERVAL: 2000,  // 终端输出轮询间隔
  MAX_DIAGNOSIS_TIME: 600000,    // 最大诊断时间 10分钟
  SUBMIT_TIMEOUT: 30000,         // 提交任务超时时间 30秒
  MAX_POLL_COUNT: 300,           // 最大轮询次数（10分钟/2秒=300次）
};

const Diagnosis = () => {
  // 获取来自监控页面的告警信息
  const location = useLocation();
  const alertInfo = location.state || {};
  
  // 使用全局诊断 Context
  const {
    diagnosing: globalDiagnosing,
    diagnosisProgress: globalProgress,
    diagnosisResult: globalResult,
    terminalOutput: globalTerminal,
    realTimeSteps: globalSteps,
    currentStepIndex: globalStepIndex,
    uploadFile: globalUploadFile,
    diagnosisId: globalDiagnosisId,
    uploadMode: globalUploadMode,
    trcParseResult: globalTrcParseResult,
    trcFaultEvents: globalTrcFaultEvents,
    trcTimeline: globalTrcTimeline,
    trcAEUList: globalTrcAEUList,
    startDiagnosis,
    updateProgress,
    updateTerminal,
    completeDiagnosis,
    failDiagnosis,
    resetDiagnosis,
    setUploadMode,
    setTrcParseResult,
    setTrcFaultEvents,
    setTrcTimeline,
    setTrcAEUList
  } = useDiagnosis();

  const [loading, setLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState('deepseek-chat');
  const [localUploadFile, setLocalUploadFile] = useState(null);
  
  // 防抖相关
  const lastDiagnosisTimeRef = useRef(0);
  
  // ========== 核心状态管理 ==========
  const diagnosisStateRef = useRef({
    status: DIAGNOSIS_STATUS.IDLE,
    diagnosisId: null,
    startTime: null,
    isPolling: false
  });
  
  // 轮询定时器引用
  const pollingTimersRef = useRef({
    progressTimer: null,
    terminalTimer: null,
    timeoutTimer: null
  });
  
  // 组件挂载状态引用
  const isMountedRef = useRef(true);
  
  // 终端输出引用
  const terminalOutputRef = useRef(globalTerminal);

  // 创建别名变量
  const diagnosing = globalDiagnosing;
  const diagnosisProgress = globalProgress;
  const diagnosisResult = globalResult;
  const terminalOutput = globalTerminal;
  const realTimeSteps = globalSteps;
  const currentStepIndex = globalStepIndex;
  const uploadMode = globalUploadMode;

  // 同步终端输出引用
  useEffect(() => {
    terminalOutputRef.current = globalTerminal;
  }, [globalTerminal]);

  // ========== 统一清理所有轮询定时器 ==========
  const clearAllTimers = useCallback(() => {
    const timers = pollingTimersRef.current;
    
    if (timers.progressTimer) {
      clearInterval(timers.progressTimer);
      timers.progressTimer = null;
      console.log('[TIMER] 进度轮询已停止');
    }
    
    if (timers.terminalTimer) {
      clearInterval(timers.terminalTimer);
      timers.terminalTimer = null;
      console.log('[TIMER] 终端轮询已停止');
    }
    
    if (timers.timeoutTimer) {
      clearTimeout(timers.timeoutTimer);
      timers.timeoutTimer = null;
      console.log('[TIMER] 超时定时器已清除');
    }
    
    diagnosisStateRef.current.isPolling = false;
    console.log('[TIMER] 所有定时器已清理');
  }, []);

  // ========== 终态处理函数 ==========
  const handleDiagnosisComplete = useCallback(async (source = 'unknown') => {
    console.log(`[COMPLETE] 诊断完成，来源: ${source}`);
    
    // 1. 立即停止所有轮询（防止重复触发）
    clearAllTimers();
    
    // 2. 更新 ref 状态
    diagnosisStateRef.current.status = DIAGNOSIS_STATUS.COMPLETED;
    diagnosisStateRef.current.isPolling = false;
    
    // 3. 获取最终结果
    try {
      console.log('[COMPLETE] 正在获取最终诊断结果...');
      const result = await diagnoseAPI.getResult();
      console.log('[COMPLETE] 获取到的结果:', result ? '有数据' : '无数据');
      
      if (result) {
        // 强制更新状态，不检查 isMountedRef
        completeDiagnosis(result);
        message.success('诊断完成');
        
        // 通知 Reports 页面刷新
        window.dispatchEvent(new CustomEvent('diagnosis-completed', {
          detail: {
            anomaly_type: result.anomaly_type || 'unknown',
            root_cause: result.root_causes?.[0]?.type || 'unknown',
            diagnosis_time: result.diagnosis_time
          }
        }));
      } else {
        message.warning('诊断完成但未能获取结果');
        failDiagnosis();
      }
    } catch (error) {
      console.error('[COMPLETE] 获取结果失败:', error);
      message.error('获取诊断结果失败');
      failDiagnosis();
    }
  }, [clearAllTimers, completeDiagnosis, failDiagnosis]);

  // ========== 失败处理函数 ==========
  const handleDiagnosisFailed = useCallback((error, source = 'unknown') => {
    console.log(`[FAILED] 诊断失败，来源: ${source}, 错误: ${error?.message || error}`);
    
    clearAllTimers();
    diagnosisStateRef.current.status = DIAGNOSIS_STATUS.FAILED;
    diagnosisStateRef.current.isPolling = false;
    
    failDiagnosis();
    
    const errorMsg = error?.message || '诊断失败，请重试';
    message.error(errorMsg);
  }, [clearAllTimers, failDiagnosis]);

  // ========== 超时处理函数 ==========
  const handleDiagnosisTimeout = useCallback(() => {
    console.log('[TIMEOUT] 诊断超时（10分钟）');
    
    clearAllTimers();
    diagnosisStateRef.current.status = DIAGNOSIS_STATUS.TIMEOUT;
    diagnosisStateRef.current.isPolling = false;
    
    failDiagnosis();
    message.warning('诊断超时（10分钟），请检查后端服务状态');
  }, [clearAllTimers, failDiagnosis]);

  // ========== 启动轮询（核心逻辑） ==========
  const startPolling = useCallback((diagnosisId) => {
    if (diagnosisStateRef.current.isPolling) {
      console.log('[POLL] 轮询已在运行中，跳过');
      return;
    }
    
    diagnosisStateRef.current.isPolling = true;
    console.log('[POLL] 启动轮询，诊断ID:', diagnosisId);
    
    let lastStepCount = 0;
    let lastCurrentStep = 0;
    let lastIsCompleted = false;
    let pollCount = 0;
    let isPollingStopped = false;  // 新增：轮询停止标志
    
    // 辅助函数：安全停止轮询
    const stopPollingSafely = () => {
      if (!isPollingStopped) {
        isPollingStopped = true;
        console.log('[POLL] 轮询已标记为停止');
      }
    };
    
    // 进度轮询（核心：检测终态）
    pollingTimersRef.current.progressTimer = setInterval(async () => {
      // 检查轮询是否已停止
      if (isPollingStopped) {
        console.log('[POLL] 轮询已停止，跳过本次执行');
        return;
      }
      
      if (!isMountedRef.current) {
        clearAllTimers();
        return;
      }
      
      pollCount++;
      
      // ========== 最大轮询次数检查 ==========
      if (pollCount > CONFIG.MAX_POLL_COUNT) {
        console.log(`[POLL] 超过最大轮询次数 ${CONFIG.MAX_POLL_COUNT}，强制停止`);
        stopPollingSafely();
        message.warning('诊断轮询超时，强制获取结果');
        handleDiagnosisComplete('polling_timeout');
        return;
      }
      
      try {
        const progressData = await diagnoseAPI.getProgress();
        
        // ========== 调试日志：打印每次轮询返回的数据 ==========
        if (pollCount <= 5 || pollCount % 10 === 0) {
          console.log(`[POLL] 第 ${pollCount} 次轮询返回:`, JSON.stringify(progressData, null, 2));
        }
        
        if (!isMountedRef.current || !progressData) {
          console.log(`[POLL] 第 ${pollCount} 次轮询跳过: isMounted=${isMountedRef.current}, data=${!!progressData}`);
          return;
        }
        
        // 更新进度
        const newStepCount = progressData.steps?.length || 0;
        const newCurrentStep = progressData.current_step || 0;
        
        if (newStepCount !== lastStepCount || newCurrentStep !== lastCurrentStep) {
          lastStepCount = newStepCount;
          lastCurrentStep = newCurrentStep;
          updateProgress(
            Math.round((newCurrentStep / (progressData.total_steps || 10)) * 100),
            progressData.steps || [],
            newCurrentStep
          );
        }
        
        // ========== 终态判断（核心逻辑） ==========
        const isCompleted = progressData.is_completed === true || 
                           progressData.status === 'completed';
        
        // ========== 调试日志：打印终态判断 ==========
        console.log(`[POLL] 第 ${pollCount} 次轮询终态判断:`, {
          is_completed: progressData.is_completed,
          status: progressData.status,
          isCompleted: isCompleted,
          lastIsCompleted: lastIsCompleted,
          isPollingStopped: isPollingStopped
        });
        
        if (isCompleted && !lastIsCompleted && !isPollingStopped) {
          lastIsCompleted = true;
          stopPollingSafely();  // 立即标记停止
          console.log(`[POLL] ✅ 第 ${pollCount} 次轮询检测到诊断完成信号`);
          console.log('[POLL] is_completed:', progressData.is_completed);
          console.log('[POLL] status:', progressData.status);
          
          // 立即停止轮询并处理完成
          handleDiagnosisComplete('polling');
        }
        
      } catch (error) {
        console.error(`[POLL] 第 ${pollCount} 次轮询失败:`, error.message);
        // 不中断轮询，继续尝试
      }
    }, CONFIG.POLL_INTERVAL);
    
    // 终端输出轮询
    pollingTimersRef.current.terminalTimer = setInterval(async () => {
      if (!isMountedRef.current) return;
      
      try {
        const outputData = await diagnoseAPI.getTerminalOutput();
        if (outputData?.output && isMountedRef.current) {
          updateTerminal(outputData.output);
        }
      } catch (error) {
        console.error('[POLL] 获取终端输出失败:', error.message);
      }
    }, CONFIG.TERMINAL_POLL_INTERVAL);
    
    // 超时定时器（10分钟兜底）
    pollingTimersRef.current.timeoutTimer = setTimeout(() => {
      if (diagnosisStateRef.current.status === DIAGNOSIS_STATUS.RUNNING) {
        handleDiagnosisTimeout();
      }
    }, CONFIG.MAX_DIAGNOSIS_TIME);
    
  }, [clearAllTimers, updateProgress, updateTerminal, handleDiagnosisComplete, handleDiagnosisTimeout]);

  // ========== 组件卸载时清理 ==========
  useEffect(() => {
    isMountedRef.current = true;
    
    return () => {
      console.log('[CLEANUP] 组件卸载，清理资源');
      isMountedRef.current = false;
      // 只有在诊断还在运行时才清理状态
      if (diagnosisStateRef.current.status === DIAGNOSIS_STATUS.RUNNING) {
        clearAllTimers();
        diagnosisStateRef.current.status = DIAGNOSIS_STATUS.IDLE;
        diagnosisStateRef.current.isPolling = false;
      }
    };
  }, [clearAllTimers]);

  // ========== 读取文件内容 ==========
  const readFileContent = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.onerror = reject;
      reader.readAsText(file);
    });
  };

  // ========== 上传文件处理 ==========
  const handleUpload = (file) => {
    console.log('[UPLOAD] 文件选择:', file.name);
    setLocalUploadFile(file);
    
    const fileName = file.name.toLowerCase();
    
    // 检查是否是 macOS 系统文件 (._开头)
    if (fileName.startsWith('._')) {
      message.warning(`检测到系统文件: ${file.name}，已忽略`);
      return false;
    }
    
    // 先设置 uploadMode，再重置其他状态
    if (fileName.endsWith('.trc')) {
      console.log('[UPLOAD] 检测到 TRC 文件，设置 uploadMode 为 trc_single');
      message.info(`检测到 SunDB 日志文件: ${file.name}，将进行 TRC 解析`);
      setUploadMode('trc_single');
    } else if (fileName.endsWith('.tar.gz') || fileName.endsWith('.tgz')) {
      console.log('[UPLOAD] 检测到 TAR.GZ 文件，设置 uploadMode 为 trc_batch');
      message.info(`检测到 TRC 压缩包: ${file.name}，将进行批量解析`);
      setUploadMode('trc_batch');
    } else {
      console.log('[UPLOAD] 检测到 JSON 文件，设置 uploadMode 为 json');
      setUploadMode('json');
    }

    // 重置诊断状态（但保留 uploadMode）
    resetDiagnosis();

    message.success(`已选择文件: ${file.name}`);
    return false;
  };

  // ========== TRC 文件上传处理 ==========
  const handleTrcUpload = async (file, mode) => {
    setLoading(true);
    message.loading({ content: '正在解析 TRC 文件...', key: 'trc_parse' });

    try {
      let result;
      
      if (mode === 'trc_single') {
        result = await sundbTrcAPI.uploadTrc(file);
      } else if (mode === 'trc_batch') {
        result = await sundbTrcAPI.uploadTrcDirectory(file);
      } else {
        throw new Error(`无法识别的文件类型: ${file.name}`);
      }

      console.log('[TRC] 解析结果:', result);

      const trcData = result;
      
      console.log('[TRC] trcData:', trcData);
      console.log('[TRC] fault_summary:', trcData?.fault_summary);
      console.log('[TRC] aeu_list:', trcData?.aeu_list);
      console.log('[TRC] entries:', trcData?.entries);
      
      if (trcData) {
        const { fault_summary, aeu_list, entries, timeline_range, files_parsed } = trcData;
        
        console.log('[TRC] 调用 setTrcParseResult...');
        setTrcParseResult(trcData, aeu_list || [], entries || [], aeu_list || []);
        
        console.log('[TRC] setTrcParseResult 调用完成');
        
        if (aeu_list) {
          setTrcAEUList(aeu_list);
        }
        
        if (entries) {
          setTrcTimeline(entries);
        }
        
        const faultCount = trcData.fault_count || fault_summary?.total || 0;
        if (faultCount > 0) {
          message.success(`TRC 解析完成，发现 ${faultCount} 个故障事件`);
        } else {
          message.success('TRC 解析完成，未发现故障事件');
        }

        window.dispatchEvent(new CustomEvent('trc-parse-completed', {
          detail: {
            fault_count: faultCount,
            timeline_range,
            files_parsed
          }
        }));

        if (faultCount > 0 || (trcData.entries_by_level && Object.keys(trcData.entries_by_level).length > 0)) {
          message.loading({ content: '正在进行智能诊断...', key: 'trc_diagnose' });
          
          try {
            const diagnosisResult = await sundbTrcAPI.trcDiagnose({
              filename: trcData.filename,
              parser_type: trcData.parser_type,
              fault_count: faultCount,
              entries: trcData.entries || [],
              entries_by_level: trcData.entries_by_level || {}
            });
            
            console.log('[TRC] 诊断结果:', diagnosisResult);
            
            if (diagnosisResult) {
              completeDiagnosis(diagnosisResult);
              message.success({ content: '智能诊断完成', key: 'trc_diagnose' });
            }
          } catch (diagError) {
            console.error('[TRC] 智能诊断失败:', diagError);
            message.warning({ content: `智能诊断失败: ${diagError.message || '未知错误'}`, key: 'trc_diagnose' });
          }
        }
      }
    } catch (error) {
      console.error('[TRC] 解析失败:', error);
      message.error(`TRC 解析失败: ${error.message || '未知错误'}`);
    } finally {
      setLoading(false);
      message.destroy('trc_parse');
    }
  };

  // ========== 开始诊断（核心流程） ==========
  const handleStartDiagnosis = async () => {
    // 1. 防重复检查
    if (diagnosisStateRef.current.status === DIAGNOSIS_STATUS.RUNNING) {
      message.warning('诊断正在进行中，请等待完成');
      return;
    }
    
    if (diagnosing) {
      message.warning('诊断正在进行中，请等待完成');
      return;
    }
    
    // 2. 防抖检查
    const now = Date.now();
    if (now - lastDiagnosisTimeRef.current < CONFIG.DEBOUNCE_TIME) {
      message.warning('请稍后再试');
      return;
    }
    
    // 3. 检查是否有上传文件
    if (!localUploadFile) {
      message.warning('请先上传文件后再开始诊断');
      return;
    }
    
    // 3.5 检查是否是 TRC 文件，走 TRC 解析流程
    if (uploadMode === 'trc_single' || uploadMode === 'trc_batch') {
      console.log('[DIAGNOSIS] 检测到 TRC 文件，启动 TRC 解析流程');
      await handleTrcUpload(localUploadFile, uploadMode);
      return;
    }
    
    // 4. 检查后端是否有任务在运行
    try {
      const statusRes = await diagnoseAPI.getProgress();
      if (statusRes?.is_running) {
        message.warning('后端诊断任务正在运行中，请等待完成后再试');
        return;
      }
    } catch (e) {
      console.log('检查诊断状态失败:', e);
    }
    
    // 5. 初始化诊断状态
    const diagnosisId = `diag_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    diagnosisStateRef.current = {
      status: DIAGNOSIS_STATUS.RUNNING,
      diagnosisId: diagnosisId,
      startTime: Date.now(),
      isPolling: false
    };
    lastDiagnosisTimeRef.current = now;
    
    // 6. 更新 Context 状态
    startDiagnosis(diagnosisId, localUploadFile);
    
    // 7. 清理之前的定时器
    clearAllTimers();
    
    // 8. 准备异常信息
    let anomalyInfo = {
      alert_type: alertInfo.alertType || 'CPU High',
      description: alertInfo.alertMessage || '数据库性能异常',
      severity: alertInfo.alertLevel || 'high',
      timestamp: alertInfo.alertTime || new Date().toISOString(),
      source: 'monitoring_alert'  // 标记来源为监控告警
    };
    
    console.log('[DIAGNOSIS] 告警信息:', alertInfo);
    console.log('[DIAGNOSIS] 构建的异常信息:', anomalyInfo);
    
    try {
      if (localUploadFile) {
        const fileContent = await readFileContent(localUploadFile);
        if (fileContent) {
          try {
            const parsed = JSON.parse(fileContent);
            anomalyInfo = { ...anomalyInfo, ...parsed };
          } catch (parseError) {
            const dynamicInfo = buildAnomalyInfo(fileContent);
            anomalyInfo = { ...anomalyInfo, ...dynamicInfo };
            console.log('[DIAGNOSIS] 动态解析文件内容:', dynamicInfo);
          }
        }
      }
    } catch (e) {
      console.log('解析数据失败，使用默认异常信息');
    }
    
    // ========== 核心流程改变 ==========
    // 9. 先启动轮询（不等待主请求）
    console.log('[DIAGNOSIS] 启动轮询...');
    startPolling(diagnosisId);
    
    // 10. 提交诊断任务（不等待完成）
    console.log('[DIAGNOSIS] 提交诊断任务...');
    
    try {
      const submitResult = await diagnoseAPI.submitDiagnosis(anomalyInfo, {
        timeout: CONFIG.SUBMIT_TIMEOUT
      });
      
      console.log('[DIAGNOSIS] 提交结果:', submitResult);
      
      // ========== 错误分类处理 ==========
      // 可忽略的错误：CanceledError、canceled、NS_BINDING_ABORTED、超时
      // 这些错误不应该停止轮询，让轮询继续接管
      
      if (submitResult.success) {
        // 检查是否是 HTTP 202（自动任务正在运行）
        if (submitResult.data?.status === 'auto_running') {
          console.log('[DIAGNOSIS] 检测到自动巡检任务正在运行');
          // 停止当前轮询
          clearAllTimers();
          diagnosisStateRef.current.status = DIAGNOSIS_STATUS.IDLE;
          // 显示 Modal 让用户选择
          handleAutoTaskConflict(submitResult.data.auto_task, anomalyInfo);
          return;
        }
        
        if (submitResult.data) {
          console.log('[DIAGNOSIS] 后端立即返回了结果');
          // 不在这里处理，让轮询来处理
        } else if (submitResult.isTimeout) {
          console.log('[DIAGNOSIS] 主请求超时，继续通过轮询获取状态');
        } else {
          console.log('[DIAGNOSIS] 任务已提交，等待轮询检测完成');
        }
      } else {
        // 检查是否是可忽略的错误
        const isIgnorableError = 
          submitResult.message?.toLowerCase().includes('canceled') ||
          submitResult.message?.toLowerCase().includes('abort') ||
          submitResult.isTimeout ||
          submitResult.error?.name === 'CanceledError' ||
          submitResult.error?.code === 'ERR_CANCELED';
        
        if (isIgnorableError) {
          console.log('[DIAGNOSIS] 主请求被取消/中止，但轮询继续运行，等待后端状态');
          console.log('[DIAGNOSIS] 忽略错误:', submitResult.message);
        } else if (submitResult.isRunning) {
          // 同类任务正在运行
          const taskTypeDisplay = submitResult.taskType === 'auto' ? '自动巡检' : '手动诊断';
          message.warning(`${taskTypeDisplay}任务正在运行中，请等待完成后再试`);
          handleDiagnosisFailed(new Error(submitResult.message), 'submit');
        } else {
          // 致命错误：后端明确返回失败，才停止轮询
          console.error('[DIAGNOSIS] 提交失败（致命错误）:', submitResult.message);
          handleDiagnosisFailed(new Error(submitResult.message), 'submit');
        }
      }
      
    } catch (error) {
      console.error('[DIAGNOSIS] 提交异常:', error);
      
      // ========== 异常分类处理 ==========
      // 检查是否是可忽略的异常
      const isIgnorableException = 
        error?.name === 'CanceledError' ||
        error?.code === 'ERR_CANCELED' ||
        error?.message?.toLowerCase().includes('canceled') ||
        error?.message?.toLowerCase().includes('abort');
      
      if (isIgnorableException) {
        // 可忽略异常：不停止轮询，不提示失败
        console.log('[DIAGNOSIS] 主请求异常（可忽略），轮询继续运行');
        console.log('[DIAGNOSIS] 忽略异常:', error?.message || error);
      } else {
        // 致命异常：给轮询一些时间检测状态，如果轮询检测不到完成才报错
        console.log('[DIAGNOSIS] 主请求异常（非取消），等待轮询检测状态...');
        setTimeout(() => {
          if (diagnosisStateRef.current.status === DIAGNOSIS_STATUS.RUNNING) {
            console.log('[DIAGNOSIS] 轮询仍在运行，继续等待后端状态');
          }
        }, 5000);
      }
    }
  };

  // ========== 停止诊断 ==========
  const handleStopDiagnosis = useCallback(() => {
    console.log('[STOP] 用户主动停止诊断');
    clearAllTimers();
    diagnosisStateRef.current.status = DIAGNOSIS_STATUS.IDLE;
    diagnosisStateRef.current.isPolling = false;
    failDiagnosis();
    message.info('诊断已停止');
  }, [clearAllTimers, failDiagnosis]);

  // ========== 清除诊断状态 ==========
  const clearDiagnosisState = () => {
    resetDiagnosis();
    setLocalUploadFile(null);
    message.success('已清除诊断状态');
  };

  // ========== 自动任务冲突处理 ==========
  const [autoTaskModalVisible, setAutoTaskModalVisible] = useState(false);
  const [autoTaskInfo, setAutoTaskInfo] = useState(null);
  const [pendingDiagnosis, setPendingDiagnosis] = useState(null);

  // 处理自动任务冲突：显示 Modal 让用户选择
  const handleAutoTaskConflict = (autoStatus, anomalyInfo) => {
    setAutoTaskInfo(autoStatus);
    setPendingDiagnosis(anomalyInfo);
    setAutoTaskModalVisible(true);
  };

  // 用户选择取消自动任务并开始手动诊断
  const handleCancelAutoAndStart = async () => {
    setAutoTaskModalVisible(false);
    message.loading('正在取消自动巡检任务...');
    
    try {
      const cancelResult = await diagnoseAPI.cancelAutoTask('user_request');
      if (cancelResult?.success) {
        message.success('已发送取消请求，等待任务停止...');
        
        // 轮询等待自动任务停止
        let retries = 0;
        const maxRetries = 30;
        const checkInterval = setInterval(async () => {
          const status = await diagnoseAPI.checkAutoTaskStatus();
          if (!status?.auto_running || retries >= maxRetries) {
            clearInterval(checkInterval);
            message.success('自动任务已停止，开始手动诊断...');
            // 开始手动诊断
            if (pendingDiagnosis) {
              submitDiagnosisTask(pendingDiagnosis);
            }
          }
          retries++;
        }, 1000);
      }
    } catch (error) {
      message.error('取消自动任务失败: ' + error.message);
    }
  };

  // 用户选择等待自动任务完成
  const handleWaitAutoTask = () => {
    setAutoTaskModalVisible(false);
    message.info('等待自动巡检任务完成...');
    
    // 轮询等待自动任务完成
    const checkInterval = setInterval(async () => {
      const status = await diagnoseAPI.checkAutoTaskStatus();
      if (!status?.auto_running) {
        clearInterval(checkInterval);
        message.success('自动任务已完成，开始手动诊断...');
        if (pendingDiagnosis) {
          submitDiagnosisTask(pendingDiagnosis);
        }
      }
    }, 2000);
  };

  // 实际提交诊断任务
  const submitDiagnosisTask = async (anomalyInfo) => {
    const diagnosisId = `diag_manual_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    diagnosisStateRef.current = {
      status: DIAGNOSIS_STATUS.RUNNING,
      diagnosisId: diagnosisId,
      startTime: Date.now(),
      isPolling: false
    };
    lastDiagnosisTimeRef.current = Date.now();
    
    startDiagnosis(diagnosisId, localUploadFile);
    clearAllTimers();
    
    console.log('[DIAGNOSIS] 启动轮询...');
    startPolling(diagnosisId);
    
    console.log('[DIAGNOSIS] 提交诊断任务...');
    
    try {
      const submitResult = await diagnoseAPI.submitDiagnosis(anomalyInfo, {
        timeout: CONFIG.SUBMIT_TIMEOUT
      });
      
      console.log('[DIAGNOSIS] 提交结果:', submitResult);
      
      if (submitResult.success) {
        if (submitResult.data) {
          console.log('[DIAGNOSIS] 后端立即返回了结果');
        } else if (submitResult.isTimeout) {
          console.log('[DIAGNOSIS] 主请求超时，继续通过轮询获取状态');
        } else {
          console.log('[DIAGNOSIS] 任务已提交，等待轮询检测完成');
        }
      } else {
        const isIgnorableError = 
          submitResult.message?.toLowerCase().includes('canceled') ||
          submitResult.message?.toLowerCase().includes('abort') ||
          submitResult.isTimeout ||
          submitResult.error?.name === 'CanceledError' ||
          submitResult.error?.code === 'ERR_CANCELED';
        
        if (isIgnorableError) {
          console.log('[DIAGNOSIS] 主请求被取消/中止，但轮询继续运行，等待后端状态');
        } else if (submitResult.isRunning) {
          const taskTypeDisplay = submitResult.taskType === 'auto' ? '自动巡检' : '手动诊断';
          message.warning(`${taskTypeDisplay}任务正在运行中，请等待完成后再试`);
          handleDiagnosisFailed(new Error(submitResult.message), 'submit');
        } else {
          console.error('[DIAGNOSIS] 提交失败（致命错误）:', submitResult.message);
          handleDiagnosisFailed(new Error(submitResult.message), 'submit');
        }
      }
    } catch (error) {
      console.error('[DIAGNOSIS] 提交异常:', error);
      
      const isIgnorableException = 
        error?.name === 'CanceledError' ||
        error?.code === 'ERR_CANCELED' ||
        error?.message?.toLowerCase().includes('canceled') ||
        error?.message?.toLowerCase().includes('abort');
      
      if (isIgnorableException) {
        console.log('[DIAGNOSIS] 主请求异常（可忽略），轮询继续运行');
      } else {
        console.log('[DIAGNOSIS] 主请求异常（非取消），等待轮询检测状态...');
        setTimeout(() => {
          if (diagnosisStateRef.current.status === DIAGNOSIS_STATUS.RUNNING) {
            console.log('[DIAGNOSIS] 轮询仍在运行，继续等待后端状态');
          }
        }, 5000);
      }
    }
  };

  // ========== 重置所有诊断状态（管理员功能） ==========
  const handleResetAllStatus = async () => {
    try {
      const result = await diagnoseAPI.resetStatus();
      if (result) {
        message.success('已重置所有诊断状态');
        resetDiagnosis();
      }
    } catch (error) {
      message.error('重置失败: ' + error.message);
    }
  };

  const modelList = [
    { value: 'deepseek-chat', label: 'DeepSeek-V3' },
    { value: 'deepseek-reasoner', label: 'DeepSeek-R1' }
  ];

  // ========== 翻译相关 ==========
  const [translationCache, setTranslationCache] = useState({});
  const [translatingTexts, setTranslatingTexts] = useState(new Set());

  const translateText = async (text) => {
    if (!text || typeof text !== 'string') return text;
    if (translationCache[text]) return translationCache[text];
    if (translatingTexts.has(text)) return text;
    
    if (!/[\u4e00-\u9fa5]/.test(text)) {
      setTranslatingTexts(prev => new Set([...prev, text]));
      try {
        const translated = await translateAPI.translateText(text, 'zh');
        setTranslationCache(prev => ({ ...prev, [text]: translated }));
        return translated;
      } catch (error) {
        return text;
      } finally {
        setTranslatingTexts(prev => {
          const newSet = new Set(prev);
          newSet.delete(text);
          return newSet;
        });
      }
    }
    return text;
  };

  const TranslatableText = ({ text, style }) => {
    const [translated, setTranslated] = useState(translationCache[text] || text);
    const [isTranslating, setIsTranslating] = useState(false);
    
    useEffect(() => {
      if (translationCache[text]) {
        setTranslated(translationCache[text]);
        return;
      }
      if (!/[\u4e00-\u9fa5]/.test(text) && text.length > 10) {
        setIsTranslating(true);
        translateText(text).then(result => {
          setTranslated(result);
          setIsTranslating(false);
        });
      }
    }, [text]);
    
    if (isTranslating) {
      return (
        <span style={style}>
          <LoadingOutlined style={{ marginRight: '6px' }} spin />
          正在翻译...
        </span>
      );
    }
    return <span style={style}>{translated}</span>;
  };

  return (
    <div className="diagnosis-page" style={{ padding: '24px' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', marginBottom: '8px' }}>
          <BugOutlined /> 数据库智能诊断
        </h1>
        <p style={{ color: '#8c8c8c' }}>
          基于 D-Bot 论文的 Tree Search 算法，自动分析数据库异常根因
        </p>
      </div>

      <Row gutter={[24, 24]}>
        {/* 左侧：诊断配置 */}
        <Col xs={24} lg={8}>
          <Card title="诊断配置" bordered={false}>
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '8px' }}>选择 LLM 模型</label>
              <Select
                value={selectedModel}
                onChange={setSelectedModel}
                style={{ width: '100%' }}
              >
                {modelList.map(model => (
                  <Option key={model.value} value={model.value}>{model.label}</Option>
                ))}
              </Select>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '8px' }}>上传文件</label>
              <Upload
                beforeUpload={handleUpload}
                accept=".json,.yaml,.yml,.trc,.tar.gz,.tgz"
                maxCount={1}
              >
                <Button icon={<UploadOutlined />}>选择文件</Button>
              </Upload>
              {localUploadFile && (
                <div style={{ marginTop: '8px' }}>
                  <Tag color="blue" style={{ marginRight: '4px' }}>
                    <FileTextOutlined /> {localUploadFile.name}
                  </Tag>
                  {(uploadMode === 'trc_single' || uploadMode === 'trc_batch') && (
                    <Tag color="orange">SunDB TRC 模式</Tag>
                  )}
                </div>
              )}
            </div>

            <Divider style={{ margin: '12px 0' }} />

            <Button
              type="primary"
              icon={diagnosing ? <LoadingOutlined /> : <PlayCircleOutlined />}
              onClick={handleStartDiagnosis}
              disabled={diagnosing}
              block
              size="large"
            >
              {diagnosing ? '诊断进行中...' : '开始诊断'}
            </Button>

            {diagnosing && (
              <>
                <div style={{ marginTop: '16px' }}>
                  <Progress percent={diagnosisProgress} status="active" />
                </div>
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={handleStopDiagnosis}
                  block
                  style={{ marginTop: '12px' }}
                >
                  停止诊断
                </Button>
              </>
            )}
            
            {/* 重置状态按钮（管理员功能） */}
            <Button
              type="dashed"
              icon={<ReloadOutlined />}
              onClick={handleResetAllStatus}
              block
              style={{ marginTop: '12px' }}
              title="用于异常情况下重置诊断状态"
            >
              重置诊断状态
            </Button>
          </Card>


        </Col>

        {/* 右侧：诊断结果 */}
        <Col xs={24} lg={16}>
          {/* 诊断过程中或诊断完成后显示实时进度拓扑图 */}
          {(diagnosing || realTimeSteps.length > 0) && (
            <Card 
              title={
                <span style={{ color: '#1890ff' }}>
                  {diagnosing ? (
                    <><SyncOutlined spin style={{ marginRight: '8px' }} />实时诊断进度</>
                  ) : (
                    <><CheckCircleOutlined style={{ marginRight: '8px', color: '#52c41a' }} />诊断过程</>
                  )}
                </span>
              }
              bordered={false}
              style={{ marginBottom: '16px', backgroundColor: '#1e1e1e', border: '1px solid #1890ff' }}
            >
              <DiagnosisProgressGraph 
                isDiagnosing={diagnosing}
                steps={realTimeSteps}
                currentStep={currentStepIndex}
                height={400}
              />
            </Card>
          )}

          {/* DeepSeek 思考流终端 - 已隐藏 */}
          {/* (diagnosing || terminalOutput) && (
            <Card
              title={
                <span style={{ color: '#58a6ff' }}>
                  <BulbOutlined style={{ marginRight: '8px' }} />
                  DeepSeek 思考流
                </span>
              }
              bordered={false}
              style={{ marginBottom: '16px', backgroundColor: '#1e1e1e', border: '1px solid #30363d' }}
              styles={{ body: { padding: 0 } }}
            >
              <ThinkingTerminal
                output={terminalOutput}
                isRunning={diagnosing}
                height={250}
                maxHeight={500}
                showControls={true}
                title="实时推理输出"
              />
            </Card>
          ) */}

          <Spin spinning={diagnosing} tip="正在进行 Tree Search 诊断...">
            {/* TRC 解析结果展示 */}
            {(() => {
              console.log('[TRC RENDER] globalTrcParseResult:', globalTrcParseResult);
              console.log('[TRC RENDER] uploadMode:', uploadMode);
              console.log('[TRC RENDER] 显示条件:', globalTrcParseResult && (uploadMode === 'trc_single' || uploadMode === 'trc_batch'));
              return null;
            })()}
            
            {/* TRC 解析结果 - 图表、故障面板、时间线 */}
            {globalTrcParseResult && (uploadMode === 'trc_single' || uploadMode === 'trc_batch') && (
              <>
                {/* TRC 故障统计图表 */}
                <TrcFaultSummaryChart 
                  faultSummary={{
                    total: globalTrcParseResult.fault_count || 0,
                    by_type: globalTrcParseResult.entries_by_level || {},
                    by_severity: globalTrcParseResult.entries_by_level || {},
                    by_instance: {}
                  }}
                  style={{ marginBottom: '16px' }}
                />
                
                {/* TRC 故障事件面板 */}
                <TrcFaultPanel 
                  faults={globalTrcParseResult.entries || []}
                  loading={loading}
                  style={{ marginBottom: '16px' }}
                />
                
                {/* TRC 时间线面板 */}
                {globalTrcParseResult.entries && globalTrcParseResult.entries.length > 0 && (
                  <TrcTimelinePanel 
                    entries={globalTrcParseResult.entries}
                    loading={loading}
                    maxHeight="500px"
                    style={{ marginBottom: '16px' }}
                  />
                )}
              </>
            )}
            
            {/* 智能诊断结果 */}
            {diagnosisResult ? (
              <>
                {/* 根因分析结果 */}
                <Card 
                  title={
                    <span style={{ color: '#e6e6e6' }}>
                      <CheckCircleOutlined style={{ color: '#52c41a', marginRight: '8px' }} />
                      诊断结果
                    </span>
                  }
                  bordered={false}
                  style={{ marginBottom: '16px', backgroundColor: '#1e1e1e', border: '1px solid #333' }}
                >
                  <Alert
                    message="根因识别成功"
                    description={`检测到 ${diagnosisResult.root_causes?.length || 0} 个潜在根因`}
                    type="success"
                    showIcon
                    style={{ marginBottom: '16px' }}
                  />

                  {diagnosisResult.root_causes?.map((cause, index) => {
                    const cnCauseType = ROOT_CAUSE_CN_MAP[cause.type] || cause.type;
                    return (
                    <Descriptions
                      key={index}
                      title={`根因 ${index + 1}: ${cnCauseType}`}
                      bordered
                      column={1}
                      style={{ marginBottom: '16px' }}
                    >
                      <Descriptions.Item label="根因描述">
                        <div style={{ 
                          backgroundColor: '#1a2a3a', 
                          padding: '12px', 
                          borderRadius: '4px',
                          fontSize: '14px',
                          lineHeight: '1.8',
                          color: '#e6e6e6',
                          border: '1px solid #2d4a6a',
                          wordBreak: 'break-word'
                        }}>
                          {cause.description || cause.impact || '暂无详细描述'}
                        </div>
                      </Descriptions.Item>
                      <Descriptions.Item label="置信度">
                        <Progress percent={Math.round(cause.confidence * 100)} size="small" />
                      </Descriptions.Item>
                      {cause.impact && cause.impact !== cause.description && (
                        <Descriptions.Item label="影响分析">
                          <div style={{ 
                            backgroundColor: '#2d2d2d', 
                            padding: '8px', 
                            borderRadius: '4px',
                            fontSize: '13px',
                            lineHeight: '1.6',
                            color: '#ffa940',
                            border: '1px solid #444'
                          }}>
                            {cause.impact}
                          </div>
                        </Descriptions.Item>
                      )}
                    </Descriptions>
                    );
                  })}
                </Card>

                {/* 解决方案 */}
                <Card 
                  title={<span style={{ color: '#e6e6e6' }}>优化建议</span>} 
                  bordered={false} 
                  style={{ marginBottom: '16px', backgroundColor: '#1e1e1e', border: '1px solid #333' }}
                >
                  {diagnosisResult.solutions?.map((solution, index) => (
                    <Card
                      key={index}
                      type="inner"
                      title={<span style={{ color: '#52c41a', fontSize: '16px', fontWeight: 600 }}>{stripMarkdownPreserveCode(solution.action || '')}</span>}
                      style={{ marginBottom: '16px', backgroundColor: '#2d2d2d', border: '1px solid #444' }}
                    >
                      {solution.sql && solution.sql !== '-- 请根据上述建议执行具体的优化操作' && (
                        <div style={{ marginBottom: '16px' }}>
                          <div style={{ color: '#52c41a', fontWeight: 600, marginBottom: '8px' }}>可执行 SQL 语句:</div>
                          <SqlHighlight 
                            sql={solution.sql} 
                            showCopy={true}
                            maxHeight="400px"
                          />
                        </div>
                      )}
                      <div 
                        className="solution-explanation"
                        style={{ 
                          color: '#e6e6e6',
                          lineHeight: '2',
                          fontSize: '14px',
                          marginTop: '12px',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word'
                        }}
                      >
                        {stripMarkdownPreserveCode(solution.explanation || '')}
                      </div>
                      <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                        {solution.confidence && (
                          <Tag color="green">
                            置信度: {(solution.confidence * 100).toFixed(0)}%
                          </Tag>
                        )}
                        {solution.priority && (
                          <Tag color={solution.priority === '高' ? 'red' : solution.priority === '中' ? 'orange' : 'blue'}>
                            优先级: {solution.priority}
                          </Tag>
                        )}
                      </div>
                    </Card>
                  ))}
                </Card>

                {/* 推理过程可视化 */}
                <Card 
                  title={
                    <span style={{ color: '#e6e6e6' }}>
                      <SyncOutlined style={{ marginRight: '8px' }} />
                      推理过程 (Tree Search)
                    </span>
                  }
                  bordered={false}
                  style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
                >
                  <ReasoningTreeChart 
                    data={{ 
                      reasoning_tree: diagnosisResult.reasoning_tree,
                      reasoning_steps: diagnosisResult.reasoning_steps 
                    }}
                    height={400}
                  />
                </Card>

                {/* 多智能体协作诊断 */}
                {diagnosisResult.multi_agent_result && 
                 (diagnosisResult.multi_agent_result.experts?.length > 0 || 
                  diagnosisResult.multi_agent_result.expert_results?.length > 0) && (
                  <Card 
                    title={
                      <span style={{ color: '#e6e6e6' }}>
                        <TeamOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
                        多智能体协作诊断
                      </span>
                    }
                    bordered={false}
                    style={{ marginTop: '16px', backgroundColor: '#1e1e1e', border: '1px solid #333' }}
                    extra={
                      <Tag color="blue" icon={<ThunderboltOutlined />}>
                        协作耗时: {diagnosisResult.multi_agent_result?.collaboration_time || diagnosisResult.multi_agent_result?.performance_stats?.total_diagnosis_time || '--'}
                      </Tag>
                    }
                  >
                    {/* 专家分配器 */}
                    {diagnosisResult.multi_agent_result?.assigner?.assigned_experts?.length > 0 && (
                      <Alert
                        message={<span style={{ color: '#e6e6e6' }}>Expert Assigner 已分配专家</span>}
                        description={
                          <span>
                            {diagnosisResult.multi_agent_result.assigner.assigned_experts.map(expert => (
                              <Tag key={expert} color="blue" style={{ margin: '4px' }}>{expert}</Tag>
                            ))}
                          </span>
                        }
                        type="info"
                        showIcon
                        icon={<UserOutlined />}
                        style={{ marginBottom: '16px', backgroundColor: '#1a3a4d', border: '1px solid #1890ff' }}
                      />
                    )}

                    {/* 专家诊断卡片 */}
                    <Row gutter={[16, 16]}>
                      {(diagnosisResult.multi_agent_result?.experts || diagnosisResult.multi_agent_result?.expert_results || []).map((expert, index) => {
                        // 兼容两种数据格式，优先使用expert_name字段
                        const expertData = expert.expert_type ? {
                          name: expert.expert_name || expert.name || expert.expert_type?.value || `专家${index + 1}`,
                          role: expert.role || expert.expert_type?.description || '',
                          status: expert.status || 'completed',
                          confidence: expert.confidence || 0.8,
                          findings: expert.findings || expert.root_cause_summary || '',
                          analysis: expert.analysis || expert.reasoning_steps || [],
                          reasoning: expert.reasoning || '',
                          avatar_color: expert.avatar_color || ['#ff4d4f', '#1890ff', '#52c41a', '#faad14', '#722ed1', '#13c2c2', '#eb2f96'][index % 7]
                        } : expert;
                        
                        return (
                          <Col xs={24} md={8} key={index}>
                            <Card 
                              size="small"
                              title={
                                <span style={{ color: '#e6e6e6' }}>
                                  <UserOutlined style={{ color: expertData.avatar_color, marginRight: '8px' }} />
                                  {expertData.name}
                                </span>
                              }
                              extra={<Tag color={expertData.status === 'completed' ? 'success' : 'processing'}>{expertData.status}</Tag>}
                              style={{ height: '100%', backgroundColor: '#2d2d2d', border: '1px solid #444' }}
                            >
                              <p style={{ color: '#b0b0b0', fontSize: '12px', marginBottom: '8px' }}>{expertData.role}</p>
                              
                              {/* 分析步骤 */}
                              {expertData.analysis?.length > 0 && (
                                <div style={{ marginBottom: '8px' }}>
                                  {expertData.analysis.map((step, i) => (
                                    <div key={i} style={{ fontSize: '12px', marginBottom: '4px', paddingLeft: '8px', borderLeft: '2px solid ' + expertData.avatar_color }}>
                                      <span style={{ color: '#888' }}>Step {step.step || i + 1}:</span> <span style={{ color: '#d0d0d0' }}>{step.thought || step}</span>
                                    </div>
                                  ))}
                                </div>
                              )}

                              {/* 发现 */}
                              {expertData.findings && (
                                <div style={{ background: '#3d3d3d', padding: '8px', borderRadius: '4px', marginBottom: '8px' }}>
                                  <strong style={{ fontSize: '12px', color: '#e6e6e6' }}>发现:</strong>
                                  <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#d0d0d0' }}>
                                    <TranslatableText text={expertData.findings} />
                                  </p>
                                </div>
                              )}

                              {/* 置信度 */}
                              <Progress 
                                percent={Math.round((expertData.confidence || 0.8) * 100)} 
                                size="small" 
                                strokeColor={expertData.avatar_color}
                                format={percent => `置信度 ${percent}%`}
                              />
                            </Card>
                          </Col>
                        );
                      })}
                    </Row>

                    {/* 交叉评审 */}
                    {diagnosisResult.multi_agent_result?.cross_review?.reviews?.length > 0 && (
                      <Card 
                        title={
                          <span style={{ color: '#e6e6e6' }}>
                            <MessageOutlined style={{ marginRight: '8px' }} />
                            交叉评审 (Cross Review)
                          </span>
                        }
                        size="small"
                        style={{ marginTop: '16px', backgroundColor: '#2d2d2d', border: '1px solid #444' }}
                      >
                        <Timeline
                          items={(diagnosisResult.multi_agent_result?.cross_review?.reviews || []).map((review, i) => ({
                            color: 'green',
                            children: (
                              <div style={{ 
                                backgroundColor: '#252525', 
                                padding: '12px', 
                                borderRadius: '6px',
                                border: '1px solid #333'
                              }}>
                                <Tag color="blue" style={{ marginBottom: '8px' }}>{review?.expert || `专家${i + 1}`}</Tag>
                                <div style={{ 
                                  color: '#d0d0d0', 
                                  whiteSpace: 'pre-wrap',
                                  wordBreak: 'break-word',
                                  lineHeight: '1.6',
                                  fontSize: '13px'
                                }}>
                                  {review?.advice || ''}
                                </div>
                              </div>
                            )
                          }))}
                        />
                        
                        {diagnosisResult.multi_agent_result?.cross_review?.final_consensus && (
                          <Alert
                            message={<span style={{ color: '#e6e6e6' }}>最终共识</span>}
                            description={
                              <div style={{ 
                                color: '#d0d0d0',
                                whiteSpace: 'pre-wrap',
                                lineHeight: '2',
                                fontSize: '14px',
                                wordBreak: 'break-word'
                              }}>
                                {(diagnosisResult.multi_agent_result?.cross_review?.final_consensus || '')
                                  .replace(/^#{1,6}\s*/gm, '')
                                  .replace(/\*\*([^*]+)\*\*/g, '$1')
                                  .replace(/^\*\s+/gm, '• ')}
                              </div>
                            }
                            type="success"
                            showIcon
                            icon={<CheckCircleOutlined />}
                            style={{ backgroundColor: '#1a3d1a', border: '1px solid #52c41a' }}
                          />
                        )}
                      </Card>
                    )}
                  </Card>
                )}

                {/* 新组件：知识检索、反思、工具匹配 */}
                <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
                  <Col xs={24} md={8}>
                    <InlineKnowledgePanel 
                      data={diagnosisResult.retrieved_knowledge}
                      title="知识检索分析 (BM25)"
                    />
                  </Col>
                  <Col xs={24} md={8}>
                    <InlineReflectionPanel 
                      data={diagnosisResult.reflection_insights}
                      title="反思机制洞察"
                      totalSteps={diagnosisResult.tool_match_scores?.length || 7}
                    />
                  </Col>
                  <Col xs={24} md={8}>
                    <InlineToolMatchPanel 
                      data={diagnosisResult.tool_match_scores}
                      title="工具匹配分析"
                    />
                  </Col>
                </Row>
              </>
            ) : !globalTrcParseResult ? (
              <>
                {/* 诊断未开始时的空状态提示 */}
                <Card bordered={false} style={{ backgroundColor: '#1e1e1e', border: '1px solid #333', marginBottom: '16px' }}>
                  <div style={{ textAlign: 'center', padding: '40px 0', color: '#8c8c8c' }}>
                    <BugOutlined style={{ fontSize: '48px', marginBottom: '16px', color: '#1890ff' }} />
                    <h3 style={{ color: '#e6e6e6', marginBottom: '12px' }}>数据库智能诊断系统</h3>
                    <p style={{ marginBottom: '24px' }}>上传异常文件并点击"开始诊断"查看结果</p>
                    <Alert
                      message="快速开始"
                      description="点击左侧「选择文件」上传诊断配置，或直接点击「开始诊断」使用默认配置"
                      type="info"
                      showIcon
                      style={{ textAlign: 'left', maxWidth: '400px', margin: '0 auto' }}
                    />
                  </div>
                </Card>

                {/* 空状态卡片 */}
                <Card 
                  title={<span style={{ color: '#e6e6e6' }}><TeamOutlined style={{ marginRight: '8px', color: '#1890ff' }} />多专家协同诊断</span>}
                  bordered={false}
                  style={{ marginBottom: '16px', backgroundColor: '#1e1e1e', border: '1px solid #333' }}
                >
                  <div style={{ textAlign: 'center', padding: '30px 0', color: '#666' }}>
                    <TeamOutlined style={{ fontSize: '32px', marginBottom: '12px', opacity: 0.5 }} />
                    <p>点击"开始诊断"后，专家将并行分析数据库异常</p>
                    <Tag color="default" style={{ marginTop: '8px' }}>等待诊断开始</Tag>
                  </div>
                </Card>
              </>
            ) : null}
          </Spin>
        </Col>
      </Row>

      {/* 实验评估看板 */}
      <Row style={{ marginTop: '24px' }}>
        <Col span={24}>
          <EvaluationTable />
        </Col>
      </Row>

      {/* 自动任务冲突 Modal */}
      <Modal
        title={
          <span>
            <ExclamationCircleOutlined style={{ color: '#faad14', marginRight: '8px' }} />
            系统后台正在执行自动巡检任务
          </span>
        }
        open={autoTaskModalVisible}
        onCancel={() => setAutoTaskModalVisible(false)}
        footer={null}
        width={520}
      >
        <div style={{ padding: '16px 0' }}>
          <p style={{ marginBottom: '16px', color: '#666' }}>
            系统检测到后台正在执行自动巡检诊断任务，您可以选择：
          </p>
          
          <Descriptions column={2} size="small" style={{ marginBottom: '16px', backgroundColor: '#fafafa', padding: '12px', borderRadius: '4px' }}>
            <Descriptions.Item label="任务ID">{autoTaskInfo?.diagnosis_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="已运行时间">{Math.round(autoTaskInfo?.elapsed_seconds || 0)} 秒</Descriptions.Item>
            <Descriptions.Item label="当前步骤">{autoTaskInfo?.current_step || 0} / {autoTaskInfo?.total_steps || 10}</Descriptions.Item>
            <Descriptions.Item label="预计剩余">{Math.round(autoTaskInfo?.estimated_remaining || 60)} 秒</Descriptions.Item>
          </Descriptions>
          
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '24px' }}>
            <Button onClick={() => setAutoTaskModalVisible(false)}>
              取消
            </Button>
            <Button 
              type="default" 
              icon={<SyncOutlined />}
              onClick={handleWaitAutoTask}
            >
              等待完成
            </Button>
            <Button 
              type="primary" 
              danger
              icon={<StopOutlined />}
              onClick={handleCancelAutoAndStart}
            >
              取消自动任务并开始诊断
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default Diagnosis;
