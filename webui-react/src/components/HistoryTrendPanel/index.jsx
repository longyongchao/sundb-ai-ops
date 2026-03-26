/**
 * HistoryTrendPanel - 历史趋势展示组件
 * 
 * 功能：
 * 1. 展示 CPU、内存、慢查询的历史趋势曲线
 * 2. 支持选择时间范围：1小时、1天、7天
 * 3. 展示告警历史列表
 * 4. 显示统计信息
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Row, Col, Select, Spin, Empty, Statistic, Tag, Table,
  Typography, Space, Divider, Badge, Tooltip, Tabs
} from 'antd';
import {
  LineChartOutlined, AlertOutlined, DatabaseOutlined,
  ClockCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { historyAPI } from '@/utils/api';

const { Title, Text } = Typography;
const { TabPane } = Tabs;
const { RangePicker } = DatePicker;

const ALERT_TYPE_MAP = {
  'NodeCpuHigh': { text: 'CPU 高负载', color: 'red' },
  'NodeMemoryHigh': { text: '内存高使用', color: 'orange' },
  'HighDiskIO': { text: 'IO 瓶颈', color: 'purple' },
  'SlowQueryDetected': { text: '慢查询', color: 'blue' },
  'ConnectionPoolExhausted': { text: '连接池耗尽', color: 'magenta' },
  'DeadlockDetected': { text: '死锁', color: 'red' }
};

const ALERT_LEVEL_MAP = {
  'info': { text: '信息', color: 'blue' },
  'warning': { text: '警告', color: 'orange' },
  'critical': { text: '严重', color: 'red' }
};

const HistoryTrendPanel = () => {
  const [loading, setLoading] = useState(false);
  const [timeRange, setTimeRange] = useState('24');
  const [trendData, setTrendData] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [statistics, setStatistics] = useState(null);
  const [activeMetric, setActiveMetric] = useState('cpu');

  useEffect(() => {
    loadData();
  }, [timeRange]);

  const loadData = async () => {
    setLoading(true);
    try {
      const hours = parseInt(timeRange);
      
      const [cpuTrend, memTrend, ioTrend, alertsData, statsData] = await Promise.all([
        historyAPI.getTrendData('cpu', hours),
        historyAPI.getTrendData('memory', hours),
        historyAPI.getTrendData('disk_io', hours),
        historyAPI.getAlertHistory({ days: Math.ceil(hours / 24) || 1 }),
        historyAPI.getStatistics(7)
      ]);
      
      setTrendData({
        cpu: cpuTrend,
        memory: memTrend,
        disk_io: ioTrend
      });
      setAlerts(alertsData || []);
      setStatistics(statsData);
    } catch (error) {
      console.error('加载历史数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const getChartOption = (metricType) => {
    const data = trendData[metricType];
    if (!data || !data.timestamps) {
      return {};
    }

    const colors = {
      cpu: '#ff4d4f',
      memory: '#faad14',
      disk_io: '#722ed1'
    };

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(0,0,0,0.8)',
        borderColor: '#333',
        textStyle: { color: '#fff' }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: data.timestamps.map(t => {
          if (!t) return '';
          const date = new Date(t);
          return `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
        }),
        axisLine: { lineStyle: { color: '#444' } },
        axisLabel: { color: '#888', fontSize: 10 }
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLine: { lineStyle: { color: '#444' } },
        axisLabel: { color: '#888', formatter: '{value}%' },
        splitLine: { lineStyle: { color: '#333' } }
      },
      series: [{
        name: data.metric_type?.toUpperCase() || metricType.toUpperCase(),
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: colors[metricType] || '#1890ff' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: `${colors[metricType] || '#1890ff'}40` },
              { offset: 1, color: `${colors[metricType] || '#1890ff'}05` }
            ]
          }
        },
        data: data.values
      }]
    };
  };

  const alertColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text) => text ? new Date(text).toLocaleString('zh-CN') : '-'
    },
    {
      title: '告警类型',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 120,
      render: (type) => {
        const info = ALERT_TYPE_MAP[type] || { text: type, color: 'default' };
        return <Tag color={info.color}>{info.text}</Tag>;
      }
    },
    {
      title: '级别',
      dataIndex: 'alert_level',
      key: 'alert_level',
      width: 80,
      render: (level) => {
        const info = ALERT_LEVEL_MAP[level] || { text: level, color: 'default' };
        return <Tag color={info.color}>{info.text}</Tag>;
      }
    },
    {
      title: '告警信息',
      dataIndex: 'alert_message',
      key: 'alert_message',
      ellipsis: true
    },
    {
      title: '诊断状态',
      dataIndex: 'is_diagnosed',
      key: 'is_diagnosed',
      width: 100,
      render: (diagnosed) => diagnosed 
        ? <Tag color="success" icon={<CheckCircleOutlined />}>已诊断</Tag>
        : <Tag color="warning" icon={<ExclamationCircleOutlined />}>待处理</Tag>
    }
  ];

  return (
    <div style={{ padding: '16px' }}>
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card
            style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
            headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333' }}
            bodyStyle={{ padding: '16px' }}
          >
            <Space style={{ marginBottom: '16px' }}>
              <Text style={{ color: '#888' }}>时间范围：</Text>
              <Select
                value={timeRange}
                onChange={setTimeRange}
                style={{ width: 120 }}
                options={[
                  { value: '1', label: '最近 1 小时' },
                  { value: '6', label: '最近 6 小时' },
                  { value: '24', label: '最近 24 小时' },
                  { value: '72', label: '最近 3 天' },
                  { value: '168', label: '最近 7 天' }
                ]}
              />
            </Space>

            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <Spin size="large" />
              </div>
            ) : (
              <Tabs defaultActiveKey="cpu" onChange={setActiveMetric}>
                <TabPane tab="CPU 使用率" key="cpu">
                  <ReactECharts
                    option={getChartOption('cpu')}
                    style={{ height: '300px' }}
                    opts={{ renderer: 'canvas' }}
                  />
                </TabPane>
                <TabPane tab="内存使用率" key="memory">
                  <ReactECharts
                    option={getChartOption('memory')}
                    style={{ height: '300px' }}
                    opts={{ renderer: 'canvas' }}
                  />
                </TabPane>
                <TabPane tab="磁盘 IO" key="disk_io">
                  <ReactECharts
                    option={getChartOption('disk_io')}
                    style={{ height: '300px' }}
                    opts={{ renderer: 'canvas' }}
                  />
                </TabPane>
              </Tabs>
            )}
          </Card>
        </Col>

        <Col span={24}>
          <Card
            title={
              <span>
                <AlertOutlined style={{ marginRight: '8px', color: '#faad14' }} />
                告警历史
              </span>
            }
            style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
            headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333' }}
            bodyStyle={{ padding: '16px' }}
          >
            <Table
              dataSource={alerts}
              columns={alertColumns}
              rowKey="id"
              pagination={{ pageSize: 10 }}
              size="small"
              locale={{ emptyText: <Empty description="暂无告警记录" /> }}
            />
          </Card>
        </Col>

        {statistics && (
          <Col span={24}>
            <Card
              title={
                <span>
                  <DatabaseOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
                  统计概览（最近 7 天）
                </span>
              }
              style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
              headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333' }}
              bodyStyle={{ padding: '16px' }}
            >
              <Row gutter={[16, 16]}>
                <Col span={6}>
                  <Statistic
                    title={<Text style={{ color: '#888' }}>监控记录数</Text>}
                    value={statistics.summary?.total_monitoring_records || 0}
                    valueStyle={{ color: '#1890ff' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={<Text style={{ color: '#888' }}>告警总数</Text>}
                    value={statistics.summary?.total_alerts || 0}
                    valueStyle={{ color: '#faad14' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={<Text style={{ color: '#888' }}>诊断率</Text>}
                    value={statistics.summary?.diagnosis_rate || 0}
                    suffix="%"
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={<Text style={{ color: '#888' }}>平均 CPU</Text>}
                    value={statistics.summary?.avg_cpu_usage || '0%'}
                    valueStyle={{ color: '#ff4d4f' }}
                  />
                </Col>
              </Row>
              
              <Divider style={{ margin: '16px 0', borderColor: '#333' }} />
              
              <Row gutter={[16, 16]}>
                <Col span={6}>
                  <Statistic
                    title={<Text style={{ color: '#888' }}>最大 CPU</Text>}
                    value={statistics.summary?.max_cpu_usage || '0%'}
                    valueStyle={{ color: '#ff4d4f' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={<Text style={{ color: '#888' }}>平均内存</Text>}
                    value={statistics.summary?.avg_memory_usage || '0%'}
                    valueStyle={{ color: '#faad14' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={<Text style={{ color: '#888' }}>最大内存</Text>}
                    value={statistics.summary?.max_memory_usage || '0%'}
                    valueStyle={{ color: '#faad14' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={<Text style={{ color: '#888' }}>活跃告警</Text>}
                    value={statistics.alerts?.active_count || 0}
                    valueStyle={{ color: '#ff4d4f' }}
                  />
                </Col>
              </Row>
            </Card>
          </Col>
        )}
      </Row>
    </div>
  );
};

export default HistoryTrendPanel;
