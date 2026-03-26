/**
 * 多专家协作组件 - 可视化展示专家诊断过程
 * 
 * 本组件展示 D-Bot 论文提出的多专家协作诊断机制：
 * 1. 专家面板 - 展示各领域专家的诊断状态和结论
 * 2. 协作流程 - 可视化专家之间的交互和评审过程
 * 3. 结果融合 - 综合多位专家意见形成最终诊断
 * 4. 置信度展示 - 显示各专家诊断结果的可信程度
 * 
 * 支持的专家类型：CPU、内存、I/O、工作负载、锁、查询、存储
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Row, Col, Tag, Badge, Progress, Timeline, Empty,
  Button, Drawer, List, Typography, Space, Divider, Tooltip,
  Steps, Collapse, Statistic
} from 'antd';
import {
  UserOutlined, MessageOutlined, CheckCircleOutlined,
  SyncOutlined, ExclamationCircleOutlined, BulbOutlined, EyeOutlined,
  CommentOutlined, ArrowRightOutlined, TeamOutlined, ThunderboltOutlined,
  BranchesOutlined, ShareAltOutlined, CodeOutlined, ClockCircleOutlined,
  DatabaseOutlined, DashboardOutlined, RightOutlined, SwapOutlined,
  WarningOutlined, InfoCircleOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';

const { Text, Title, Paragraph } = Typography;

const STATUS_COLORS = {
  normal: { bg: '#0F172A', color: '#10B981', glow: 'rgba(16, 185, 129, 0.3)' },
  processing: { bg: '#0F172A', color: '#3B82F6', glow: 'rgba(59, 130, 246, 0.3)' },
  warning: { bg: '#0F172A', color: '#F59E0B', glow: 'rgba(245, 158, 11, 0.3)' },
  error: { bg: '#0F172A', color: '#EF4444', glow: 'rgba(239, 68, 68, 0.3)' }
};

const expertConfig = {
  cpu_expert: { name: 'CPU专家', icon: '🔥', role: 'CPU使用率、进程调度、负载均衡' },
  memory_expert: { name: '内存专家', icon: '💾', role: '内存泄漏、缓冲区管理、交换空间' },
  io_expert: { name: 'I/O专家', icon: '💿', role: '磁盘I/O、存储性能、文件系统' },
  workload_expert: { name: '工作负载专家', icon: '📊', role: '查询优化、并发控制、事务处理' },
  database_expert: { name: '数据库专家', icon: '🗄️', role: '数据库配置、架构设计、整体性能' }
};

const MultiExpertCollaboration = ({ 
  collaborationData, 
  isVisible = true,
  isRunning = false,
  currentPhase = ''
}) => {
  const [activeStep, setActiveStep] = useState(0);
  const [selectedReview, setSelectedReview] = useState(null);
  const [reviewDrawerVisible, setReviewDrawerVisible] = useState(false);
  const [animatingConsensus, setAnimatingConsensus] = useState(0);

  useEffect(() => {
    if (isRunning) {
      const interval = setInterval(() => {
        setActiveStep(prev => (prev < 3 ? prev + 1 : prev));
      }, 2500);
      return () => clearInterval(interval);
    }
  }, [isRunning]);

  useEffect(() => {
    if (isRunning) {
      const interval = setInterval(() => {
        setAnimatingConsensus(prev => {
          const target = collaborationData?.expert_consensus_rate || 0;
          if (prev < target * 100) {
            return Math.min(prev + 3, target * 100);
          }
          return prev;
        });
      }, 150);
      return () => clearInterval(interval);
    } else {
      setAnimatingConsensus((collaborationData?.expert_consensus_rate || 0) * 100);
    }
  }, [isRunning, collaborationData?.expert_consensus_rate]);

  const getAssignedExperts = () => {
    const experts = collaborationData?.assigner?.assigned_experts || 
                   collaborationData?.assigned_experts || [];
    if (experts.length > 0) return experts;
    const alertType = collaborationData?.anomaly_type || 'slow_sql';
    if (alertType === 'slow_sql') return ['workload_expert', 'cpu_expert', 'io_expert'];
    if (alertType === 'lock') return ['workload_expert', 'database_expert'];
    return ['cpu_expert', 'memory_expert', 'io_expert'];
  };

  const assignedExperts = getAssignedExperts();

  const getExpertStatus = (expert) => {
    if (expert.status !== 'completed') return 'processing';
    const confidence = expert.confidence || 0.85;
    if (confidence >= 0.9) return 'error';
    if (confidence >= 0.8) return 'warning';
    return 'normal';
  };

  const getFlowChartOption = () => {
    const experts = collaborationData?.experts || [];
    const expertStatusMap = {};
    experts.forEach(e => {
      expertStatusMap[e.expert_type || e.name] = getExpertStatus(e);
    });

    const getNodeColor = (name, expertKey) => {
      if (isRunning && activeStep < 3) return STATUS_COLORS.processing.color;
      if (expertKey && expertStatusMap[expertKey]) {
        return STATUS_COLORS[expertStatusMap[expertKey]].color;
      }
      if (name === '最终共识') {
        const rate = animatingConsensus / 100;
        if (rate >= 0.8) return STATUS_COLORS.normal.color;
        if (rate >= 0.6) return STATUS_COLORS.warning.color;
        return STATUS_COLORS.error.color;
      }
      return STATUS_COLORS.processing.color;
    };

    const expertNodes = assignedExperts.slice(0, 3).map((e, i) => ({
      name: expertConfig[e]?.name || e,
      expertKey: e,
      x: 380, y: 35 + i * 55,
      itemStyle: { 
        color: getNodeColor(expertConfig[e]?.name, e),
        shadowBlur: 8,
        shadowColor: isRunning ? STATUS_COLORS.processing.glow : 'transparent'
      },
      label: { 
        formatter: `${expertConfig[e]?.icon} ${expertConfig[e]?.name?.replace('专家', '') || e}`,
        color: '#E2E8F0'
      }
    }));

    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item' },
      series: [{
        type: 'graph',
        layout: 'none',
        symbolSize: [90, 32],
        roam: false,
        animation: true,
        animationDuration: 800,
        label: {
          show: true,
          fontSize: 15,
          color: '#E2E8F0',
          fontWeight: 'bold'
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [4, 8],
        data: [
          { 
            name: '异常输入', 
            x: 50, y: 80,
            itemStyle: { color: '#475569' },
            label: { formatter: '📥 异常输入', color: '#94A3B8' }
          },
          { 
            name: 'Expert Assigner', 
            x: 200, y: 80,
            itemStyle: { 
              color: getNodeColor('Expert Assigner'),
              shadowBlur: isRunning ? 10 : 0,
              shadowColor: STATUS_COLORS.processing.glow
            },
            label: { formatter: '🎯 分配器', color: '#E2E8F0' }
          },
          ...expertNodes,
          { 
            name: 'Cross Review', 
            x: 540, y: 80,
            itemStyle: { 
              color: getNodeColor('Cross Review'),
              shadowBlur: isRunning ? 10 : 0,
              shadowColor: STATUS_COLORS.warning.glow
            },
            label: { formatter: '🔄 交叉审查', color: '#E2E8F0' }
          },
          { 
            name: '最终共识', 
            x: 700, y: 80,
            itemStyle: { 
              color: getNodeColor('最终共识'),
              shadowBlur: 12,
              shadowColor: STATUS_COLORS.normal.glow
            },
            label: { formatter: '✅ 最终共识', color: '#E2E8F0' }
          }
        ],
        links: [
          { source: '异常输入', target: 'Expert Assigner', lineStyle: { width: 2, color: '#475569' } },
          ...assignedExperts.slice(0, 3).map(e => ({
            source: 'Expert Assigner',
            target: expertConfig[e]?.name || e,
            lineStyle: { width: 2, color: '#3B82F6' }
          })),
          ...assignedExperts.slice(0, 3).map(e => ({
            source: expertConfig[e]?.name || e,
            target: 'Cross Review',
            lineStyle: { width: 2, color: '#3B82F6' }
          })),
          { source: 'Cross Review', target: '最终共识', lineStyle: { width: 3, color: '#10B981' } }
        ],
        lineStyle: { curveness: 0 }
      }]
    };
  };

  const renderExpertAssigner = () => {
    const alertType = collaborationData?.anomaly_type || 'slow_sql';
    const alertDesc = collaborationData?.description || '检测到慢查询，CPU使用率异常升高';
    
    return (
      <Card 
        title={
          <Space>
            <BranchesOutlined style={{ color: '#3B82F6' }} />
            <span style={{ fontSize: 18, fontWeight: 'bold', color: '#E2E8F0' }}>专家分配器</span>
            <Tag style={{ fontSize: 14, background: '#1E293B', color: '#94A3B8', border: '1px solid #334155' }}>
              Expert Assigner
            </Tag>
          </Space>
        }
        size="small"
        style={{ 
          marginBottom: 12, 
          background: '#0F172A', 
          border: '1px solid #1E293B',
          borderLeft: `3px solid ${isRunning ? '#3B82F6' : '#10B981'}`
        }}
        extra={
          <Space>
            <Badge 
              status={isRunning ? "processing" : "success"} 
              style={{ backgroundColor: isRunning ? '#3B82F6' : '#10B981' }}
            />
            <Text style={{ fontSize: 16, color: '#94A3B8' }}>
              {isRunning ? '分析中...' : '已分配'}
            </Text>
          </Space>
        }
        headStyle={{ background: '#0F172A', borderBottom: '1px solid #1E293B' }}
        bodyStyle={{ background: '#0F172A' }}
      >
        <Row gutter={12}>
          <Col span={10}>
            <div style={{ background: '#1E293B', padding: 12, borderRadius: 6, border: '1px solid #334155' }}>
              <Text strong style={{ fontSize: 16, color: '#E2E8F0', display: 'block', marginBottom: 8 }}>
                📥 异常上下文
              </Text>
              <div style={{ fontSize: 11 }}>
                <Tag style={{ background: '#7C2D12', color: '#FED7AA', border: 'none', marginBottom: 6 }}>
                  {alertType}
                </Tag>
                <Text style={{ fontSize: 14, color: '#94A3B8' }}>{alertDesc}</Text>
              </div>
            </div>
          </Col>
          <Col span={14}>
            <div style={{ background: '#1E293B', padding: 12, borderRadius: 6, border: '1px solid #334155' }}>
              <Text strong style={{ fontSize: 12, color: '#E2E8F0', display: 'block', marginBottom: 8 }}>
                🎯 激活专家 ({assignedExperts.length}位)
              </Text>
              <Space wrap size={[6, 6]}>
                {assignedExperts.map((expert, idx) => (
                  <Tag 
                    key={idx} 
                    style={{ 
                      fontSize: 13, 
                      padding: '3px 10px',
                      background: '#1E293B',
                      color: '#E2E8F0',
                      border: '1px solid #334155'
                    }}
                  >
                    {expertConfig[expert]?.icon} {expertConfig[expert]?.name}
                  </Tag>
                ))}
              </Space>
            </div>
          </Col>
        </Row>
      </Card>
    );
  };

  const renderAsyncCollaboration = () => {
    const experts = collaborationData?.experts || [];
    const hasData = experts.length > 0;
    const totalTime = experts.reduce((sum, e) => sum + (e.diagnosis_time || 0), 0);

    return (
      <Card 
        title={
          <Space>
            <ShareAltOutlined style={{ color: '#10B981' }} />
            <span style={{ fontSize: 18, fontWeight: 'bold', color: '#E2E8F0' }}>异步协作</span>
            <Tag style={{ fontSize: 13, background: '#1E293B', color: '#94A3B8', border: '1px solid #334155' }}>
              Async Collaboration
            </Tag>
          </Space>
        }
        size="small"
        style={{ 
          marginBottom: 12, 
          background: '#0F172A', 
          border: '1px solid #1E293B',
          borderLeft: '3px solid #10B981'
        }}
        extra={
          hasData && (
            <div style={{ 
              background: '#064E3B', 
              padding: '4px 14px', 
              borderRadius: 6,
              border: '1px solid #10B981'
            }}>
              <Text style={{ 
                fontSize: 16, 
                fontWeight: 'bold', 
                fontFamily: 'Consolas, Monaco, monospace',
                color: '#10B981'
              }}>
                ⏱ {totalTime.toFixed(1)}s
              </Text>
            </div>
          )
        }
        headStyle={{ background: '#0F172A', borderBottom: '1px solid #1E293B' }}
        bodyStyle={{ background: '#0F172A' }}
      >
        {hasData ? (
          <Row gutter={[12, 12]}>
            {experts.map((expert, idx) => {
              const expertKey = expert.expert_type || expert.name;
              const config = expertConfig[expertKey] || {};
              const status = getExpertStatus(expert);
              const statusColor = STATUS_COLORS[status];
              const confidence = expert.confidence || 0.85;
              const diagTime = expert.diagnosis_time || 0;
              
              return (
                <Col xs={24} md={8} key={idx}>
                  <div 
                    style={{ 
                      padding: 14,
                      background: '#1E293B',
                      borderRadius: 8,
                      border: `1px solid ${statusColor.color}44`,
                      boxShadow: `0 0 20px ${statusColor.glow}`
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
                      <span style={{ fontSize: 24, marginRight: 10 }}>
                        {config.icon || '🤖'}
                      </span>
                      <div style={{ flex: 1 }}>
                        <Text strong style={{ fontSize: 15, color: '#E2E8F0' }}>
                          {config.name || expert.name}
                        </Text>
                      </div>
                      <Tag 
                        style={{ 
                          background: status === 'normal' ? '#064E3B' : 
                                     status === 'warning' ? '#78350F' :
                                     status === 'error' ? '#7F1D1D' : '#1E3A5F',
                          color: statusColor.color,
                          border: 'none',
                          fontSize: 10
                        }}
                      >
                        {status === 'normal' ? '✓ 正常' : 
                         status === 'warning' ? '⚠ 警告' :
                         status === 'error' ? '🔴 异常' : '⏳ 分析中'}
                      </Tag>
                    </div>

                    <div style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <Text style={{ fontSize: 13, color: '#94A3B8' }}>置信度</Text>
                        <Text style={{ fontSize: 13, fontWeight: 'bold', color: statusColor.color, fontFamily: 'monospace' }}>
                          {Math.round(confidence * 100)}%
                        </Text>
                      </div>
                      <Progress 
                        percent={Math.round(confidence * 100)} 
                        size="small"
                        strokeColor={statusColor.color}
                        trailColor="#334155"
                        showInfo={false}
                      />
                    </div>

                    {expert.findings && (
                      <div style={{ 
                        marginTop: 10, 
                        padding: 10,
                        background: '#0F172A',
                        borderRadius: 6,
                        border: `1px solid ${statusColor.color}22`
                      }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                          <BulbOutlined style={{ color: statusColor.color, marginRight: 6, marginTop: 2 }} />
                          <Text style={{ fontSize: 15, color: '#E2E8F0', lineHeight: 1.6 }}>
                            {expert.findings.substring(0, 50)}...
                          </Text>
                        </div>
                      </div>
                    )}

                    <div style={{ 
                      marginTop: 10, 
                      paddingTop: 10, 
                      borderTop: '1px solid #334155',
                      display: 'flex', 
                      justifyContent: 'space-between' 
                    }}>
                      <Text style={{ fontSize: 10, color: '#64748B', fontFamily: 'monospace' }}>
                        <ClockCircleOutlined style={{ marginRight: 4 }} />
                        {diagTime.toFixed(2)}s
                      </Text>
                      <Text style={{ fontSize: 10, color: '#3B82F6' }}>
                        并行执行
                      </Text>
                    </div>
                  </div>
                </Col>
              );
            })}
          </Row>
        ) : (
          <Empty 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span style={{ fontSize: 12, color: '#64748B' }}>
                点击"一键注入"开始诊断，专家将并行分析
              </span>
            }
            style={{ padding: '24px 0' }}
          />
        )}
      </Card>
    );
  };

  const renderCrossReview = () => {
    const reviews = collaborationData?.cross_review?.reviews || 
                   collaborationData?.review_advices || [];
    
    const reviewArray = Array.isArray(reviews) ? reviews : 
      Object.entries(reviews).flatMap(([target, advices]) => 
        advices.map(a => ({ ...a, target }))
      );

    return (
      <Card 
        title={
          <Space>
            <CommentOutlined style={{ color: '#F59E0B' }} />
            <span style={{ fontSize: 18, fontWeight: 'bold', color: '#E2E8F0' }}>交叉审查</span>
            <Tag style={{ fontSize: 10, background: '#1E293B', color: '#94A3B8', border: '1px solid #334155' }}>
              Cross Review
            </Tag>
          </Space>
        }
        size="small"
        style={{ 
          marginBottom: 12, 
          background: '#0F172A', 
          border: '1px solid #1E293B',
          borderLeft: '3px solid #F59E0B'
        }}
        extra={
          <Space>
            {reviewArray.length > 0 && (
              <Tag style={{ 
                fontSize: 11, 
                background: '#78350F',
                color: '#FCD34D',
                border: 'none'
              }}>
                {reviewArray.length} 条评审
              </Tag>
            )}
            <Tag style={{ 
              fontSize: 11, 
              background: animatingConsensus > 80 ? '#064E3B' : '#78350F',
              color: animatingConsensus > 80 ? '#10B981' : '#FCD34D',
              border: 'none',
              fontFamily: 'monospace'
            }}>
              共识度 {Math.round(animatingConsensus)}%
            </Tag>
          </Space>
        }
        headStyle={{ background: '#0F172A', borderBottom: '1px solid #1E293B' }}
        bodyStyle={{ background: '#0F172A' }}
      >
        {reviewArray.length > 0 ? (
          <div style={{ background: '#1E293B', borderRadius: 8, border: '1px solid #334155', padding: 14 }}>
            {reviewArray.slice(0, 3).map((review, idx) => {
              const agreementScore = review.agreement_score || 0.8;
              const statusColor = agreementScore > 0.7 ? STATUS_COLORS.normal : STATUS_COLORS.warning;
              
              return (
                <div 
                  key={idx}
                  style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    padding: '10px 0',
                    borderBottom: idx < Math.min(reviewArray.length, 3) - 1 ? '1px solid #334155' : 'none'
                  }}
                >
                  <div style={{ 
                    background: '#0F172A', 
                    padding: '4px 10px', 
                    borderRadius: 4,
                    border: '1px solid #334155'
                  }}>
                    <Text style={{ fontSize: 11, color: '#E2E8F0' }}>
                      {expertConfig[review.reviewer]?.icon} {review.reviewer}
                    </Text>
                  </div>
                  
                  <RightOutlined style={{ fontSize: 10, color: '#F59E0B', margin: '0 10px' }} />
                  
                  <div style={{ 
                    background: '#0F172A', 
                    padding: '4px 10px', 
                    borderRadius: 4,
                    border: '1px solid #334155'
                  }}>
                    <Text style={{ fontSize: 11, color: '#E2E8F0' }}>
                      {expertConfig[review.target]?.icon} {review.target}
                    </Text>
                  </div>
                  
                  <div style={{ flex: 1, marginLeft: 14 }}>
                    <Progress 
                      percent={Math.round(agreementScore * 100)} 
                      size="small" 
                      showInfo={false}
                      strokeColor={statusColor.color}
                      trailColor="#334155"
                    />
                  </div>
                  
                  <Text style={{ 
                    fontSize: 12, 
                    fontWeight: 'bold',
                    color: statusColor.color,
                    marginLeft: 10,
                    width: 45,
                    fontFamily: 'monospace',
                    textAlign: 'right'
                  }}>
                    {Math.round(agreementScore * 100)}%
                  </Text>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span style={{ fontSize: 12, color: '#64748B' }}>
                诊断完成后，专家将互相评审结果
              </span>
            }
            style={{ padding: '24px 0' }}
          />
        )}
      </Card>
    );
  };

  const renderConsensus = () => {
    const consensus = collaborationData?.cross_review?.final_consensus || 
                     collaborationData?.final_consensus || '';
    const consensusRate = collaborationData?.expert_consensus_rate || 0;
    const displayRate = isRunning ? animatingConsensus / 100 : consensusRate;
    
    const getStatusInfo = () => {
      if (displayRate >= 0.8) return { color: STATUS_COLORS.normal.color, bg: '#064E3B', text: '✓ 高度共识' };
      if (displayRate >= 0.6) return { color: STATUS_COLORS.warning.color, bg: '#78350F', text: '○ 基本共识' };
      return { color: STATUS_COLORS.error.color, bg: '#7F1D1D', text: '△ 存在分歧' };
    };
    const statusInfo = getStatusInfo();

    return (
      <Card 
        title={
          <Space>
            <ThunderboltOutlined style={{ color: '#A855F7' }} />
            <span style={{ fontSize: 18, fontWeight: 'bold', color: '#E2E8F0' }}>共识达成</span>
            <Tag style={{ fontSize: 10, background: '#1E293B', color: '#94A3B8', border: '1px solid #334155' }}>
              Consensus
            </Tag>
          </Space>
        }
        size="small"
        style={{ 
          marginBottom: 12, 
          background: '#0F172A', 
          border: '1px solid #1E293B',
          borderLeft: '3px solid #A855F7'
        }}
        extra={
          collaborationData?.collaboration_time && (
            <Tag 
              style={{ 
                fontFamily: 'Consolas, Monaco, monospace',
                background: '#1E3A5F',
                color: '#60A5FA',
                border: 'none'
              }}
            >
              <ClockCircleOutlined style={{ marginRight: 4 }} />
              耗时 {collaborationData.collaboration_time}
            </Tag>
          )
        }
        headStyle={{ background: '#0F172A', borderBottom: '1px solid #1E293B' }}
        bodyStyle={{ background: '#0F172A' }}
      >
        {consensus || consensusRate > 0 ? (
          <Row gutter={16}>
            <Col span={6}>
              <div style={{ 
                textAlign: 'center', 
                padding: 16,
                background: statusInfo.bg,
                borderRadius: 8
              }}>
                <Progress 
                  type="dashboard"
                  width={80}
                  percent={Math.round(displayRate * 100)} 
                  strokeColor={statusInfo.color}
                  trailColor="#334155"
                  format={percent => (
                    <span style={{ 
                      fontSize: 18, 
                      fontWeight: 'bold',
                      fontFamily: 'Consolas, Monaco, monospace',
                      color: statusInfo.color
                    }}>
                      {percent}%
                    </span>
                  )}
                />
                <div style={{ marginTop: 10 }}>
                  <Tag style={{ 
                    background: statusInfo.bg,
                    color: statusInfo.color,
                    border: `1px solid ${statusInfo.color}44`,
                    fontSize: 11
                  }}>
                    {statusInfo.text}
                  </Tag>
                </div>
              </div>
            </Col>
            <Col span={18}>
              <div style={{ 
                background: '#1E293B', 
                padding: 14, 
                borderRadius: 8, 
                border: '1px solid #334155', 
                height: '100%' 
              }}>
                <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 10, color: '#E2E8F0' }}>
                  📋 最终诊断结论
                </Text>
                <Paragraph 
                  ellipsis={{ rows: 4, expandable: true, symbol: <span style={{ color: '#3B82F6' }}>展开</span> }} 
                  style={{ fontSize: 15, color: '#CBD5E1', marginBottom: 0, lineHeight: 1.8 }}
                >
                  {consensus || '综合各专家意见，生成最终诊断结论...'}
                </Paragraph>
              </div>
            </Col>
          </Row>
        ) : (
          <Empty 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span style={{ fontSize: 12, color: '#64748B' }}>
                诊断完成后将显示共识结果
              </span>
            }
            style={{ padding: '24px 0' }}
          />
        )}
      </Card>
    );
  };

  if (!isVisible) return null;

  return (
    <div style={{ padding: '12px', background: '#0F172A', borderRadius: '8px' }}>
      <Card 
        title={
          <Space>
            <TeamOutlined style={{ fontSize: 18, color: '#E2E8F0' }} />
            <span style={{ fontSize: 20, fontWeight: 'bold', color: '#E2E8F0' }}>多专家协同诊断</span>
          </Space>
        }
        variant="borderless"
        style={{ background: '#0F172A', border: '1px solid #1E293B' }}
        extra={
          <Space>
            <Badge 
              status={isRunning ? "processing" : "success"} 
              style={{ backgroundColor: isRunning ? '#3B82F6' : '#10B981' }}
            />
            <Text style={{ fontSize: 12, color: '#94A3B8' }}>
              {isRunning ? '诊断进行中...' : '诊断完成'}
            </Text>
          </Space>
        }
        headStyle={{ background: '#0F172A', borderBottom: '1px solid #1E293B' }}
        bodyStyle={{ background: '#0F172A' }}
      >
        <Steps
          current={activeStep}
          size="small"
          items={[
            { 
              title: <span style={{ color: '#94A3B8' }}>专家分配</span>, 
              status: activeStep === 0 ? 'process' : activeStep > 0 ? 'finish' : 'wait',
              icon: activeStep === 0 ? <SyncOutlined spin style={{ color: '#3B82F6' }} /> : 
                    activeStep > 0 ? <CheckCircleOutlined style={{ color: '#10B981' }} /> : 
                    <BranchesOutlined style={{ color: '#475569' }} />
            },
            { 
              title: <span style={{ color: '#94A3B8' }}>并行诊断</span>, 
              status: activeStep === 1 ? 'process' : activeStep > 1 ? 'finish' : 'wait',
              icon: activeStep === 1 ? <SyncOutlined spin style={{ color: '#3B82F6' }} /> : 
                    activeStep > 1 ? <CheckCircleOutlined style={{ color: '#10B981' }} /> : 
                    <ShareAltOutlined style={{ color: '#475569' }} />
            },
            { 
              title: <span style={{ color: '#94A3B8' }}>交叉审查</span>, 
              status: activeStep === 2 ? 'process' : activeStep > 2 ? 'finish' : 'wait',
              icon: activeStep === 2 ? <SyncOutlined spin style={{ color: '#F59E0B' }} /> : 
                    activeStep > 2 ? <CheckCircleOutlined style={{ color: '#10B981' }} /> : 
                    <CommentOutlined style={{ color: '#475569' }} />
            },
            { 
              title: <span style={{ color: '#94A3B8' }}>共识达成</span>, 
              status: activeStep >= 3 ? 'finish' : 'wait',
              icon: activeStep >= 3 ? <CheckCircleOutlined style={{ color: '#10B981' }} /> : 
                    <ThunderboltOutlined style={{ color: '#475569' }} />
            }
          ]}
          style={{ marginBottom: 16 }}
        />

        <div style={{ 
          background: '#1E293B', 
          borderRadius: 8, 
          padding: 12,
          marginBottom: 16,
          border: '1px solid #334155'
        }}>
          <ReactECharts 
            option={getFlowChartOption()} 
            style={{ height: 160 }}
          />
        </div>
      </Card>

      {renderExpertAssigner()}
      {renderAsyncCollaboration()}
      {renderCrossReview()}
      {renderConsensus()}

      <Drawer
        title={
          <Space>
            <CommentOutlined style={{ color: '#F59E0B' }} />
            <span style={{ color: '#E2E8F0' }}>评审详情</span>
          </Space>
        }
        placement="right"
        width={450}
        open={reviewDrawerVisible}
        onClose={() => setReviewDrawerVisible(false)}
        styles={{ 
          header: { background: '#0F172A', borderBottom: '1px solid #1E293B' },
          body: { background: '#0F172A' }
        }}
      >
        {selectedReview && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Card size="small" style={{ background: '#1E293B', border: '1px solid #334155' }}>
              <Space>
                <Tag style={{ background: '#0F172A', color: '#E2E8F0', border: '1px solid #334155' }}>
                  {expertConfig[selectedReview.reviewer]?.icon} {selectedReview.reviewer}
                </Tag>
                <ArrowRightOutlined style={{ color: '#F59E0B' }} />
                <Tag style={{ background: '#0F172A', color: '#E2E8F0', border: '1px solid #334155' }}>
                  {expertConfig[selectedReview.target]?.icon} {selectedReview.target}
                </Tag>
              </Space>
            </Card>

            <Card 
              title={<span style={{ color: '#E2E8F0' }}>一致性评分</span>} 
              size="small"
              style={{ background: '#1E293B', border: '1px solid #334155' }}
              headStyle={{ background: '#1E293B', borderBottom: '1px solid #334155' }}
            >
              <Progress 
                percent={Math.round((selectedReview.agreement_score || 0.5) * 100)}
                strokeColor={selectedReview.agreement_score > 0.7 ? '#10B981' : '#F59E0B'}
                trailColor="#334155"
              />
              <Text style={{ fontSize: 12, color: '#94A3B8' }}>
                {selectedReview.agreement_score > 0.7 ? '专家意见一致' : '存在分歧，需要进一步分析'}
              </Text>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default MultiExpertCollaboration;
