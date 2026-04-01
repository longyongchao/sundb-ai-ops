/**
 * SunDB TRC 故障事件面板组件
 * 
 * 功能：
 * 1. 以表格形式展示故障事件列表
 * 2. 支持按严重程度和事件类型筛选
 * 3. 可展开行显示原始日志片段
 * 
 * @component
 */
import React, { useState, useMemo } from 'react';
import {
  Table, Card, Tag, Select, Space, Tooltip, Typography, Descriptions, Empty
} from 'antd';
import {
  ExclamationCircleOutlined, WarningOutlined, InfoCircleOutlined,
  BugOutlined, DatabaseOutlined, SafetyOutlined, ApiOutlined
} from '@ant-design/icons';

const { Option } = Select;
const { Text, Paragraph } = Typography;

const SEVERITY_CONFIG = {
  critical: { color: '#ff4d4f', icon: <ExclamationCircleOutlined />, text: '严重' },
  high: { color: '#fa8c16', icon: <WarningOutlined />, text: '高' },
  medium: { color: '#faad14', icon: <InfoCircleOutlined />, text: '中' },
  low: { color: '#52c41a', icon: <InfoCircleOutlined />, text: '低' }
};

const EVENT_TYPE_CONFIG = {
  FATAL: { color: '#ff4d4f', icon: <BugOutlined />, text: '致命错误' },
  DEADLOCK: { color: '#fa8c16', icon: <DatabaseOutlined />, text: '死锁' },
  DDL_FAILURE: { color: '#faad14', icon: <DatabaseOutlined />, text: 'DDL失败' },
  AUTH_FAILURE: { color: '#722ed1', icon: <SafetyOutlined />, text: '认证失败' },
  LISTENER_FAILURE: { color: '#13c2c2', icon: <ApiOutlined />, text: '监听器失败' }
};

const TrcFaultPanel = ({ 
  faults = [], 
  loading = false,
  title = 'SunDB 故障事件',
  showFilters = true 
}) => {
  const [severityFilter, setSeverityFilter] = useState(null);
  const [eventTypeFilter, setEventTypeFilter] = useState(null);

  const filteredFaults = useMemo(() => {
    if (!faults || faults.length === 0) return [];
    
    let result = [...faults];
    
    if (severityFilter) {
      result = result.filter(f => f.severity === severityFilter);
    }
    
    if (eventTypeFilter) {
      result = result.filter(f => f.event_type === eventTypeFilter);
    }
    
    return result;
  }, [faults, severityFilter, eventTypeFilter]);

  const uniqueEventTypes = useMemo(() => {
    if (!faults || faults.length === 0) return [];
    return [...new Set(faults.map(f => f.event_type))];
  }, [faults]);

  const columns = [
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity) => {
        const config = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.low;
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      },
      filters: Object.entries(SEVERITY_CONFIG).map(([key, val]) => ({
        text: val.text,
        value: key
      })),
      onFilter: (value, record) => record.severity === value
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (ts) => <Text style={{ fontSize: '12px', color: '#8c8c8c' }}>{ts}</Text>
    },
    {
      title: '节点',
      dataIndex: 'instance',
      key: 'instance',
      width: 80,
      render: (instance) => (
        <Tag color="blue">{instance || 'N/A'}</Tag>
      )
    },
    {
      title: '类型',
      dataIndex: 'event_type',
      key: 'event_type',
      width: 120,
      render: (type) => {
        const config = EVENT_TYPE_CONFIG[type] || { color: '#666', icon: <BugOutlined />, text: type };
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      }
    },
    {
      title: '错误码',
      dataIndex: 'error_code',
      key: 'error_code',
      width: 150,
      render: (code) => code ? (
        <Tooltip title={code}>
          <Text code style={{ fontSize: '11px' }}>{code}</Text>
        </Tooltip>
      ) : <Text type="secondary">-</Text>
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc) => (
        <Tooltip title={desc}>
          <Text style={{ fontSize: '12px' }}>
            {desc && desc.length > 50 ? `${desc.substring(0, 50)}...` : desc}
          </Text>
        </Tooltip>
      )
    }
  ];

  const expandedRowRender = (record) => {
    return (
      <div style={{ 
        padding: '12px 16px', 
        backgroundColor: '#1a1a1a', 
        borderRadius: '4px',
        border: '1px solid #333'
      }}>
        <Descriptions size="small" column={2} labelStyle={{ color: '#8c8c8c' }}>
          <Descriptions.Item label="事件ID">{record.event_id || '-'}</Descriptions.Item>
          <Descriptions.Item label="错误消息">{record.error_message || '-'}</Descriptions.Item>
        </Descriptions>
        
        {record.raw_log_snippet && (
          <div style={{ marginTop: '12px' }}>
            <Text type="secondary" style={{ fontSize: '12px', marginBottom: '8px', display: 'block' }}>
              原始日志片段:
            </Text>
            <Paragraph
              style={{
                backgroundColor: '#0d1117',
                padding: '12px',
                borderRadius: '4px',
                fontSize: '11px',
                fontFamily: 'Consolas, Monaco, monospace',
                color: '#c9d1d9',
                margin: 0,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                maxHeight: '200px',
                overflow: 'auto'
              }}
            >
              {record.raw_log_snippet}
            </Paragraph>
          </div>
        )}
      </div>
    );
  };

  const stats = useMemo(() => {
    if (!faults || faults.length === 0) return null;
    
    const bySeverity = {};
    const byType = {};
    
    faults.forEach(f => {
      bySeverity[f.severity] = (bySeverity[f.severity] || 0) + 1;
      byType[f.event_type] = (byType[f.event_type] || 0) + 1;
    });
    
    return { bySeverity, byType, total: faults.length };
  }, [faults]);

  return (
    <Card
      title={
        <span>
          <BugOutlined style={{ marginRight: '8px', color: '#ff4d4f' }} />
          {title}
          {stats && (
            <Tag color="red" style={{ marginLeft: '8px' }}>
              {stats.total} 个故障
            </Tag>
          )}
        </span>
      }
      extra={
        showFilters && (
          <Space>
            <Select
              placeholder="严重程度"
              style={{ width: 100 }}
              allowClear
              value={severityFilter}
              onChange={setSeverityFilter}
              size="small"
            >
              {Object.entries(SEVERITY_CONFIG).map(([key, val]) => (
                <Option key={key} value={key}>{val.text}</Option>
              ))}
            </Select>
            <Select
              placeholder="事件类型"
              style={{ width: 120 }}
              allowClear
              value={eventTypeFilter}
              onChange={setEventTypeFilter}
              size="small"
            >
              {uniqueEventTypes.map(type => (
                <Option key={type} value={type}>{EVENT_TYPE_CONFIG[type]?.text || type}</Option>
              ))}
            </Select>
          </Space>
        )
      }
      style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
      headStyle={{ backgroundColor: '#1e1e1e', borderBottom: '1px solid #333' }}
      bodyStyle={{ backgroundColor: '#1e1e1e', padding: '12px' }}
    >
      {stats && (
        <div style={{ 
          marginBottom: '12px', 
          padding: '8px 12px', 
          backgroundColor: '#252525', 
          borderRadius: '4px',
          display: 'flex',
          gap: '16px',
          flexWrap: 'wrap'
        }}>
          {Object.entries(stats.bySeverity).map(([severity, count]) => {
            const config = SEVERITY_CONFIG[severity];
            return (
              <Tag key={severity} color={config?.color || '#666'}>
                {config?.text || severity}: {count}
              </Tag>
            );
          })}
        </div>
      )}

      <Table
        dataSource={filteredFaults}
        columns={columns}
        rowKey={(record, index) => record.event_id || record.timestamp || `fault-${index}`}
        loading={loading}
        size="small"
        expandable={{
          expandedRowRender,
          rowExpandable: (record) => record.description || record.raw_log_snippet || record.message
        }}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          size: 'small'
        }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无故障事件"
              style={{ padding: '20px 0' }}
            />
          )
        }}
        style={{ backgroundColor: 'transparent' }}
        scroll={{ x: 800 }}
      />
    </Card>
  );
};

export default TrcFaultPanel;
