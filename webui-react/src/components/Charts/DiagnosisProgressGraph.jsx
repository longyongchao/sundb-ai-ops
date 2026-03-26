/**
 * DiagnosisProgressGraph - 实时诊断过程拓扑图
 * 在诊断过程中实时展示推理步骤的拓扑结构
 */
import React, { useRef, useMemo, useState } from 'react';
import { Card, Tag, Progress, Badge, Button } from 'antd';
import {
  BulbOutlined,
  ThunderboltOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  BranchesOutlined,
  SyncOutlined,
  ToolOutlined,
  FileSearchOutlined,
  MinusOutlined
} from '@ant-design/icons';

const DiagnosisProgressGraph = ({ 
  isDiagnosing = false,
  steps = [],
  currentStep = 0,
  height = 400 
}) => {
  const containerRef = useRef(null);
  const [showCachedSteps, setShowCachedSteps] = useState(false);

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

  // 检测是否为无效推理步骤
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

  // 为每个步骤添加缓存标记
  const processedSteps = useMemo(() => {
    return steps.map((step, index) => ({
      ...step,
      is_cached: isCachedStep(step, steps, index)
    }));
  }, [steps]);

  // 分离有效步骤、缓存步骤和无效步骤
  const { effectiveSteps, cachedSteps, ineffectiveSteps } = useMemo(() => {
    const effective = [];
    const cached = [];
    const ineffective = [];
    processedSteps.forEach((step, index) => {
      if (step.is_cached) {
        cached.push({ ...step, originalIndex: index });
      } else if (isIneffectiveStep(step)) {
        ineffective.push({ ...step, originalIndex: index });
      } else {
        effective.push({ ...step, originalIndex: index });
      }
    });
    return { effectiveSteps: effective, cachedSteps: cached, ineffectiveSteps: ineffective };
  }, [processedSteps]);

  // 显示的步骤列表
  const displaySteps = showCachedSteps ? processedSteps : effectiveSteps;

  // 为显示的步骤重新编号（连续编号）
  const numberedDisplaySteps = useMemo(() => {
    return displaySteps.map((step, displayIndex) => ({
      ...step,
      displayStepNumber: displayIndex + 1  // 连续编号
    }));
  }, [displaySteps]);

  const getActionIcon = (action) => {
    if (action === 'Finish') return <CheckCircleOutlined />;
    if (action?.includes('query')) return <ThunderboltOutlined />;
    if (action?.includes('metric')) return <BulbOutlined />;
    if (action?.includes('explain')) return <EyeOutlined />;
    if (action?.includes('lock')) return <ToolOutlined />;
    if (action?.includes('session')) return <FileSearchOutlined />;
    return <ThunderboltOutlined />;
  };

  const getActionColor = (action, status) => {
    if (status === 'running') return '#1890ff';
    if (status === 'completed') return '#52c41a';
    if (status === 'error') return '#ff4d4f';
    if (action === 'Finish') return '#52c41a';
    if (action?.includes('query')) return '#1890ff';
    if (action?.includes('metric')) return '#faad14';
    if (action?.includes('explain')) return '#722ed1';
    return '#13c2c2';
  };

  const getStatusBadge = (status, index) => {
    if (status === 'running') {
      return (
        <Badge 
          status="processing" 
          text={<span style={{ color: '#1890ff' }}>执行中</span>}
        />
      );
    }
    if (status === 'completed') {
      return (
        <Badge 
          status="success" 
          text={<span style={{ color: '#52c41a' }}>已完成</span>}
        />
      );
    }
    if (status === 'error') {
      return (
        <Badge 
          status="error" 
          text={<span style={{ color: '#ff4d4f' }}>失败</span>}
        />
      );
    }
    return (
      <Badge 
        status="default" 
        text={<span style={{ color: '#666' }}>等待中</span>}
      />
    );
  };

  if (steps.length === 0) {
    return (
      <Card 
        style={{ backgroundColor: '#1e1e1e', border: '1px solid #333', height }}
        styles={{ 
          body: {
            display: 'flex', 
            flexDirection: 'column',
            alignItems: 'center', 
            justifyContent: 'center',
            height: '100%'
          }
        }}
      >
        <BranchesOutlined style={{ fontSize: '48px', color: '#555', marginBottom: '16px' }} />
        <div style={{ color: '#8c8c8c', fontSize: '16px' }}>等待开始诊断...</div>
        <div style={{ color: '#666', fontSize: '12px', marginTop: '8px' }}>
          诊断开始后将实时显示推理过程
        </div>
      </Card>
    );
  }

  return (
    <div 
      ref={containerRef}
      style={{ 
        backgroundColor: '#1e1e1e', 
        borderRadius: '8px',
        padding: '20px',
        height,
        overflow: 'auto'
      }}
    >
      {/* 标题 */}
      <div style={{ 
        textAlign: 'center', 
        marginBottom: '24px',
        paddingBottom: '16px',
        borderBottom: '1px solid #333'
      }}>
        <h3 style={{ color: '#1890ff', margin: 0, fontSize: '18px' }}>
          {isDiagnosing ? (
            <><SyncOutlined spin style={{ marginRight: '8px' }} />诊断进行中...</>
          ) : (
            <><CheckCircleOutlined style={{ marginRight: '8px', color: '#52c41a' }} />诊断完成</>
          )}
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
        </div>
        {(cachedSteps.length > 0 || ineffectiveSteps.length > 0) && (
          <Button 
            type="link" 
            size="small"
            style={{ color: '#faad14', marginTop: '8px', padding: 0 }}
            onClick={() => setShowCachedSteps(!showCachedSteps)}
          >
            {showCachedSteps ? '只显示有效步骤' : `显示全部 ${processedSteps.length} 个步骤（含重复/无效）`}
          </Button>
        )}
      </div>

      {/* 推理步骤拓扑图 */}
      <div style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '16px',
        position: 'relative'
      }}>
        {numberedDisplaySteps.map((step, index) => {
          const isLast = index === numberedDisplaySteps.length - 1;
          const isRunning = isLast && isDiagnosing;
          const status = isRunning ? 'running' : 'completed';
          const actionColor = getActionColor(step.action, status);
          const isCached = step.is_cached;

          return (
            <div key={step.originalIndex || index} style={{ position: 'relative' }}>
              {/* 连接线 */}
              {index > 0 && (
                <div style={{
                  position: 'absolute',
                  left: '24px',
                  top: '-16px',
                  width: '2px',
                  height: '16px',
                  backgroundColor: numberedDisplaySteps[index - 1]?.status === 'error' ? '#ff4d4f' : 
                                   (numberedDisplaySteps[index - 1]?.is_cached ? '#faad14' : '#333')
                }} />
              )}

              {/* 步骤卡片 */}
              <div 
                style={{
                  backgroundColor: isCached ? '#2a2a1a' : (isRunning ? '#1a2a3a' : '#2d2d2d'),
                  border: `1px solid ${isCached ? '#faad14' : (isRunning ? '#1890ff' : '#333')}`,
                  borderRadius: '8px',
                  padding: '16px',
                  position: 'relative',
                  transition: 'all 0.3s ease',
                  boxShadow: isRunning ? '0 0 10px rgba(24, 144, 255, 0.3)' : 'none',
                  opacity: isCached ? 0.7 : 1
                }}
              >
                {/* 步骤头部 */}
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'space-between',
                  marginBottom: '12px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '50%',
                      backgroundColor: `${actionColor}20`,
                      border: `2px solid ${actionColor}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: actionColor,
                      fontSize: '20px'
                    }}>
                      {isRunning ? <LoadingOutlined /> : getActionIcon(step.action)}
                    </div>
                    <div>
                      <div style={{ color: '#e6e6e6', fontWeight: 'bold', fontSize: '14px' }}>
                        步骤 {step.displayStepNumber || step.step || index + 1}
                      </div>
                      <Tag color={actionColor} style={{ marginTop: '4px' }}>
                        {step.action || '分析中'}
                      </Tag>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {isCached && (
                      <Tag color="warning" style={{ fontSize: '11px' }}>
                        缓存结果
                      </Tag>
                    )}
                    {getStatusBadge(status, index)}
                  </div>
                </div>

                {/* 思考内容 */}
                {step.thought && (
                  <div style={{ 
                    backgroundColor: '#1a1a1a', 
                    padding: '12px', 
                    borderRadius: '6px',
                    marginBottom: '12px',
                    border: '1px solid #333'
                  }}>
                    <div style={{ color: '#8c8c8c', fontSize: '12px', marginBottom: '4px' }}>
                      思考
                    </div>
                    <pre style={{ 
                      color: '#d0d0d0', 
                      fontSize: '13px', 
                      lineHeight: '1.6',
                      margin: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: '150px',
                      overflow: 'auto'
                    }}>
                      {step.thought}
                    </pre>
                  </div>
                )}

                {/* 动作参数 */}
                {step.action_input && Object.keys(step.action_input).length > 0 && (
                  <div style={{ 
                    backgroundColor: '#1a2a1a', 
                    padding: '8px 12px', 
                    borderRadius: '6px',
                    marginBottom: '12px',
                    border: '1px solid #2d5a2d'
                  }}>
                    <div style={{ color: '#8c8c8c', fontSize: '12px', marginBottom: '4px' }}>
                      动作参数
                    </div>
                    <pre style={{ 
                      margin: 0, 
                      color: '#91d5ff', 
                      fontSize: '12px',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all'
                    }}>
                      {JSON.stringify(step.action_input, null, 2)}
                    </pre>
                  </div>
                )}

                {/* 观察结果 */}
                {step.observation && !isRunning && (
                  <div style={{ 
                    backgroundColor: '#1a1a2a', 
                    padding: '12px', 
                    borderRadius: '6px',
                    border: '1px solid #2d2d5a'
                  }}>
                    <div style={{ color: '#8c8c8c', fontSize: '12px', marginBottom: '4px' }}>
                      观察
                    </div>
                    <pre style={{ 
                      color: '#b0b0b0', 
                      fontSize: '12px', 
                      lineHeight: '1.6',
                      margin: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: '200px',
                      overflow: 'auto'
                    }}>
                      {step.observation}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* 正在执行的步骤（动画效果） */}
        {isDiagnosing && (
          <div style={{
            backgroundColor: '#1a2a3a',
            border: '1px dashed #1890ff',
            borderRadius: '8px',
            padding: '16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px'
          }}>
            <LoadingOutlined style={{ color: '#1890ff', fontSize: '20px' }} />
            <span style={{ color: '#1890ff' }}>正在生成下一步推理...</span>
          </div>
        )}
      </div>

      {/* 进度条 */}
      <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid #333' }}>
        <Progress 
          percent={Math.min(100, Math.round((effectiveSteps.length / 8) * 100))}
          status={isDiagnosing ? 'active' : 'success'}
          strokeColor={{ '0%': '#108ee9', '100%': '#87d068' }}
        />
        <div style={{ textAlign: 'center', color: '#8c8c8c', fontSize: '12px', marginTop: '8px' }}>
          {isDiagnosing ? '诊断进度' : '诊断完成'} - 有效推理步骤: {effectiveSteps.length}
        </div>
      </div>
    </div>
  );
};

export default React.memo(DiagnosisProgressGraph, (prevProps, nextProps) => {
  return (
    prevProps.isDiagnosing === nextProps.isDiagnosing &&
    prevProps.currentStep === nextProps.currentStep &&
    prevProps.steps?.length === nextProps.steps?.length &&
    JSON.stringify(prevProps.steps) === JSON.stringify(nextProps.steps)
  );
});
