/**
 * 思考终端组件 - Tree Search 推理过程可视化
 * 
 * 本组件以终端风格实时展示诊断推理过程，主要功能：
 * 1. 实时输出 - 展示 LLM 的思考过程和工具调用
 * 2. 语法高亮 - 区分思考、行动、观察三种节点类型
 * 3. 自动滚动 - 跟踪最新输出内容
 * 4. 全屏模式 - 支持展开查看完整推理链
 * 
 * 设计理念：模拟终端界面，提供沉浸式的诊断过程观察体验
 */
import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { Button, Tooltip, Tag, Switch, Space } from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ClearOutlined,
  ExpandOutlined,
  CompressOutlined,
  CodeOutlined,
  BulbOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  BugOutlined,
  ConsoleSqlOutlined
} from '@ant-design/icons';

const ThinkingTerminal = ({
  output = '',
  isRunning = false,
  height = 300,
  maxHeight = 500,
  showControls = true,
  autoScroll: externalAutoScroll,
  onAutoScrollChange,
  title = 'DeepSeek 思考流'
}) => {
  const containerRef = useRef(null);
  const contentRef = useRef(null);
  const [internalAutoScroll, setInternalAutoScroll] = useState(true);
  const [isExpanded, setIsExpanded] = useState(false);
  const [showLineNumbers, setShowLineNumbers] = useState(true);
  const lastLineCountRef = useRef(0);
  const userScrolledRef = useRef(false);
  const scrollTimeoutRef = useRef(null);

  const autoScrollEnabled = externalAutoScroll !== undefined ? externalAutoScroll : internalAutoScroll;
  const setAutoScrollEnabled = onAutoScrollChange || setInternalAutoScroll;

  const lines = useMemo(() => {
    if (!output) return [];
    return output.split('\n');
  }, [output]);

  const parseLine = useCallback((line, index) => {
    const lineLower = line.toLowerCase();
    
    if (line.includes('<think') || lineLower.includes('思考:') || lineLower.includes('thinking:')) {
      return {
        type: 'think',
        icon: <BulbOutlined style={{ color: '#faad14' }} />,
        color: '#faad14',
        bgColor: 'rgba(250, 173, 20, 0.1)',
        content: line.replace(/<\/?think[^>]*>/gi, '').replace(/^(思考|Thinking)[:：]?\s*/i, '')
      };
    }
    
    if (line.includes('</think')) {
      return {
        type: 'think_end',
        icon: null,
        color: '#faad14',
        bgColor: 'transparent',
        content: ''
      };
    }
    
    if (lineLower.includes('action:') || lineLower.includes('动作:')) {
      return {
        type: 'action',
        icon: <ThunderboltOutlined style={{ color: '#1890ff' }} />,
        color: '#1890ff',
        bgColor: 'rgba(24, 144, 255, 0.1)',
        content: line.replace(/^(Action|动作)[:：]?\s*/i, '')
      };
    }
    
    if (lineLower.includes('observation:') || lineLower.includes('观察:') || lineLower.includes('结果:')) {
      return {
        type: 'observation',
        icon: <InfoCircleOutlined style={{ color: '#52c41a' }} />,
        color: '#52c41a',
        bgColor: 'rgba(82, 196, 26, 0.1)',
        content: line.replace(/^(Observation|观察|结果)[:：]?\s*/i, '')
      };
    }
    
    if (lineLower.includes('step') && (lineLower.includes('step') || /\d+/.test(line))) {
      return {
        type: 'step',
        icon: <CodeOutlined style={{ color: '#13c2c2' }} />,
        color: '#13c2c2',
        bgColor: 'rgba(19, 194, 194, 0.1)',
        content: line
      };
    }
    
    if (lineLower.includes('error') || lineLower.includes('错误') || lineLower.includes('失败')) {
      return {
        type: 'error',
        icon: <WarningOutlined style={{ color: '#ff4d4f' }} />,
        color: '#ff4d4f',
        bgColor: 'rgba(255, 77, 79, 0.1)',
        content: line
      };
    }
    
    if (lineLower.includes('warning') || lineLower.includes('警告')) {
      return {
        type: 'warning',
        icon: <WarningOutlined style={{ color: '#faad14' }} />,
        color: '#faad14',
        bgColor: 'rgba(250, 173, 20, 0.1)',
        content: line
      };
    }
    
    if (lineLower.includes('success') || lineLower.includes('成功') || lineLower.includes('完成')) {
      return {
        type: 'success',
        icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
        color: '#52c41a',
        bgColor: 'rgba(82, 196, 26, 0.1)',
        content: line
      };
    }
    
    if (lineLower.includes('root_cause') || lineLower.includes('根因') || lineLower.includes('诊断结果')) {
      return {
        type: 'result',
        icon: <CheckCircleOutlined style={{ color: '#722ed1' }} />,
        color: '#722ed1',
        bgColor: 'rgba(114, 46, 209, 0.1)',
        content: line
      };
    }
    
    if (lineLower.includes('query') || lineLower.includes('sql') || lineLower.includes('select')) {
      return {
        type: 'sql',
        icon: <ConsoleSqlOutlined style={{ color: '#eb2f96' }} />,
        color: '#eb2f96',
        bgColor: 'rgba(235, 47, 150, 0.05)',
        content: line
      };
    }
    
    if (lineLower.includes('debug') || lineLower.includes('调试')) {
      return {
        type: 'debug',
        icon: <BugOutlined style={{ color: '#8c8c8c' }} />,
        color: '#8c8c8c',
        bgColor: 'transparent',
        content: line
      };
    }
    
    return {
      type: 'normal',
      icon: null,
      color: '#d0d0d0',
      bgColor: 'transparent',
      content: line
    };
  }, []);

  const scrollToBottom = useCallback((smooth = true) => {
    if (contentRef.current && autoScrollEnabled && !userScrolledRef.current) {
      contentRef.current.scrollTo({
        top: contentRef.current.scrollHeight,
        behavior: smooth ? 'smooth' : 'auto'
      });
    }
  }, [autoScrollEnabled]);

  useEffect(() => {
    const currentLineCount = lines.length;
    
    if (currentLineCount !== lastLineCountRef.current) {
      lastLineCountRef.current = currentLineCount;
      scrollToBottom(false);
    }
  }, [lines.length, scrollToBottom]);

  useEffect(() => {
    if (isRunning && autoScrollEnabled) {
      userScrolledRef.current = false;
    }
  }, [isRunning, autoScrollEnabled]);

  const handleScroll = useCallback((e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.target;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    
    if (!isAtBottom && autoScrollEnabled) {
      userScrolledRef.current = true;
      
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
      
      scrollTimeoutRef.current = setTimeout(() => {
        userScrolledRef.current = false;
      }, 3000);
    }
  }, [autoScrollEnabled]);

  const handleManualScrollToBottom = useCallback(() => {
    userScrolledRef.current = false;
    if (contentRef.current) {
      contentRef.current.scrollTo({
        top: contentRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, []);

  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  const currentHeight = isExpanded ? maxHeight : height;

  return (
    <div
      ref={containerRef}
      style={{
        backgroundColor: '#0d1117',
        borderRadius: '8px',
        border: '1px solid #30363d',
        overflow: 'hidden',
        fontFamily: '"Cascadia Code", "Fira Code", "Consolas", monospace',
        fontSize: '13px',
        lineHeight: '1.6'
      }}
    >
      <div
        style={{
          backgroundColor: '#161b22',
          borderBottom: '1px solid #30363d',
          padding: '8px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              backgroundColor: isRunning ? '#52c41a' : '#8c8c8c',
              animation: isRunning ? 'pulse 1.5s infinite' : 'none'
            }}
          />
          <span style={{ color: '#8b949e', fontWeight: 500 }}>{title}</span>
          {isRunning && (
            <Tag color="processing" style={{ marginLeft: '8px' }}>
              <LoadingOutlined spin style={{ marginRight: '4px' }} />
              运行中
            </Tag>
          )}
          <span style={{ color: '#6e7681', fontSize: '12px', marginLeft: '8px' }}>
            {lines.length} 行
          </span>
        </div>
        
        {showControls && (
          <Space size="small">
            <Tooltip title={autoScrollEnabled ? '暂停自动滚动' : '恢复自动滚动'}>
              <Button
                type="text"
                size="small"
                icon={autoScrollEnabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                onClick={() => setAutoScrollEnabled(!autoScrollEnabled)}
                style={{ color: autoScrollEnabled ? '#52c41a' : '#8b949e' }}
              />
            </Tooltip>
            
            <Tooltip title="滚动到底部">
              <Button
                type="text"
                size="small"
                icon={<ExpandOutlined rotate={180} />}
                onClick={handleManualScrollToBottom}
                style={{ color: '#8b949e' }}
              />
            </Tooltip>
            
            <Tooltip title={isExpanded ? '收起' : '展开'}>
              <Button
                type="text"
                size="small"
                icon={isExpanded ? <CompressOutlined /> : <ExpandOutlined />}
                onClick={() => setIsExpanded(!isExpanded)}
                style={{ color: '#8b949e' }}
              />
            </Tooltip>
            
            <Tooltip title="行号">
              <Switch
                size="small"
                checked={showLineNumbers}
                onChange={setShowLineNumbers}
                style={{ transform: 'scale(0.8)' }}
              />
            </Tooltip>
          </Space>
        )}
      </div>

      <div
        ref={contentRef}
        onScroll={handleScroll}
        style={{
          height: currentHeight,
          maxHeight: maxHeight,
          overflow: 'auto',
          padding: '12px 0',
          backgroundColor: '#0d1117'
        }}
      >
        {lines.length === 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              minHeight: '180px',
              padding: '24px',
              background: isRunning 
                ? 'linear-gradient(135deg, rgba(88, 166, 255, 0.05) 0%, rgba(24, 144, 255, 0.08) 100%)'
                : 'transparent'
            }}
          >
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '12px',
              backgroundColor: isRunning ? 'rgba(24, 144, 255, 0.15)' : 'rgba(139, 148, 158, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '20px',
              border: isRunning ? '2px solid rgba(24, 144, 255, 0.3)' : '1px solid rgba(139, 148, 158, 0.2)'
            }}>
              {isRunning ? (
                <LoadingOutlined style={{ fontSize: '28px', color: '#58a6ff' }} spin />
              ) : (
                <CodeOutlined style={{ fontSize: '28px', color: '#8b949e' }} />
              )}
            </div>
            <div style={{ 
              color: isRunning ? '#58a6ff' : '#c9d1d9', 
              fontSize: '16px', 
              fontWeight: 500,
              marginBottom: '8px'
            }}>
              {isRunning ? 'DeepSeek 正在思考...' : '等待诊断输出'}
            </div>
            <div style={{ 
              color: '#8b949e', 
              fontSize: '13px',
              maxWidth: '300px',
              textAlign: 'center',
              lineHeight: '1.6'
            }}>
              {isRunning 
                ? '模型正在分析异常数据，推理过程将实时显示在此处' 
                : '上传诊断文件并点击"开始诊断"后，思考流将在此实时显示'}
            </div>
            {isRunning && (
              <div style={{
                marginTop: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: '#6e7681',
                fontSize: '12px'
              }}>
                <span style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: '#52c41a',
                  animation: 'pulse 1.5s infinite'
                }} />
                <span>正在连接模型服务...</span>
              </div>
            )}
          </div>
        ) : (
          lines.map((line, index) => {
            const parsed = parseLine(line, index);
            
            return (
              <div
                key={index}
                style={{
                  display: 'flex',
                  backgroundColor: parsed.bgColor,
                  transition: 'background-color 0.2s'
                }}
              >
                {showLineNumbers && (
                  <div
                    style={{
                      width: '50px',
                      minWidth: '50px',
                      paddingRight: '12px',
                      textAlign: 'right',
                      color: '#484f58',
                      userSelect: 'none',
                      borderRight: '1px solid #21262d',
                      marginRight: '12px'
                    }}
                  >
                    {index + 1}
                  </div>
                )}
                
                <div
                  style={{
                    flex: 1,
                    paddingRight: '16px',
                    color: parsed.color,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word'
                  }}
                >
                  {parsed.icon && (
                    <span style={{ marginRight: '8px' }}>
                      {parsed.icon}
                    </span>
                  )}
                  {parsed.content}
                </div>
              </div>
            );
          })
        )}
        
        {isRunning && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              color: '#58a6ff',
              backgroundColor: 'rgba(88, 166, 255, 0.05)'
            }}
          >
            <LoadingOutlined spin />
            <span>等待更多输出...</span>
          </div>
        )}
      </div>

      <style>
        {`
          @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
          }
          
          ${containerRef.current ? `#${containerRef.current.id}` : ''} ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
          }
          
          ::-webkit-scrollbar-track {
            background: #0d1117;
          }
          
          ::-webkit-scrollbar-thumb {
            background: #30363d;
            border-radius: 4px;
          }
          
          ::-webkit-scrollbar-thumb:hover {
            background: #484f58;
          }
        `}
      </style>
    </div>
  );
};

export default React.memo(ThinkingTerminal);
