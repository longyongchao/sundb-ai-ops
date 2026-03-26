import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { CopyOutlined, CheckOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { message, Tooltip, Button } from 'antd';

const SqlHighlight = ({ 
  sql, 
  showCopy = true, 
  showExecute = false,
  onExecute,
  maxHeight = '300px',
  language = 'sql'
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      message.success('SQL 已复制到剪贴板');
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      message.error('复制失败');
    }
  };

  if (!sql || sql.trim().startsWith('--')) {
    return (
      <div style={{
        backgroundColor: '#1e1e1e',
        padding: '12px 16px',
        borderRadius: '6px',
        color: '#888',
        fontSize: '13px',
        fontFamily: 'Consolas, Monaco, monospace'
      }}>
        {sql || '-- 暂无 SQL'}
      </div>
    );
  }

  return (
    <div style={{ position: 'relative' }}>
      {(showCopy || showExecute) && (
        <div style={{
          position: 'absolute',
          top: '8px',
          right: '8px',
          zIndex: 10,
          display: 'flex',
          gap: '8px'
        }}>
          {showCopy && (
            <Tooltip title={copied ? '已复制' : '复制 SQL'}>
              <Button
                size="small"
                type="text"
                icon={copied ? <CheckOutlined style={{ color: '#52c41a' }} /> : <CopyOutlined style={{ color: '#888' }} />}
                onClick={handleCopy}
                style={{ backgroundColor: 'rgba(255,255,255,0.1)' }}
              />
            </Tooltip>
          )}
          {showExecute && onExecute && (
            <Tooltip title="执行 SQL">
              <Button
                size="small"
                type="text"
                icon={<PlayCircleOutlined style={{ color: '#1890ff' }} />}
                onClick={() => onExecute(sql)}
                style={{ backgroundColor: 'rgba(255,255,255,0.1)' }}
              />
            </Tooltip>
          )}
        </div>
      )}
      <SyntaxHighlighter
        language={language}
        style={vscDarkPlus}
        customStyle={{
          margin: 0,
          borderRadius: '6px',
          maxHeight: maxHeight,
          overflow: 'auto',
          fontSize: '13px',
          backgroundColor: '#1e1e1e'
        }}
        showLineNumbers={sql.split('\n').length > 3}
        wrapLines={true}
        wrapLongLines={true}
      >
        {sql}
      </SyntaxHighlighter>
    </div>
  );
};

export default SqlHighlight;
