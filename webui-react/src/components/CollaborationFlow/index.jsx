import React, { useState, useEffect, useRef } from 'react';
import { Timeline, Card, Tag, Badge, Avatar, Tooltip, Progress, message, Button, Drawer, List, Typography, Space, Divider, Alert } from 'antd';
import {
  UserOutlined,
  RobotOutlined,
  MessageOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
  BulbOutlined,
  EyeOutlined,
  CommentOutlined,
  ArrowRightOutlined,
  TeamOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';

const { Text, Title, Paragraph } = Typography;

const CollaborationFlow = ({ collaborationData, isVisible = true }) => {
  const [messages, setMessages] = useState([]);
  const [selectedReview, setSelectedReview] = useState(null);
  const [reviewDrawerVisible, setReviewDrawerVisible] = useState(false);
  const [animationEnabled, setAnimationEnabled] = useState(true);
  const messageEndRef = useRef(null);

  useEffect(() => {
    if (collaborationData) {
      parseCollaborationData(collaborationData);
    }
  }, [collaborationData]);

  useEffect(() => {
    if (animationEnabled && messageEndRef.current) {
      messageEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, animationEnabled]);

  const parseCollaborationData = (data) => {
    const parsedMessages = [];
    let msgId = 0;

    // 阶段1: 专家分配
    if (data.assigned_experts) {
      parsedMessages.push({
        id: msgId++,
        type: 'assignment',
        timestamp: new Date().toISOString(),
        title: '专家分配完成',
        content: `Expert Assigner 已分配 ${data.assigned_experts.length} 个专家`,
        experts: data.assigned_experts,
        status: 'success'
      });
    }

    // 阶段2: 专家诊断
    if (data.experts) {
      data.experts.forEach((expert, index) => {
        parsedMessages.push({
          id: msgId++,
          type: 'diagnosis',
          timestamp: new Date().toISOString(),
          expert: expert.name || expert.expert_type,
          role: expert.role || getExpertRole(expert.name || expert.expert_type),
          status: expert.status || 'completed',
          confidence: expert.confidence,
          findings: expert.findings,
          rootCauses: expert.root_causes,
          duration: expert.diagnosis_time
        });
      });
    }

    // 阶段3: 交叉评审
    if (data.review_advices) {
      Object.entries(data.review_advices).forEach(([target, advices]) => {
        advices.forEach((advice, index) => {
          parsedMessages.push({
            id: msgId++,
            type: 'review',
            timestamp: new Date().toISOString(),
            reviewer: advice.reviewer,
            target: target,
            agreementScore: advice.agreement_score,
            missedCauses: advice.missed_causes,
            suggestions: advice.improvement_suggestions,
            reviewConfidence: advice.review_confidence
          });
        });
      });
    }

    // 阶段4: 结果精炼
    if (data.refined_results) {
      data.refined_results.forEach((result, index) => {
        if (result.refined) {
          parsedMessages.push({
            id: msgId++,
            type: 'refinement',
            timestamp: new Date().toISOString(),
            expert: result.expert_type,
            refined: result.refined,
            agreementScore: result.agreement_score,
            reviewCount: result.review_count
          });
        }
      });
    }

    // 阶段5: 最终共识
    if (data.final_consensus) {
      parsedMessages.push({
        id: msgId++,
        type: 'consensus',
        timestamp: new Date().toISOString(),
        content: data.final_consensus,
        consensusRate: data.expert_consensus_rate
      });
    }

    setMessages(parsedMessages);
  };

  const getExpertRole = (expertName) => {
    const roles = {
      'cpu_expert': 'CPU专家 - 专注CPU性能分析',
      'memory_expert': '内存专家 - 专注内存使用优化',
      'io_expert': 'I/O专家 - 专注磁盘和网络I/O',
      'workload_expert': '工作负载专家 - 专注查询和事务',
      'database_expert': '数据库专家 - 专注整体架构'
    };
    return roles[expertName] || '数据库诊断专家';
  };

  const getExpertColor = (expertName) => {
    const colors = {
      'cpu_expert': '#ff4d4f',
      'memory_expert': '#1890ff',
      'io_expert': '#52c41a',
      'workload_expert': '#faad14',
      'database_expert': '#722ed1'
    };
    return colors[expertName] || '#666';
  };

  const getExpertIcon = (expertName) => {
    const icons = {
      'cpu_expert': '🔥',
      'memory_expert': '💾',
      'io_expert': '💿',
      'workload_expert': '📊',
      'database_expert': '🗄️'
    };
    return icons[expertName] || '🤖';
  };

  const renderMessage = (msg) => {
    switch (msg.type) {
      case 'assignment':
        return (
          <div style={{ padding: '12px', background: '#f6ffed', borderRadius: '8px', border: '1px solid #b7eb8f' }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
              <TeamOutlined style={{ color: '#52c41a', marginRight: 8 }} />
              <Text strong style={{ color: '#52c41a' }}>{msg.title}</Text>
            </div>
            <Space wrap>
              {msg.experts?.map((expert, idx) => (
                <Tag key={idx} color={getExpertColor(expert)} icon={<RobotOutlined />}>
                  {getExpertIcon(expert)} {expert}
                </Tag>
              ))}
            </Space>
          </div>
        );

      case 'diagnosis':
        return (
          <div style={{ padding: '12px', background: '#fff', borderRadius: '8px', border: `2px solid ${getExpertColor(msg.expert)}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Space>
                <Avatar style={{ backgroundColor: getExpertColor(msg.expert) }}>
                  {getExpertIcon(msg.expert)}
                </Avatar>
                <div>
                  <Text strong>{msg.expert}</Text>
                  <br />
                  <Text type="secondary" style={{ fontSize: 12 }}>{msg.role}</Text>
                </div>
              </Space>
              <Space direction="vertical" align="end">
                <Tag color={msg.status === 'completed' ? 'success' : 'processing'}>
                  {msg.status === 'completed' ? '✅ 完成' : '⏳ 进行中'}
                </Tag>
                {msg.confidence && (
                  <Progress 
                    percent={Math.round(msg.confidence * 100)} 
                    size="small" 
                    style={{ width: 80 }}
                    strokeColor={getExpertColor(msg.expert)}
                  />
                )}
              </Space>
            </div>
            {msg.findings && (
              <Alert 
                message="诊断发现" 
                description={msg.findings} 
                type="info" 
                showIcon 
                style={{ marginTop: 8 }}
              />
            )}
            {msg.duration && (
              <Text type="secondary" style={{ fontSize: 12 }}>⏱️ 耗时: {msg.duration.toFixed(2)}s</Text>
            )}
          </div>
        );

      case 'review':
        return (
          <div 
            style={{ padding: '12px', background: '#fffbe6', borderRadius: '8px', border: '1px solid #ffe58f', cursor: 'pointer' }}
            onClick={() => {
              setSelectedReview(msg);
              setReviewDrawerVisible(true);
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
              <CommentOutlined style={{ color: '#faad14', marginRight: 8 }} />
              <Text strong style={{ color: '#faad14' }}>交叉评审</Text>
              <ArrowRightOutlined style={{ margin: '0 8px', color: '#999' }} />
              <Tag color={getExpertColor(msg.reviewer)}>{getExpertIcon(msg.reviewer)} {msg.reviewer}</Tag>
              <Text type="secondary">评审</Text>
              <Tag color={getExpertColor(msg.target)}>{getExpertIcon(msg.target)} {msg.target}</Tag>
            </div>
            <Space>
              <Text>一致性评分: </Text>
              <Progress 
                percent={Math.round((msg.agreementScore || 0.5) * 100)} 
                size="small" 
                style={{ width: 100 }}
                strokeColor={msg.agreementScore > 0.7 ? '#52c41a' : '#faad14'}
              />
              <Button type="link" size="small" icon={<EyeOutlined />}>
                查看详情
              </Button>
            </Space>
          </div>
        );

      case 'refinement':
        return (
          <div style={{ padding: '12px', background: '#e6f7ff', borderRadius: '8px', border: '1px solid #91d5ff' }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
              <SyncOutlined spin style={{ color: '#1890ff', marginRight: 8 }} />
              <Text strong style={{ color: '#1890ff' }}>结果精炼</Text>
              <Tag color={getExpertColor(msg.expert)} style={{ marginLeft: 8 }}>
                {getExpertIcon(msg.expert)} {msg.expert}
              </Tag>
            </div>
            <Space direction="vertical" size="small">
              <Text>✅ 基于评审意见已精炼诊断结果</Text>
              <Text type="secondary">一致性: {(msg.agreementScore * 100).toFixed(0)}% | 评审数: {msg.reviewCount}</Text>
            </Space>
          </div>
        );

      case 'consensus':
        return (
          <div style={{ padding: '16px', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', borderRadius: '8px', color: '#fff' }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
              <ThunderboltOutlined style={{ marginRight: 8, fontSize: 20 }} />
              <Text strong style={{ color: '#fff', fontSize: 16 }}>🎉 最终共识达成</Text>
            </div>
            <Paragraph style={{ color: '#fff', marginBottom: 8 }}>{msg.content}</Paragraph>
            {msg.consensusRate && (
              <Progress 
                percent={Math.round(msg.consensusRate * 100)} 
                strokeColor="#fff"
                trailColor="rgba(255,255,255,0.3)"
              />
            )}
          </div>
        );

      default:
        return null;
    }
  };

  const getTimelineColor = (type) => {
    const colors = {
      'assignment': 'green',
      'diagnosis': 'blue',
      'review': 'gold',
      'refinement': 'cyan',
      'consensus': 'purple'
    };
    return colors[type] || 'gray';
  };

  const getTimelineDot = (type) => {
    const dots = {
      'assignment': <TeamOutlined style={{ fontSize: 16 }} />,
      'diagnosis': <RobotOutlined style={{ fontSize: 16 }} />,
      'review': <CommentOutlined style={{ fontSize: 16 }} />,
      'refinement': <SyncOutlined style={{ fontSize: 16 }} />,
      'consensus': <CheckCircleOutlined style={{ fontSize: 16 }} />
    };
    return dots[type];
  };

  const getCollaborationGraphOption = () => {
    if (!collaborationData?.experts) return {};

    const experts = collaborationData.experts.map(e => ({
      name: e.name || e.expert_type,
      category: 0
    }));

    const links = [];
    if (collaborationData.review_advices) {
      Object.entries(collaborationData.review_advices).forEach(([target, advices]) => {
        advices.forEach(advice => {
          links.push({
            source: advice.reviewer,
            target: target,
            value: advice.agreement_score
          });
        });
      });
    }

    return {
      title: {
        text: '专家协作网络',
        left: 'center',
        top: 10,
        textStyle: { fontSize: 14 }
      },
      tooltip: {
        trigger: 'item',
        formatter: (params) => {
          if (params.dataType === 'edge') {
            return `${params.data.source} → ${params.data.target}<br/>一致性: ${(params.data.value * 100).toFixed(0)}%`;
          }
          return params.data.name;
        }
      },
      series: [{
        type: 'graph',
        layout: 'force',
        data: experts,
        links: links,
        roam: true,
        label: {
          show: true,
          position: 'bottom'
        },
        force: {
          repulsion: 200,
          edgeLength: 100
        },
        lineStyle: {
          width: 2,
          curveness: 0.3
        },
        itemStyle: {
          color: (params) => getExpertColor(params.data.name)
        }
      }]
    };
  };

  if (!isVisible) return null;

  return (
    <div style={{ padding: '16px' }}>
      <Card 
        title={
          <Space>
            <TeamOutlined />
            <span>多智能体协作流程</span>
            {messages.length > 0 && (
              <Badge count={messages.length} style={{ backgroundColor: '#52c41a' }} />
            )}
          </Space>
        }
        extra={
          <Space>
            <Button 
              size="small" 
              icon={<SyncOutlined />}
              onClick={() => setAnimationEnabled(!animationEnabled)}
            >
              {animationEnabled ? '暂停动画' : '开启动画'}
            </Button>
          </Space>
        }
      >
        {/* 协作网络图 */}
        {collaborationData?.experts && (
          <div style={{ marginBottom: 16 }}>
            <ReactECharts 
              option={getCollaborationGraphOption()} 
              style={{ height: 200 }}
            />
          </div>
        )}

        {/* 消息流时间线 */}
        <Timeline
          mode="left"
          items={messages.map(msg => ({
            key: msg.id,
            color: getTimelineColor(msg.type),
            dot: getTimelineDot(msg.type),
            children: renderMessage(msg)
          }))}
        />
        
        <div ref={messageEndRef} />
      </Card>

      {/* 评审详情抽屉 */}
      <Drawer
        title={
          <Space>
            <CommentOutlined />
            <span>评审详情</span>
          </Space>
        }
        placement="right"
        width={500}
        open={reviewDrawerVisible}
        onClose={() => setReviewDrawerVisible(false)}
      >
        {selectedReview && (
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Card size="small">
              <Space>
                <Tag color={getExpertColor(selectedReview.reviewer)}>
                  {getExpertIcon(selectedReview.reviewer)} {selectedReview.reviewer}
                </Tag>
                <ArrowRightOutlined />
                <Tag color={getExpertColor(selectedReview.target)}>
                  {getExpertIcon(selectedReview.target)} {selectedReview.target}
                </Tag>
              </Space>
            </Card>

            <Card title="一致性评分" size="small">
              <Progress 
                percent={Math.round((selectedReview.agreementScore || 0.5) * 100)}
                strokeColor={selectedReview.agreementScore > 0.7 ? '#52c41a' : '#faad14'}
              />
              <Text type="secondary">
                {selectedReview.agreementScore > 0.7 ? '高度一致' : '存在分歧'}
              </Text>
            </Card>

            {selectedReview.missedCauses?.length > 0 && (
              <Card title="可能遗漏的根因" size="small">
                <List
                  size="small"
                  dataSource={selectedReview.missedCauses}
                  renderItem={item => (
                    <List.Item>
                      <ExclamationCircleOutlined style={{ color: '#faad14', marginRight: 8 }} />
                      {item}
                    </List.Item>
                  )}
                />
              </Card>
            )}

            {selectedReview.suggestions?.length > 0 && (
              <Card title="改进建议" size="small">
                <List
                  size="small"
                  dataSource={selectedReview.suggestions}
                  renderItem={item => (
                    <List.Item>
                      <BulbOutlined style={{ color: '#1890ff', marginRight: 8 }} />
                      {item}
                    </List.Item>
                  )}
                />
              </Card>
            )}

            <Card title="评审置信度" size="small">
              <Progress 
                percent={Math.round((selectedReview.reviewConfidence || 0.5) * 100)}
                strokeColor="#722ed1"
              />
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default CollaborationFlow;
