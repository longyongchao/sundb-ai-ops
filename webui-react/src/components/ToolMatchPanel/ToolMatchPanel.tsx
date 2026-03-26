/**
 * ToolMatchPanel - 工具匹配可视化面板
 * Reference: D-Bot Paper Section 5.2 - Tool Matching with Sentence-BERT
 * 展示工具匹配分数和置信度分析
 */
import React from 'react';
import { Card, Tag, Progress, Descriptions, Tooltip } from 'antd';
import { ToolOutlined, CheckCircleOutlined } from '@ant-design/icons';

interface ToolMatchScore {
  step: number;
  action: string;
  sentence_bert_score: number;
  confidence_level: string;
  matched_tools: string[];
  selection_reason: string;
}

interface ToolMatchPanelProps {
  data?: ToolMatchScore[];
  title?: string;
  showDetails?: boolean;
}

const ToolMatchPanel: React.FC<ToolMatchPanelProps> = ({ 
  data = [], 
  title = '工具匹配分析 (Sentence-BERT)',
  showDetails = true 
}) => {
  // 如果数据为空，显示提示
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

  // 根据置信度获取颜色
  const getConfidenceColor = (level: string) => {
    const normalizedLevel = level?.toLowerCase() || '';
    if (normalizedLevel === 'high' || normalizedLevel.includes('高')) return '#52c41a';
    if (normalizedLevel === 'medium' || normalizedLevel.includes('中')) return '#faad14';
    if (normalizedLevel === 'low' || normalizedLevel.includes('低')) return '#ff4d4f';
    return '#8c8c8c';
  };

  // 根据分数获取颜色
  const getScoreColor = (score: number) => {
    if (score >= 0.8) return '#52c41a';
    if (score >= 0.6) return '#1890ff';
    if (score >= 0.4) return '#faad14';
    return '#ff4d4f';
  };

  // 计算统计信息
  const stats = {
    totalSteps: data.length,
    avgScore: data.reduce((sum, item) => sum + item.sentence_bert_score, 0) / data.length,
    highConfidence: data.filter(item => {
      const level = item.confidence_level?.toLowerCase() || '';
      return level === 'high' || level.includes('高');
    }).length,
    mediumConfidence: data.filter(item => {
      const level = item.confidence_level?.toLowerCase() || '';
      return level === 'medium' || level.includes('中');
    }).length,
    lowConfidence: data.filter(item => {
      const level = item.confidence_level?.toLowerCase() || '';
      return level === 'low' || level.includes('低');
    }).length,
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
        <ToolOutlined style={{ color: '#1890ff', fontSize: '18px', marginRight: '12px' }} />
        <div>
          <div style={{ fontSize: '13px', color: '#91d5ff', fontWeight: 'bold' }}>工具匹配机制</div>
          <div style={{ fontSize: '12px', color: '#6a9fcf', marginTop: '4px' }}>基于Sentence-BERT模型计算异常描述与工具库的语义相似度，为每一步诊断选择最匹配的工具</div>
        </div>
      </div>

      {/* 暗色主题的匹配统计信息 */}
      {stats && (
        <div style={{ 
          marginBottom: '16px', 
          padding: '12px', 
          backgroundColor: '#252525', 
          borderRadius: '8px', 
          border: '1px solid #333' 
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
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
              <Tag color="#52c41a" style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>高: {stats.highConfidence}</Tag>
              <Tag color="#faad14" style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>中: {stats.mediumConfidence}</Tag>
              <Tag color="#ff4d4f" style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>低: {stats.lowConfidence}</Tag>
            </div>
          </div>
        </div>
      )}

      {/* 横向布局的工具匹配卡片 */}
      <div style={{ display: 'flex', flexDirection: 'row', gap: '16px', overflowX: 'auto', paddingBottom: '8px' }}>
        {data.map((item, index) => (
          <Card 
            key={index}
            size="small" 
            style={{ 
              minWidth: '280px',
              maxWidth: '340px',
              flex: '0 0 auto',
              borderLeft: `4px solid ${getConfidenceColor(item.confidence_level)}`,
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
                <Tag color={getConfidenceColor(item.confidence_level)} style={{ fontSize: '11px', marginLeft: '4px' }}>
                  {item.confidence_level}
                </Tag>
              </div>
              <Tooltip title={`Sentence-BERT分数: ${item.sentence_bert_score.toFixed(4)}`}>
                <Progress 
                  type="circle" 
                  percent={Math.round(item.sentence_bert_score * 100)} 
                  size={28} 
                  strokeColor={getScoreColor(item.sentence_bert_score)}
                  format={() => `${Math.round(item.sentence_bert_score * 100)}%`}
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
                  {item.matched_tools.slice(0, 3).map((tool, idx) => (
                    <Tag 
                      key={idx} 
                      color="blue" 
                      style={{ fontSize: '10px', marginBottom: '2px' }}
                    >
                      {tool}
                    </Tag>
                  ))}
                  {item.matched_tools.length > 3 && (
                    <Tag style={{ fontSize: '10px' }}>
                      +{item.matched_tools.length - 3}
                    </Tag>
                  )}
                </div>
              </Descriptions.Item>
              
              {showDetails && (
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
                    {item.selection_reason}
                  </div>
                </Descriptions.Item>
              )}
            </Descriptions>
            
            <div style={{ marginTop: '8px', fontSize: '10px', color: '#666' }}>
              匹配算法: Sentence-BERT
            </div>
          </Card>
        ))}
      </div>

      {/* 暗色主题的工具匹配说明 */}
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

      {/* 暗色主题的置信度分布柱状图 */}
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

export default ToolMatchPanel;
