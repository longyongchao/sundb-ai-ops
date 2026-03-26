/**
 * ReasoningTreeChart - 推理过程可视化图表（毕设核心亮点）
 * Reference: D-Bot Paper Section 6 - Tree Search for LLM Diagnosis
 * 用于展示 LLM 的 Thought -> Action -> Observation 推理链
 */
import React, { useState, useMemo } from 'react';
import { Card, Tag, Progress, Tooltip, Button, Badge } from 'antd';
import {
  BulbOutlined,
  ThunderboltOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  BranchesOutlined,
  MinusOutlined
} from '@ant-design/icons';

const ReasoningTreeChart = ({ 
  data = null, 
  title = '诊断推理过程',
  height = 500 
}) => {
  const [expandedObservations, setExpandedObservations] = useState({});
  const [expandedThoughts, setExpandedThoughts] = useState({});
  const [showCachedSteps, setShowCachedSteps] = useState(false);

  const ObservationContent = ({ observation, isExpanded }) => {
    if (!observation) return null;
    
    const isJsonObject = (str) => {
      if (typeof str !== 'string') return false;
      const trimmed = str.trim();
      return (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
             (trimmed.startsWith('[') && trimmed.endsWith(']'));
    };

    const formatJsonIfPossible = (str) => {
      if (!isJsonObject(str)) return null;
      try {
        const parsed = JSON.parse(str);
        return JSON.stringify(parsed, null, 2);
      } catch (e) {
        return null;
      }
    };

    const formattedJson = formatJsonIfPossible(observation);
    
    if (formattedJson) {
      return (
        <pre style={{ 
          color: '#b7eb8f', 
          fontSize: '12px', 
          lineHeight: '1.5',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          maxHeight: isExpanded ? 'none' : '150px',
          overflow: isExpanded ? 'visible' : 'auto',
          margin: 0,
          backgroundColor: '#0d1f0d',
          padding: '8px',
          borderRadius: '4px'
        }}>
          {formattedJson}
        </pre>
      );
    }
    
    return (
      <div style={{ 
        color: '#b7eb8f', 
        fontSize: '13px', 
        lineHeight: '1.6',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        maxHeight: isExpanded ? 'none' : '150px',
        overflow: isExpanded ? 'visible' : 'hidden',
        textOverflow: isExpanded ? 'unset' : 'ellipsis'
      }}>
        {observation}
      </div>
    );
  };

  // 检测是否为缓存结果（重复调用）
  const isCachedStep = (step, allSteps, index) => {
    if (!step.observation) return false;
    const obsLower = step.observation.toLowerCase();
    if (obsLower.includes('cached') || obsLower.includes('cache hit')) {
      return true;
    }
    for (let i = 0; i < index; i++) {
      const prevStep = allSteps[i];
      if (prevStep.action === step.action && 
          JSON.stringify(prevStep.action_input) === JSON.stringify(step.action_input)) {
        return true;
      }
    }
    return false;
  };

  // 检测是否为无效推理步骤（动作参数空 + 返回无有效信息）
  const isIneffectiveStep = (step) => {
    const actionInput = step.action_input || {};
    const isEmptyActionInput = Object.keys(actionInput).length === 0;
    
    if (!step.observation) return isEmptyActionInput;
    
    const obsLower = step.observation.toLowerCase();
    const hasValidMetrics = obsLower.includes('cpu') || 
                           obsLower.includes('memory') || 
                           obsLower.includes('disk') ||
                           obsLower.includes('io') ||
                           obsLower.includes('query') ||
                           (obsLower.includes('lock') && (obsLower.includes('wait') || obsLower.includes('block'))) ||
                           obsLower.includes('connection') ||
                           obsLower.includes('cache') ||
                           obsLower.includes('transaction') ||
                           obsLower.includes('error') ||
                           obsLower.includes('异常') ||
                           obsLower.includes('问题') ||
                           obsLower.includes('发现');
    
    const onlyEmptySession = /活跃会话\s*[:：]?\s*0\s*个/.test(step.observation) && 
                             !hasValidMetrics &&
                             step.observation.length < 100;
    
    return isEmptyActionInput && onlyEmptySession;
  };

  // 处理后端返回的数据结构
  const getReasoningTreeFromData = () => {
    if (!data) return [];
    
    // 优先使用 reasoning_steps（包含quality_score等UCT信息）
    if (data.reasoning_steps && Array.isArray(data.reasoning_steps)) {
      return data.reasoning_steps.map((step, index, arr) => ({
        step: step.step,
        thought: step.thought,
        action: step.action,
        action_input: step.action_input,
        observation: step.observation,
        quality_score: step.quality_score || 0.5,
        tool_match_score: step.tool_match_score || 0.5,
        pruned: step.pruned || false,
        is_cached: isCachedStep(step, arr, index)
      }));
    }
    
    // 兼容旧格式 reasoning_tree
    if (data.reasoning_tree && Array.isArray(data.reasoning_tree)) {
      return data.reasoning_tree;
    }
    
    return [];
  };

  const reasoningTree = getReasoningTreeFromData();
  
  // 分离有效步骤、缓存步骤和无效步骤
  const { effectiveSteps, cachedSteps, ineffectiveSteps } = useMemo(() => {
    const effective = [];
    const cached = [];
    const ineffective = [];
    reasoningTree.forEach((step, index) => {
      if (step.is_cached) {
        cached.push({ ...step, originalIndex: index });
      } else if (isIneffectiveStep(step)) {
        ineffective.push({ ...step, originalIndex: index });
      } else {
        effective.push({ ...step, originalIndex: index });
      }
    });
    return { effectiveSteps: effective, cachedSteps: cached, ineffectiveSteps: ineffective };
  }, [reasoningTree]);
  
  // 显示的步骤列表（默认只显示有效步骤）
  const displaySteps = showCachedSteps ? reasoningTree : effectiveSteps;

  // 根据quality_score获取节点颜色
  const getQualityColor = (qualityScore, isPruned = false) => {
    if (isPruned) return { bg: '#2d2d2d', border: '#666', text: '#999' };
    
    if (qualityScore >= 0.9) return { bg: '#1a3a1a', border: '#52c41a', text: '#95de95' };
    if (qualityScore >= 0.7) return { bg: '#1a2a1a', border: '#73d13d', text: '#b7eb8f' };
    if (qualityScore >= 0.5) return { bg: '#2a2a1a', border: '#ffc53d', text: '#ffe58f' };
    if (qualityScore >= 0.3) return { bg: '#2a1a1a', border: '#ff7a45', text: '#ffa39e' };
    return { bg: '#2a1a1a', border: '#ff4d4f', text: '#ff7875' };
  };

  // 根据action类型获取图标和颜色
  const getActionStyle = (action) => {
    if (action === 'Finish') return { icon: <CheckCircleOutlined />, color: '#52c41a' };
    if (action.includes('query')) return { icon: <ThunderboltOutlined />, color: '#1890ff' };
    if (action.includes('metric')) return { icon: <BulbOutlined />, color: '#faad14' };
    if (action.includes('explain')) return { icon: <EyeOutlined />, color: '#722ed1' };
    return { icon: <ThunderboltOutlined />, color: '#13c2c2' };
  };

  if (reasoningTree.length === 0) {
    return (
      <Card 
        style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
        bodyStyle={{ textAlign: 'center', padding: '40px' }}
      >
        <BranchesOutlined style={{ fontSize: '48px', color: '#555', marginBottom: '16px' }} />
        <div style={{ color: '#8c8c8c' }}>暂无推理过程数据</div>
      </Card>
    );
  }

  return (
    <div style={{ backgroundColor: '#1e1e1e', padding: '20px', borderRadius: '8px' }}>
      {/* 标题 */}
      <div style={{ 
        textAlign: 'center', 
        marginBottom: '24px',
        paddingBottom: '16px',
        borderBottom: '1px solid #333'
      }}>
        <h3 style={{ color: '#1890ff', margin: 0, fontSize: '18px' }}>
          <BranchesOutlined style={{ marginRight: '8px' }} />
          {title}
        </h3>
        <div style={{ color: '#8c8c8c', fontSize: '12px', marginTop: '8px' }}>
          有效步骤 {effectiveSteps.length} 个
          {(cachedSteps.length > 0 || ineffectiveSteps.length > 0) && (
            <span style={{ marginLeft: '8px' }}>
              | 已折叠 
              {cachedSteps.length > 0 && <Tag color="orange" style={{ marginLeft: '4px' }}>{cachedSteps.length} 重复</Tag>}
              {ineffectiveSteps.length > 0 && <Tag color="default" style={{ marginLeft: '4px' }}>{ineffectiveSteps.length} 无效</Tag>}
            </span>
          )}
          {' | '}
          平均质量: {(effectiveSteps.reduce((sum, s) => sum + (s.quality_score || 0.5), 0) / (effectiveSteps.length || 1)).toFixed(2)}
        </div>
        <div style={{ 
          color: '#666', 
          fontSize: '11px', 
          marginTop: '6px',
          fontStyle: 'italic'
        }}>
          质量分说明：基于工具匹配度与推理有效性计算，分值范围 0-1，≥0.7 为高质量推理
        </div>
        {(cachedSteps.length > 0 || ineffectiveSteps.length > 0) && (
          <Button 
            type="link" 
            size="small"
            style={{ color: '#faad14', marginTop: '8px', padding: 0 }}
            onClick={() => setShowCachedSteps(!showCachedSteps)}
          >
            {showCachedSteps ? '只显示有效步骤' : `显示全部 ${reasoningTree.length} 个步骤（含重复/无效）`}
          </Button>
        )}
      </div>

      {/* 推理流程图 - 垂直布局 */}
      <div style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '16px',
        maxHeight: `${height}px`,
        overflowY: 'auto',
        paddingRight: '8px'
      }}>
        {displaySteps.map((step, index) => {
          const qualityColors = getQualityColor(step.quality_score, step.pruned);
          const actionStyle = getActionStyle(step.action);
          const isLast = index === displaySteps.length - 1;
          const isCached = step.is_cached;
          
          return (
            <div key={step.step || index} style={{ position: 'relative' }}>
              {/* 连接线 */}
              {!isLast && (
                <div style={{
                  position: 'absolute',
                  left: '24px',
                  top: '100%',
                  width: '2px',
                  height: '16px',
                  backgroundColor: step.pruned ? '#444' : (isCached ? '#faad14' : '#1890ff'),
                  zIndex: 1
                }} />
              )}
              
              {/* 步骤卡片 */}
              <Card 
                size="small"
                style={{ 
                  backgroundColor: isCached ? '#2a2a1a' : qualityColors.bg,
                  border: `2px solid ${isCached ? '#faad14' : qualityColors.border}`,
                  borderRadius: '8px',
                  opacity: (step.pruned || isCached) ? 0.7 : 1
                }}
                headStyle={{ 
                  backgroundColor: 'transparent',
                  borderBottom: '1px solid #333',
                  padding: '12px 16px'
                }}
                bodyStyle={{ padding: '16px' }}
                title={
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{
                        backgroundColor: isCached ? '#faad14' : (step.pruned ? '#666' : actionStyle.color),
                        color: '#fff',
                        padding: '4px 12px',
                        borderRadius: '4px',
                        fontSize: '13px',
                        fontWeight: 'bold'
                      }}>
                        步骤 {step.step}
                      </span>
                      <span style={{ color: '#e6e6e6', fontSize: '14px', fontWeight: 'bold' }}>
                        {actionStyle.icon} {step.action}
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {isCached && (
                        <Tag color="warning" style={{ fontSize: '11px' }}>
                          缓存结果
                        </Tag>
                      )}
                      {step.pruned && (
                        <Tag color="default" style={{ fontSize: '11px' }}>
                          已剪枝
                        </Tag>
                      )}
                    </div>
                  </div>
                }
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {/* 思考 */}
                  <div style={{ 
                    backgroundColor: '#2d2d4a', 
                    padding: '12px', 
                    borderRadius: '6px',
                    border: '1px solid #722ed1'
                  }}>
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      marginBottom: '8px',
                      color: '#b37feb',
                      fontSize: '13px',
                      fontWeight: 'bold',
                      justifyContent: 'space-between'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <BulbOutlined style={{ marginRight: '6px' }} />
                        思考
                      </div>
                      {step.thought && step.thought.length > 150 && (
                        <Button 
                          type="link" 
                          size="small"
                          style={{ color: '#b37feb', padding: 0, height: 'auto' }}
                          onClick={() => {
                            const key = `thought-${index}`;
                            setExpandedThoughts(prev => ({
                              ...prev,
                              [key]: !prev[key]
                            }));
                          }}
                        >
                          {expandedThoughts[`thought-${index}`] ? '收起' : '展开全部'}
                        </Button>
                      )}
                    </div>
                    <div style={{ 
                      color: '#d3d3ff', 
                      fontSize: '13px', 
                      lineHeight: '1.6',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: expandedThoughts[`thought-${index}`] ? 'none' : '100px',
                      overflow: expandedThoughts[`thought-${index}`] ? 'visible' : 'hidden',
                      textOverflow: expandedThoughts[`thought-${index}`] ? 'unset' : 'ellipsis'
                    }}>
                      {step.thought}
                    </div>
                  </div>

                  {/* 动作参数 */}
                  <div style={{ 
                    backgroundColor: '#1a2a3a', 
                    padding: '12px', 
                    borderRadius: '6px',
                    border: '1px solid #1890ff'
                  }}>
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      marginBottom: '8px',
                      color: '#69c0ff',
                      fontSize: '13px',
                      fontWeight: 'bold'
                    }}>
                      <ThunderboltOutlined style={{ marginRight: '6px' }} />
                      动作参数
                    </div>
                    <pre style={{ 
                      color: '#91d5ff', 
                      fontSize: '12px',
                      margin: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word'
                    }}>
                      {JSON.stringify(step.action_input, null, 2)}
                    </pre>
                  </div>

                  {/* 观察 */}
                  <div style={{ 
                    backgroundColor: '#1a3a1a', 
                    padding: '12px', 
                    borderRadius: '6px',
                    border: '1px solid #52c41a'
                  }}>
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      marginBottom: '8px',
                      color: '#95de95',
                      fontSize: '13px',
                      fontWeight: 'bold',
                      justifyContent: 'space-between'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <EyeOutlined style={{ marginRight: '6px' }} />
                        观察
                      </div>
                      {step.observation && step.observation.length > 200 && (
                        <Button 
                          type="link" 
                          size="small"
                          style={{ color: '#95de95', padding: 0, height: 'auto' }}
                          onClick={() => {
                            const key = `obs-${index}`;
                            setExpandedObservations(prev => ({
                              ...prev,
                              [key]: !prev[key]
                            }));
                          }}
                        >
                          {expandedObservations[`obs-${index}`] ? '收起' : '展开全部'}
                        </Button>
                      )}
                    </div>
                    <ObservationContent 
                      observation={step.observation} 
                      isExpanded={expandedObservations[`obs-${index}`]}
                    />
                  </div>

                  {/* 工具匹配分数 */}
                  {step.tool_match_score && (
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px',
                      marginTop: '8px'
                    }}>
                      <span style={{ color: '#8c8c8c', fontSize: '12px' }}>工具匹配度:</span>
                      <Progress 
                        percent={Math.round(step.tool_match_score * 100)} 
                        size="small" 
                        strokeColor="#722ed1"
                        style={{ flex: 1 }}
                      />
                    </div>
                  )}
                </div>
              </Card>
            </div>
          );
        })}
      </div>

      {/* 统计信息 */}
      <div style={{ 
        marginTop: '20px',
        padding: '16px',
        backgroundColor: '#252525',
        borderRadius: '8px',
        border: '1px solid #333'
      }}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-around', 
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px'
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: '#8c8c8c', fontSize: '12px', marginBottom: '4px' }}>有效步骤</div>
            <div style={{ color: '#1890ff', fontSize: '20px', fontWeight: 'bold' }}>
              {effectiveSteps.length}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: '#8c8c8c', fontSize: '12px', marginBottom: '4px' }}>平均质量</div>
            <div style={{ color: '#52c41a', fontSize: '20px', fontWeight: 'bold' }}>
              {(effectiveSteps.reduce((sum, s) => sum + (s.quality_score || 0.5), 0) / (effectiveSteps.length || 1)).toFixed(2)}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: '#8c8c8c', fontSize: '12px', marginBottom: '4px' }}>缓存命中</div>
            <div style={{ color: '#faad14', fontSize: '20px', fontWeight: 'bold' }}>
              {cachedSteps.length}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: '#8c8c8c', fontSize: '12px', marginBottom: '4px' }}>无效步骤</div>
            <div style={{ color: '#666', fontSize: '20px', fontWeight: 'bold' }}>
              {ineffectiveSteps.length}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReasoningTreeChart;
