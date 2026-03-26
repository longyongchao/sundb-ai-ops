/**
 * KnowledgePanel - 知识检索可视化面板
 * Reference: D-Bot Paper Section 5.1 - Knowledge Retrieval with BM25
 * 展示 BM25 算法检索到的相关知识块
 */
import React, { useState, useEffect } from 'react';
import { Card, Tag, Progress, Tooltip } from 'antd';
import { BookOutlined, FileSearchOutlined, LineChartOutlined, CheckCircleOutlined, TranslationOutlined, LoadingOutlined } from '@ant-design/icons';
import { translateAPI } from '@/utils/api';

interface KnowledgeItem {
  rank: number;
  bm25_score: number;
  cause_name: string;
  description: string;
  metrics: string[];
  relevance_percentage: number;
  actionable_steps: string[];
}

interface KnowledgePanelProps {
  data?: KnowledgeItem[];
  title?: string;
  showMetrics?: boolean;
}

const TranslatableText: React.FC<{ text: string; style?: React.CSSProperties }> = ({ text, style }) => {
  const [translated, setTranslated] = useState(text);
  const [isTranslating, setIsTranslating] = useState(false);
  const cacheKey = `knowledge_${text}`;
  
  useEffect(() => {
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      setTranslated(cached);
      return;
    }
    
    if (!/[\u4e00-\u9fa5]/.test(text) && text.length > 10) {
      setIsTranslating(true);
      translateAPI.translateText(text, 'zh').then(result => {
        setTranslated(result);
        sessionStorage.setItem(cacheKey, result);
        setIsTranslating(false);
      }).catch(() => {
        setIsTranslating(false);
      });
    }
  }, [text, cacheKey]);
  
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

const KnowledgePanel: React.FC<KnowledgePanelProps> = ({ 
  data = [], 
  title = '知识检索结果 (BM25 算法)',
  showMetrics = true 
}) => {
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

  const getRelevanceColor = (percentage: number) => {
    if (percentage >= 85) return '#52c41a';
    if (percentage >= 70) return '#1890ff';
    if (percentage >= 50) return '#faad14';
    return '#ff4d4f';
  };

  const avgBM25Score = data.reduce((sum, item) => sum + item.bm25_score, 0) / data.length;

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
      {/* 提示框 */}
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

      {/* 横向布局的知识卡片 */}
      <div style={{ display: 'flex', flexDirection: 'row', gap: '20px', overflowX: 'auto', paddingBottom: '12px' }}>
        {data.map((item: KnowledgeItem) => (
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
                  <span style={{ fontWeight: 'bold', color: '#e6e6e6', fontSize: '14px' }}>
                    {item.cause_name.length > 15 ? item.cause_name.substring(0, 15) + '...' : item.cause_name}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Tooltip title={`BM25分数: ${item.bm25_score.toFixed(3)}`}>
                    <span style={{ 
                      backgroundColor: getRelevanceColor(item.relevance_percentage), 
                      color: '#fff', 
                      padding: '4px 8px', 
                      borderRadius: '4px', 
                      fontSize: '12px',
                      fontWeight: 'bold'
                    }}>
                      BM25: {item.bm25_score.toFixed(2)}
                    </span>
                  </Tooltip>
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
            {/* 问题描述区域 - 增大字体，显示完整内容 */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ 
                fontSize: '13px', 
                color: '#8c8c8c', 
                marginBottom: '8px',
                fontWeight: 'bold'
              }}>
                问题描述
              </div>
              <div style={{ 
                backgroundColor: '#2d2d2d', 
                padding: '12px', 
                borderRadius: '6px',
                fontSize: '14px',
                lineHeight: '1.6',
                color: '#e6e6e6',
                border: '1px solid #444',
                wordBreak: 'break-word',
                maxHeight: '200px',
                overflowY: 'auto'
              }}>
                {item.description}
              </div>
            </div>

            {/* 中文翻译区域 - 增大字体，显示完整内容 */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ 
                backgroundColor: '#1a2a3a', 
                padding: '12px', 
                borderRadius: '6px',
                fontSize: '13px',
                lineHeight: '1.6',
                color: '#91d5ff',
                border: '1px solid #2d4a6a',
                wordBreak: 'break-word',
                maxHeight: '200px',
                overflowY: 'auto'
              }}>
                <TranslationOutlined style={{ marginRight: '6px', color: '#1890ff', fontSize: '14px' }} />
                <strong style={{ fontSize: '13px' }}>中文翻译:</strong> 
                <span style={{ marginLeft: '4px' }}>
                  <TranslatableText text={item.description} />
                </span>
              </div>
            </div>
            
            {/* 相关指标区域 */}
            {showMetrics && item.metrics && item.metrics.length > 0 && (
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
            
            {/* 诊断步骤区域 */}
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
        ))}
      </div>

      {/* 统计信息 */}
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
                高相关: {data.filter(item => item.relevance_percentage >= 85).length}
              </span>
              <span style={{ 
                backgroundColor: '#1890ff', 
                color: '#fff', 
                padding: '4px 10px', 
                borderRadius: '4px', 
                fontSize: '12px',
                fontWeight: 'bold'
              }}>
                中相关: {data.filter(item => item.relevance_percentage >= 70 && item.relevance_percentage < 85).length}
              </span>
              <span style={{ 
                backgroundColor: '#faad14', 
                color: '#fff', 
                padding: '4px 10px', 
                borderRadius: '4px', 
                fontSize: '12px',
                fontWeight: 'bold'
              }}>
                低相关: {data.filter(item => item.relevance_percentage < 70).length}
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

export default KnowledgePanel;
