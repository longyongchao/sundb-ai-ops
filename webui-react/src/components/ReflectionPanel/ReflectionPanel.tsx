/**
 * ReflectionPanel - 反思过程展示面板
 * Reference: D-Bot Paper Section 6.3 - Reflection Mechanism
 * 展示诊断过程中的反思洞察和修正建议
 */
import React from 'react';
import { Card, Tag, Descriptions, Tooltip, Progress } from 'antd';
import { SyncOutlined, BulbOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';

interface ReflectionInsight {
  step: number;
  trigger: string;
  insight: string;
  recommended_action: string;
  confidence: number;
}

interface ReflectionPanelProps {
  data?: ReflectionInsight[];
  title?: string;
  showConfidence?: boolean;
}

const ReflectionPanel: React.FC<ReflectionPanelProps> = ({ 
  data = [], 
  title = '反思过程 (Reflection Mechanism)',
  showConfidence = true 
}) => {
  // 如果数据为空，显示提示
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

  // 根据置信度获取颜色
  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return '#52c41a';
    if (confidence >= 0.7) return '#1890ff';
    if (confidence >= 0.5) return '#faad14';
    return '#ff4d4f';
  };

  // 根据触发类型获取图标
  const getTriggerIcon = (trigger: string) => {
    if (trigger.includes('Low quality') || trigger.includes('错误')) {
      return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
    }
    if (trigger.includes('Key decision') || trigger.includes('关键')) {
      return <BulbOutlined style={{ color: '#1890ff' }} />;
    }
    return <SyncOutlined style={{ color: '#faad14' }} />;
  };

  // 根据触发类型获取标签颜色 - 使用自定义颜色而非预设颜色
  const getTriggerTagStyle = (trigger: string): React.CSSProperties => {
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
      {/* 暗色主题的提示框 */}
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

      {/* 横向布局的反思卡片 */}
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
              {showConfidence && (
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
              )}
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
                  <span>{insight.recommended_action}</span>
                </div>
              </Descriptions.Item>
            </Descriptions>
            
            <div style={{ marginTop: '8px', fontSize: '10px', color: '#666' }}>
              反思算法: Self-Reflection Prompt
            </div>
          </Card>
        ))}
      </div>

      {/* 暗色主题的反思统计信息 */}
      <div style={{ marginTop: '16px', padding: '12px', backgroundColor: '#252525', borderRadius: '8px', border: '1px solid #333' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
            <div>
              <span style={{ color: '#8c8c8c' }}>反思统计:</span>
              <span style={{ marginLeft: '8px', color: '#91d5ff', fontWeight: 'bold' }}>
                平均触发间隔: {data.length > 1 ? Math.round((data[data.length-1].step - data[0].step) / (data.length - 1)) : 'N/A'} 步
              </span>
            </div>
            <div>
              <span style={{ color: '#b7eb8f', fontWeight: 'bold' }}>
                平均置信度: {(data.reduce((sum, item) => sum + item.confidence, 0) / data.length).toFixed(3)}
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

      {/* 暗色主题的反思类型分布 */}
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
            const triggerCounts: Record<string, number> = {};
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

      {/* 暗色主题的反思效果评估 */}
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
              共 {data.length} 次反思触发，平均在步骤 {Math.round(data.reduce((sum, item) => sum + item.step, 0) / data.length)} 触发，有效修正推理路径。
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
};

export default ReflectionPanel;
