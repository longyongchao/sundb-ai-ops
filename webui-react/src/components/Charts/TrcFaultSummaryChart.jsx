/**
 * SunDB TRC 故障统计图表组件
 * 
 * 功能：
 * 1. 按事件类型分布饼图
 * 2. 按严重程度分布柱状图
 * 3. 按节点分布柱状图
 * 
 * @component
 */
import React, { useMemo } from 'react';
import { Card, Row, Col, Typography, Empty, Space, Tag } from 'antd';
import {
  PieChartOutlined, BarChartOutlined, DatabaseOutlined,
  BugOutlined, WarningOutlined, InfoCircleOutlined
} from '@ant-design/icons';

const { Text, Title } = Typography;

const COLORS = {
  FATAL: '#ff4d4f',
  DEADLOCK: '#fa8c16',
  DDL_FAILURE: '#faad14',
  AUTH_FAILURE: '#722ed1',
  LISTENER_FAILURE: '#13c2c2'
};

const SEVERITY_COLORS = {
  critical: '#ff4d4f',
  high: '#fa8c16',
  medium: '#faad14',
  low: '#52c41a'
};

const EVENT_TYPE_NAMES = {
  FATAL: '致命错误',
  DEADLOCK: '死锁',
  DDL_FAILURE: 'DDL失败',
  AUTH_FAILURE: '认证失败',
  LISTENER_FAILURE: '监听器失败'
};

const SEVERITY_NAMES = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低'
};

const SimplePieChart = ({ data, title, colors, names }) => {
  const total = useMemo(() => {
    return Object.values(data || {}).reduce((sum, val) => sum + val, 0);
  }, [data]);

  if (!data || total === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0' }}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      </div>
    );
  }

  let currentAngle = 0;
  const radius = 80;
  const centerX = 100;
  const centerY = 100;

  const slices = Object.entries(data).map(([key, value]) => {
    const angle = (value / total) * 360;
    const startAngle = currentAngle;
    const endAngle = currentAngle + angle;
    currentAngle = endAngle;

    const startRad = (startAngle - 90) * Math.PI / 180;
    const endRad = (endAngle - 90) * Math.PI / 180;

    const x1 = centerX + radius * Math.cos(startRad);
    const y1 = centerY + radius * Math.sin(startRad);
    const x2 = centerX + radius * Math.cos(endRad);
    const y2 = centerY + radius * Math.sin(endRad);

    const largeArc = angle > 180 ? 1 : 0;
    const color = colors[key] || '#666';

    const pathD = `M ${centerX} ${centerY} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`;

    return {
      key,
      value,
      percentage: ((value / total) * 100).toFixed(1),
      color,
      pathD,
      name: names[key] || key
    };
  });

  return (
    <div>
      <svg width="200" height="200" viewBox="0 0 200 200" style={{ display: 'block', margin: '0 auto' }}>
        {slices.map((slice, index) => (
          <path
            key={index}
            d={slice.pathD}
            fill={slice.color}
            stroke="#1e1e1e"
            strokeWidth="2"
            style={{ transition: 'opacity 0.2s' }}
          />
        ))}
        <circle cx={centerX} cy={centerY} r="40" fill="#1e1e1e" />
        <text x={centerX} y={centerY - 8} textAnchor="middle" fill="#fff" fontSize="20" fontWeight="bold">
          {total}
        </text>
        <text x={centerX} y={centerY + 12} textAnchor="middle" fill="#8c8c8c" fontSize="11">
          总计
        </text>
      </svg>
      
      <div style={{ marginTop: '16px' }}>
        {slices.map((slice, index) => (
          <div key={index} style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            padding: '4px 8px',
            marginBottom: '4px',
            backgroundColor: '#252525',
            borderRadius: '4px'
          }}>
            <Space size="small">
              <div style={{ 
                width: '12px', 
                height: '12px', 
                backgroundColor: slice.color, 
                borderRadius: '2px' 
              }} />
              <Text style={{ fontSize: '12px' }}>{slice.name}</Text>
            </Space>
            <Space size="small">
              <Text style={{ fontSize: '12px', fontWeight: 'bold' }}>{slice.value}</Text>
              <Text type="secondary" style={{ fontSize: '11px' }}>({slice.percentage}%)</Text>
            </Space>
          </div>
        ))}
      </div>
    </div>
  );
};

const SimpleBarChart = ({ data, title, colors, names }) => {
  const maxValue = useMemo(() => {
    return Math.max(...Object.values(data || {}), 1);
  }, [data]);

  if (!data || Object.keys(data).length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0' }}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      </div>
    );
  }

  return (
    <div>
      {Object.entries(data).map(([key, value]) => {
        const percentage = (value / maxValue) * 100;
        const color = colors[key] || '#1890ff';
        const name = names[key] || key;

        return (
          <div key={key} style={{ marginBottom: '12px' }}>
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              marginBottom: '4px'
            }}>
              <Text style={{ fontSize: '12px' }}>{name}</Text>
              <Text style={{ fontSize: '12px', fontWeight: 'bold' }}>{value}</Text>
            </div>
            <div style={{ 
              height: '24px', 
              backgroundColor: '#333', 
              borderRadius: '4px',
              overflow: 'hidden',
              position: 'relative'
            }}>
              <div style={{
                width: `${percentage}%`,
                height: '100%',
                backgroundColor: color,
                borderRadius: '4px',
                transition: 'width 0.3s ease',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                paddingRight: '8px'
              }}>
                {percentage > 20 && (
                  <Text style={{ fontSize: '11px', color: '#fff' }}>
                    {((value / Object.values(data).reduce((a, b) => a + b, 0)) * 100).toFixed(1)}%
                  </Text>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

const TrcFaultSummaryChart = ({ 
  faultSummary = null,
  title = '故障统计概览'
}) => {
  const { byType, bySeverity, byInstance, total } = useMemo(() => {
    if (!faultSummary) {
      return { byType: {}, bySeverity: {}, byInstance: {}, total: 0 };
    }
    
    return {
      byType: faultSummary.by_type || {},
      bySeverity: faultSummary.by_severity || {},
      byInstance: faultSummary.by_instance || {},
      total: faultSummary.total || 0
    };
  }, [faultSummary]);

  return (
    <Card
      title={
        <span>
          <BarChartOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
          {title}
          {total > 0 && (
            <Tag color="red" style={{ marginLeft: '8px' }}>
              {total} 个故障
            </Tag>
          )}
        </span>
      }
      style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
      headStyle={{ backgroundColor: '#1e1e1e', borderBottom: '1px solid #333' }}
      bodyStyle={{ backgroundColor: '#1e1e1e', padding: '16px' }}
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={24} md={8}>
          <Card
            size="small"
            title={
              <span>
                <PieChartOutlined style={{ marginRight: '6px', color: '#1890ff' }} />
                按类型分布
              </span>
            }
            style={{ backgroundColor: '#252525', border: '1px solid #333' }}
            headStyle={{ 
              backgroundColor: '#252525', 
              borderBottom: '1px solid #333',
              padding: '8px 12px',
              minHeight: 'auto'
            }}
            bodyStyle={{ padding: '12px' }}
          >
            <SimplePieChart 
              data={byType} 
              colors={COLORS}
              names={EVENT_TYPE_NAMES}
            />
          </Card>
        </Col>

        <Col xs={24} sm={24} md={8}>
          <Card
            size="small"
            title={
              <span>
                <WarningOutlined style={{ marginRight: '6px', color: '#fa8c16' }} />
                按严重程度
              </span>
            }
            style={{ backgroundColor: '#252525', border: '1px solid #333' }}
            headStyle={{ 
              backgroundColor: '#252525', 
              borderBottom: '1px solid #333',
              padding: '8px 12px',
              minHeight: 'auto'
            }}
            bodyStyle={{ padding: '12px' }}
          >
            <SimpleBarChart 
              data={bySeverity} 
              colors={SEVERITY_COLORS}
              names={SEVERITY_NAMES}
            />
          </Card>
        </Col>

        <Col xs={24} sm={24} md={8}>
          <Card
            size="small"
            title={
              <span>
                <DatabaseOutlined style={{ marginRight: '6px', color: '#52c41a' }} />
                按节点分布
              </span>
            }
            style={{ backgroundColor: '#252525', border: '1px solid #333' }}
            headStyle={{ 
              backgroundColor: '#252525', 
              borderBottom: '1px solid #333',
              padding: '8px 12px',
              minHeight: 'auto'
            }}
            bodyStyle={{ padding: '12px' }}
          >
            <SimpleBarChart 
              data={byInstance} 
              colors={{}}
              names={{}}
            />
          </Card>
        </Col>
      </Row>

      {total === 0 && (
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无故障数据" />
        </div>
      )}
    </Card>
  );
};

export default TrcFaultSummaryChart;
