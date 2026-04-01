/**
 * SunDB TRC 时间线面板组件
 * 
 * 功能：
 * 1. 跨文件统一时间线视图
 * 2. 按日志级别着色
 * 3. 支持按节点、级别、时间范围筛选
 * 
 * @component
 */
import React, { useState, useMemo } from 'react';
import {
  Card, Timeline, Tag, Select, Space, Input, Typography, Empty, Tooltip, Badge
} from 'antd';
import {
  ClockCircleOutlined, ExclamationCircleOutlined, WarningOutlined,
  InfoCircleOutlined, DatabaseOutlined, ApiOutlined, SearchOutlined
} from '@ant-design/icons';

const { Option } = Select;
const { Text, Paragraph } = Typography;
const { RangePicker } = Input;

const LEVEL_CONFIG = {
  FATAL: { color: '#ff4d4f', icon: <ExclamationCircleOutlined />, dot: 'error' },
  WARNING: { color: '#fa8c16', icon: <WarningOutlined />, dot: 'warning' },
  INFORMATION: { color: '#52c41a', icon: <InfoCircleOutlined />, dot: 'success' },
  '': { color: '#8c8c8c', icon: <InfoCircleOutlined />, dot: 'gray' }
};

const TrcTimelinePanel = ({ 
  entries = [], 
  loading = false,
  title = 'SunDB 日志时间线',
  showFilters = true,
  maxHeight = '600px'
}) => {
  const [levelFilter, setLevelFilter] = useState(null);
  const [instanceFilter, setInstanceFilter] = useState(null);
  const [searchText, setSearchText] = useState('');

  const uniqueInstances = useMemo(() => {
    if (!entries || entries.length === 0) return [];
    const instances = [...new Set(entries.map(e => e.instance).filter(Boolean))];
    return instances.sort();
  }, [entries]);

  const filteredEntries = useMemo(() => {
    if (!entries || entries.length === 0) return [];
    
    let result = [...entries];
    
    if (levelFilter) {
      result = result.filter(e => e.level === levelFilter);
    }
    
    if (instanceFilter) {
      result = result.filter(e => e.instance === instanceFilter);
    }
    
    if (searchText) {
      const lowerSearch = searchText.toLowerCase();
      result = result.filter(e => 
        (e.message && e.message.toLowerCase().includes(lowerSearch)) ||
        (e.category && e.category.toLowerCase().includes(lowerSearch)) ||
        (e.error_code && e.error_code.toLowerCase().includes(lowerSearch))
      );
    }
    
    return result.slice(0, 200);
  }, [entries, levelFilter, instanceFilter, searchText]);

  const stats = useMemo(() => {
    if (!entries || entries.length === 0) return null;
    
    const byLevel = {};
    const byInstance = {};
    
    entries.forEach(e => {
      const level = e.level || 'UNKNOWN';
      const instance = e.instance || 'N/A';
      byLevel[level] = (byLevel[level] || 0) + 1;
      byInstance[instance] = (byInstance[instance] || 0) + 1;
    });
    
    return {
      byLevel,
      byInstance,
      total: entries.length,
      earliest: entries[0]?.timestamp,
      latest: entries[entries.length - 1]?.timestamp
    };
  }, [entries]);

  const getTimelineItem = (entry, index) => {
    const levelConfig = LEVEL_CONFIG[entry.level] || LEVEL_CONFIG[''];
    
    return (
      <Timeline.Item
        key={index}
        dot={
          <Badge 
            count={levelConfig.icon} 
            style={{ 
              backgroundColor: levelConfig.color,
              width: '20px',
              height: '20px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          />
        }
        style={{ paddingBottom: '16px' }}
      >
        <div style={{ 
          backgroundColor: '#252525', 
          padding: '12px', 
          borderRadius: '6px',
          border: `1px solid ${levelConfig.color}33`
        }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            marginBottom: '8px',
            flexWrap: 'wrap',
            gap: '8px'
          }}>
            <Space size="small" wrap>
              <Text style={{ fontSize: '12px', color: '#8c8c8c', fontFamily: 'monospace' }}>
                <ClockCircleOutlined style={{ marginRight: '4px' }} />
                {entry.timestamp}
              </Text>
              
              {entry.instance && (
                <Tag color="blue" style={{ margin: 0 }}>{entry.instance}</Tag>
              )}
              
              {entry.level && (
                <Tag color={levelConfig.color} style={{ margin: 0 }}>
                  {entry.level}
                </Tag>
              )}
              
              {entry.category && (
                <Tag color="cyan" style={{ margin: 0 }}>{entry.category}</Tag>
              )}
            </Space>
            
            <Space size="small">
              {entry.error_code && (
                <Tooltip title={entry.error_message}>
                  <Tag color="red" style={{ margin: 0, fontFamily: 'monospace', fontSize: '11px' }}>
                    {entry.error_code}
                  </Tag>
                </Tooltip>
              )}
              {entry.source_file && (
                <Text type="secondary" style={{ fontSize: '11px' }}>
                  <DatabaseOutlined style={{ marginRight: '4px' }} />
                  {entry.source_file}
                </Text>
              )}
            </Space>
          </div>
          
          <Paragraph
            style={{
              margin: 0,
              fontSize: '12px',
              color: '#d9d9d9',
              fontFamily: entry.message && entry.message.includes('SQL') ? 'monospace' : 'inherit',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}
            ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
          >
            {entry.message}
          </Paragraph>
        </div>
      </Timeline.Item>
    );
  };

  return (
    <Card
      title={
        <span>
          <ClockCircleOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
          {title}
          {stats && (
            <Tag color="blue" style={{ marginLeft: '8px' }}>
              {stats.total} 条日志
            </Tag>
          )}
        </span>
      }
      extra={
        showFilters && (
          <Space size="small" wrap>
            <Input
              placeholder="搜索日志..."
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ width: 150 }}
              size="small"
              allowClear
            />
            <Select
              placeholder="级别"
              style={{ width: 100 }}
              allowClear
              value={levelFilter}
              onChange={setLevelFilter}
              size="small"
            >
              <Option value="FATAL">FATAL</Option>
              <Option value="WARNING">WARNING</Option>
              <Option value="INFORMATION">INFORMATION</Option>
            </Select>
            <Select
              placeholder="节点"
              style={{ width: 80 }}
              allowClear
              value={instanceFilter}
              onChange={setInstanceFilter}
              size="small"
            >
              {uniqueInstances.map(inst => (
                <Option key={inst} value={inst}>{inst}</Option>
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
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '8px'
        }}>
          <Space size="small" wrap>
            {Object.entries(stats.byLevel).map(([level, count]) => {
              const config = LEVEL_CONFIG[level] || LEVEL_CONFIG[''];
              return (
                <Tag key={level} color={config.color}>
                  {level || 'UNKNOWN'}: {count}
                </Tag>
              );
            })}
          </Space>
          <Text type="secondary" style={{ fontSize: '11px' }}>
            时间范围: {stats.earliest} ~ {stats.latest}
          </Text>
        </div>
      )}

      <div style={{ maxHeight, overflow: 'auto', padding: '8px' }}>
        {filteredEntries.length > 0 ? (
          <Timeline
            style={{ marginTop: 0 }}
            items={filteredEntries.map((entry, index) => ({
              key: index,
              children: getTimelineItem(entry, index)
            }))}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无日志记录"
            style={{ padding: '40px 0' }}
          />
        )}
      </div>

      {filteredEntries.length >= 200 && (
        <Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: '8px', fontSize: '11px' }}>
          仅显示最近 200 条日志
        </Text>
      )}
    </Card>
  );
};

export default TrcTimelinePanel;
