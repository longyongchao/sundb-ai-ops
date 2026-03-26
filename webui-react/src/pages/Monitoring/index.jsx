/**
 * @fileoverview Monitoring 页面 - 实时监控仪表盘
 * @author [Your Name]
 * @date 2024/01/01
 * @description 实现论文 D-Bot Section 2 - 数据库性能异常监控
 *              核心：PostgreSQL 数据库运行指标监控
 */
import React, { useState, useEffect } from 'react';
import { Row, Col, Card, Table, Tag, Alert, Statistic, Progress, Switch, Spin, Tabs, Badge, Tooltip, Button, message, Divider, Dropdown } from 'antd';
import {
  MonitorOutlined, DatabaseOutlined, AlertOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
  ClockCircleOutlined, ThunderboltOutlined, LockOutlined,
  ApiOutlined, HddOutlined, CloudOutlined, DesktopOutlined,
  CopyOutlined, ExpandOutlined, CompressOutlined, DashboardOutlined,
  SafetyOutlined, ClusterOutlined, TransactionOutlined, DownOutlined
} from '@ant-design/icons';
import { MetricLineChart } from '@/components/Charts';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const safeFormatNumber = (value, decimals = 2) => {
  if (value === null || value === undefined) return '0.00';
  const num = Number(value);
  return isNaN(num) ? '0.00' : num.toFixed(decimals);
};

const Monitoring = () => {
  const navigate = useNavigate();
  const [monitoringEnabled, setMonitoringEnabled] = useState(() => {
    const saved = localStorage.getItem('monitoring_enabled');
    return saved !== null ? JSON.parse(saved) : false;  // 【2024修复】默认关闭监控
  });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [monitorData, setMonitorData] = useState({
    databases: [],
    alerts: [],
    metrics: null,
    realTime: null,
    database: null
  });
  const [slowQueries, setSlowQueries] = useState([]);
  const [dbStatus, setDbStatus] = useState(null);
  const [alertHistory, setAlertHistory] = useState([]);
  const [expandedQueries, setExpandedQueries] = useState({});

  useEffect(() => {
    localStorage.setItem('monitoring_enabled', JSON.stringify(monitoringEnabled));
  }, [monitoringEnabled]);

  useEffect(() => {
    const fetchMonitoringStatus = async () => {
      try {
        const res = await axios.get('/api/monitoring/status');
        if (res?.data?.code === 200) {
          const backendStatus = res.data.data?.monitoring_enabled ?? false;
          setMonitoringEnabled(backendStatus);
          localStorage.setItem('monitoring_enabled', JSON.stringify(backendStatus));
        }
      } catch (error) {
        console.error('Failed to fetch monitoring status:', error);
      }
    };
    fetchMonitoringStatus();
  }, []);

  useEffect(() => {
    const timeInterval = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    return () => clearInterval(timeInterval);
  }, []);

  useEffect(() => {
    if (!monitoringEnabled) {
      return;
    }
    fetchAllData();
    let interval;
    if (autoRefresh) {
      interval = setInterval(fetchAllData, 10000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, monitoringEnabled]);

  const handleMonitoringToggle = async (enabled) => {
    try {
      const res = await axios.post('/api/monitoring/toggle', { enabled });
      
      if (res?.data?.code === 200) {
        setMonitoringEnabled(enabled);
        message.success(res.data.msg);
        
        if (enabled) {
          fetchAllData();
        }
      } else {
        message.error(res?.data?.msg || '操作失败');
      }
    } catch (error) {
      console.error('切换监控状态失败:', error);
      message.error('切换监控状态失败，请检查后端服务');
    }
  };

  const fetchAllData = async () => {
    setLoading(true);
    try {
      await Promise.all([
        fetchMonitoringData(),
        fetchSlowQueries(),
        fetchDatabaseStatus(),
        fetchAlertHistory()
      ]);
    } finally {
      setLoading(false);
    }
  };

  const fetchMonitoringData = async () => {
    try {
      const res = await axios.get('/api/dashboard/metrics').catch(() => null);
      
      if (res?.data?.data) {
        const data = res.data.data;
        const realTime = data.metrics?.real_time || {};
        const database = data.metrics?.database || {};
        const dbStatusData = data.database_status || {};
        
        const dbConnections = database.connections || {};
        const dbPerformance = database.performance || {};
        const dbCache = database.cache || {};
        const dbLocks = database.locks || {};
        const dbSlowQueries = database.slow_queries || {};
        const dbInstance = database.instance || {};
        
        const healthStatus = getDatabaseHealthStatus(
          dbConnections.usage_percent || 0,
          dbCache.cache_hit_ratio || 100,
          dbSlowQueries.count || 0,
          dbLocks.blocked_sessions || 0,
          dbStatusData.connected
        );

        const databases = [{
          id: 1,
          name: 'PostgreSQL-Main',
          host: dbStatusData.config?.host || '127.0.0.1',
          port: dbStatusData.config?.port || 5432,
          status: healthStatus,
          version: dbInstance.version || 'Unknown',
          uptime: dbInstance.uptime || '-',
          connections: dbConnections.total || 0,
          maxConnections: dbConnections.max_connections || 100,
          connUsagePercent: dbConnections.usage_percent || 0,
          activeConnections: dbConnections.active || 0,
          qps: dbPerformance.qps || 0,
          tps: dbPerformance.tps || 0,
          cacheHitRatio: dbCache.cache_hit_ratio || 0,
          slowQueryCount: dbSlowQueries.count || 0,
          blockedSessions: dbLocks.blocked_sessions || 0,
          waitingLocks: dbLocks.waiting_locks || 0,
          healthReason: getHealthReason(
            dbConnections.usage_percent || 0,
            dbCache.cache_hit_ratio || 100,
            dbSlowQueries.count || 0,
            dbLocks.blocked_sessions || 0,
            dbStatusData.connected
          )
        }];

        const alerts = generateAlerts(database, realTime, dbStatusData);

        setMonitorData({
          databases,
          alerts,
          metrics: data.metrics,
          realTime,
          database
        });
      }
    } catch (error) {
      console.log('获取监控数据失败:', error);
    }
  };

  const generateAlerts = (database, realTime, dbStatusData) => {
    const alerts = [];
    const now = new Date().toLocaleTimeString();
    
    if (!dbStatusData.connected) {
      alerts.push({ id: Date.now(), level: 'error', message: '数据库连接失败', time: now });
    }
    
    const connections = database.connections || {};
    if (connections.usage_percent > 85) {
      alerts.push({
        id: Date.now() + 1,
        level: connections.usage_percent > 95 ? 'error' : 'warning',
        message: `数据库连接数使用率过高: ${safeFormatNumber(connections.usage_percent, 1)}%`,
        time: now
      });
    }
    
    const cache = database.cache || {};
    if (cache.cache_hit_ratio < 90) {
      alerts.push({
        id: Date.now() + 2,
        level: 'warning',
        message: `数据库缓存命中率过低: ${safeFormatNumber(cache.cache_hit_ratio, 1)}%`,
        time: now
      });
    }
    
    const locks = database.locks || {};
    if (locks.blocked_sessions > 0) {
      alerts.push({
        id: Date.now() + 3,
        level: 'error',
        message: `检测到 ${locks.blocked_sessions} 个阻塞会话`,
        time: now
      });
    }
    
    const slowQueries = database.slow_queries || {};
    if (slowQueries.count > 10) {
      alerts.push({
        id: Date.now() + 4,
        level: 'warning',
        message: `检测到 ${slowQueries.count} 条慢查询`,
        time: now
      });
    }
    
    return alerts;
  };

  const fetchSlowQueries = async () => {
    try {
      const res = await axios.get('/api/database/slow_queries?top_n=10').catch(() => null);
      if (res?.data?.data?.queries) {
        setSlowQueries(res.data.data.queries);
      }
    } catch (error) {
      console.log('获取慢查询失败:', error);
    }
  };

  const fetchDatabaseStatus = async () => {
    try {
      const res = await axios.get('/api/database/status').catch(() => null);
      if (res?.data?.data) {
        setDbStatus(res.data.data);
      }
    } catch (error) {
      console.log('获取数据库状态失败:', error);
    }
  };

  const fetchAlertHistory = async () => {
    try {
      const res = await axios.get('/api/history/alerts?limit=20').catch(() => null);
      if (res?.data?.data && Array.isArray(res.data.data)) {
        const formattedAlerts = res.data.data.map(alert => ({
          id: alert.id,
          level: alert.alert_level === 'critical' ? 'error' : alert.alert_level,
          type: alert.alert_type,
          message: alert.alert_message,
          time: alert.created_at ? new Date(alert.created_at).toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
          }) : '-',
          status: alert.status,
          isDiagnosed: alert.is_diagnosed
        }));
        setAlertHistory(formattedAlerts);
      }
    } catch (error) {
      console.log('获取告警历史失败:', error);
    }
  };

  const getDatabaseHealthStatus = (connUsage, cacheHit, slowCount, blockedCount, dbConnected) => {
    if (!dbConnected) return 'error';
    if (blockedCount > 0 || connUsage > 95 || cacheHit < 70) return 'error';
    if (connUsage > 85 || cacheHit < 90 || slowCount > 10) return 'warning';
    return 'healthy';
  };

  const getHealthReason = (connUsage, cacheHit, slowCount, blockedCount, dbConnected) => {
    const reasons = [];
    if (!dbConnected) reasons.push('数据库连接失败');
    if (blockedCount > 0) reasons.push(`存在${blockedCount}个阻塞会话`);
    if (connUsage > 85) reasons.push(`连接使用率过高(${safeFormatNumber(connUsage, 1)}%)`);
    if (cacheHit < 90) reasons.push(`缓存命中率偏低(${safeFormatNumber(cacheHit, 1)}%)`);
    if (slowCount > 10) reasons.push(`慢查询过多(${slowCount}条)`);
    return reasons.length > 0 ? reasons.join('、') : '数据库运行正常';
  };

  const handleStatusChange = async (alertId, newStatus) => {
    try {
      const res = await axios.put(`/api/history/alerts/${alertId}/status`, { status: newStatus });
      if (res?.data?.code === 200) {
        message.success(`状态已更新为: ${getStatusText(newStatus)}`);
        fetchAlertHistory();
      } else {
        message.error('状态更新失败');
      }
    } catch (error) {
      console.log('更新告警状态失败:', error);
      message.error('状态更新失败，请稍后重试');
    }
  };

  const getStatusText = (status) => {
    const statusMap = {
      'active': '待处理',
      'resolved': '已处理',
      'acknowledged': '已确认',
      'ignored': '已忽略'
    };
    return statusMap[status] || status;
  };

  const getStatusConfig = (status, level) => {
    const configs = {
      'active': {
        bg: level === 'error' || level === 'critical' ? '#ff4d4f' : '#faad14',
        color: '#fff',
        text: '待处理',
        hoverBg: level === 'error' || level === 'critical' ? '#ff7875' : '#ffc53d'
      },
      'resolved': {
        bg: '#52c41a',
        color: '#fff',
        text: '已处理',
        hoverBg: '#73d13d'
      },
      'acknowledged': {
        bg: '#1890ff',
        color: '#fff',
        text: '已确认',
        hoverBg: '#40a9ff'
      },
      'ignored': {
        bg: '#8c8c8c',
        color: '#fff',
        text: '已忽略',
        hoverBg: '#bfbfbf'
      }
    };
    return configs[status] || configs['active'];
  };

  const statusMenuItems = (alertId, currentStatus) => [
    { key: 'active', label: '待处理', disabled: currentStatus === 'active' },
    { key: 'resolved', label: '已处理', disabled: currentStatus === 'resolved' },
    { key: 'acknowledged', label: '已确认', disabled: currentStatus === 'acknowledged' },
    { key: 'ignored', label: '已忽略', disabled: currentStatus === 'ignored' }
  ];

  const getStatusTag = (status) => {
    const statusMap = {
      healthy: { color: '#237804', icon: <CheckCircleOutlined />, text: '健康' },
      warning: { color: '#ad6800', icon: <AlertOutlined />, text: '警告' },
      error: { color: '#a61d24', icon: <CloseCircleOutlined />, text: '异常' }
    };
    const config = statusMap[status] || { color: '#434343', icon: null, text: status };
    return <Tag color={config.color} icon={config.icon}>{config.text}</Tag>;
  };

  const getProgressColor = (percent, isReverse = false) => {
    if (isReverse) {
      if (percent < 70) return '#ff4d4f';
      if (percent < 90) return '#faad14';
      return '#52c41a';
    }
    if (percent >= 95) return '#ff4d4f';
    if (percent >= 80) return '#fa8c16';
    if (percent >= 70) return '#faad14';
    return '#52c41a';
  };

  const toggleQueryExpand = (queryId) => {
    setExpandedQueries(prev => ({
      ...prev,
      [queryId]: !prev[queryId]
    }));
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      message.success('SQL已复制到剪贴板');
    }).catch(() => {
      message.error('复制失败');
    });
  };

  const dbColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 50 },
    { title: '实例名称', dataIndex: 'name', key: 'name', width: 140 },
    { 
      title: '主机/端口', 
      key: 'host_port',
      width: 130,
      render: (_, record) => `${record.host}:${record.port}`
    },
    { 
      title: '运行状态', 
      dataIndex: 'status', 
      key: 'status', 
      width: 90,
      render: (status, record) => (
        <Tooltip title={record.healthReason}>
          {getStatusTag(status)}
        </Tooltip>
      )
    },
    {
      title: '连接数使用率',
      dataIndex: 'connUsagePercent',
      key: 'connUsagePercent',
      width: 150,
      render: (percent, record) => (
        <Tooltip title={`${record.activeConnections}/${record.maxConnections} 活跃连接`}>
          <Progress 
            percent={Math.round(percent)} 
            size="small" 
            strokeColor={getProgressColor(percent)}
            format={(p) => `${p}%`}
          />
        </Tooltip>
      )
    },
    {
      title: 'QPS',
      dataIndex: 'qps',
      key: 'qps',
      width: 80,
      render: (qps) => <Tag color="blue">{safeFormatNumber(qps, 1)}</Tag>
    },
    {
      title: '慢查询数',
      dataIndex: 'slowQueryCount',
      key: 'slowQueryCount',
      width: 90,
      render: (count) => (
        <Tag color={count > 10 ? 'red' : count > 5 ? 'orange' : 'green'}>
          {count}
        </Tag>
      )
    },
    {
      title: '缓存命中率',
      dataIndex: 'cacheHitRatio',
      key: 'cacheHitRatio',
      width: 120,
      render: (ratio) => (
        <Progress 
          percent={Math.round(ratio)} 
          size="small" 
          strokeColor={getProgressColor(ratio, true)}
          format={(p) => `${p}%`}
        />
      )
    },
    {
      title: '阻塞会话',
      dataIndex: 'blockedSessions',
      key: 'blockedSessions',
      width: 90,
      render: (count) => (
        <Tag color={count > 0 ? 'red' : 'green'}>
          {count}
        </Tag>
      )
    }
  ];

  const slowQueryColumns = [
    {
      title: 'Query ID',
      dataIndex: 'query_id',
      key: 'query_id',
      width: 80,
      render: (id) => <Tag color="blue">{id}</Tag>
    },
    {
      title: 'SQL 语句',
      dataIndex: 'query',
      key: 'query',
      width: 350,
      render: (query, record) => {
        const isExpanded = expandedQueries[record.query_id];
        const displayQuery = isExpanded ? query : (query?.substring(0, 50) + (query?.length > 50 ? '...' : ''));
        return (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
            <code style={{ 
              fontSize: '12px', 
              flex: 1, 
              wordBreak: 'break-all',
              whiteSpace: isExpanded ? 'pre-wrap' : 'nowrap',
              overflow: isExpanded ? 'auto' : 'hidden',
              maxHeight: isExpanded ? '200px' : 'auto'
            }}>
              {displayQuery}
            </code>
            <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
              <Tooltip title={isExpanded ? '收起' : '展开'}>
                <Button 
                  size="small" 
                  type="text" 
                  icon={isExpanded ? <CompressOutlined /> : <ExpandOutlined />}
                  onClick={() => toggleQueryExpand(record.query_id)}
                />
              </Tooltip>
              <Tooltip title="复制SQL">
                <Button 
                  size="small" 
                  type="text" 
                  icon={<CopyOutlined />}
                  onClick={() => copyToClipboard(query)}
                />
              </Tooltip>
            </div>
          </div>
        );
      }
    },
    {
      title: '调用次数',
      dataIndex: 'calls',
      key: 'calls',
      width: 90,
      render: (calls) => <Tag color="purple">{calls}</Tag>
    },
    {
      title: '总耗时',
      dataIndex: 'total_time',
      key: 'total_time',
      width: 100,
      render: (time) => <span style={{ color: '#ff4d4f', fontWeight: 500 }}>{safeFormatNumber(time, 2)}ms</span>
    },
    {
      title: '平均耗时',
      dataIndex: 'mean_time',
      key: 'mean_time',
      width: 100,
      render: (time) => <span>{safeFormatNumber(time, 2)}ms</span>
    },
    {
      title: 'CPU占比',
      dataIndex: 'cpu_percent',
      key: 'cpu_percent',
      width: 100,
      render: (percent) => (
        <Progress 
          percent={Math.round(percent || 0)} 
          size="small" 
          strokeColor={percent > 50 ? '#ff4d4f' : '#52c41a'}
        />
      )
    }
  ];

  const database = monitorData.database || {};
  const connections = database.connections || {};
  const performance = database.performance || {};
  const cache = database.cache || {};
  const locks = database.locks || {};
  const transactions = database.transactions || {};
  const slowQueriesData = database.slow_queries || {};

  return (
    <div className="monitoring-page" style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', marginBottom: '8px' }}>
            <DatabaseOutlined /> 数据库实时监控
          </h1>
          <p style={{ color: '#8c8c8c' }}>
            PostgreSQL 数据库运行状态与性能指标监控 | 更新时间：{currentTime.toLocaleString('zh-CN', { 
              year: 'numeric', 
              month: '2-digit', 
              day: '2-digit',
              hour: '2-digit', 
              minute: '2-digit', 
              second: '2-digit',
              hour12: false 
            })}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '8px',
            padding: '8px 16px',
            background: monitoringEnabled ? 'rgba(82, 196, 26, 0.1)' : 'rgba(140, 140, 140, 0.1)',
            borderRadius: '8px',
            border: `1px solid ${monitoringEnabled ? '#52c41a' : '#8c8c8c'}`
          }}>
            <span style={{ 
              fontSize: '14px',
              fontWeight: 500,
              color: monitoringEnabled ? '#52c41a' : '#8c8c8c'
            }}>
              {monitoringEnabled ? '● 实时监控中' : '○ 监控已暂停'}
            </span>
            <Switch 
              checked={monitoringEnabled} 
              onChange={handleMonitoringToggle}
              checkedChildren="开"
              unCheckedChildren="关"
              style={{ background: monitoringEnabled ? '#52c41a' : '#8c8c8c' }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ color: monitoringEnabled ? 'inherit' : '#8c8c8c' }}>自动刷新 (10秒)</span>
            <Switch 
              checked={autoRefresh} 
              onChange={setAutoRefresh}
              disabled={!monitoringEnabled}
            />
            {monitoringEnabled && autoRefresh && <SyncOutlined spin style={{ color: '#1890ff' }} />}
            {loading && <Spin size="small" />}
          </div>
        </div>
      </div>

      {!monitoringEnabled && (
        <Alert
          message="监控已暂停"
          description="监控功能已暂停，数据将不再自动刷新。点击顶部开关可恢复实时监控。"
          type="warning"
          showIcon
          style={{ marginBottom: '16px' }}
        />
      )}

      {monitorData.alerts.filter(a => a.level === 'error').length > 0 && monitoringEnabled && (
        <Alert
          message="检测到数据库异常"
          description={monitorData.alerts.filter(a => a.level === 'error').map(a => a.message).join('; ')}
          type="error"
          showIcon
          closable
          style={{ marginBottom: '16px' }}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable style={{ background: 'linear-gradient(135deg, #1890ff 0%, #096dd9 100%)' }}>
            <Statistic
              title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>监控数据库</span>}
              value={monitorData.databases.length}
              prefix={<DatabaseOutlined style={{ color: '#fff' }} />}
              valueStyle={{ color: '#fff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable style={{ background: monitorData.databases.filter(d => d.status === 'healthy').length > 0 ? 'linear-gradient(135deg, #52c41a 0%, #389e0d 100%)' : '#1f1f1f' }}>
            <Statistic
              title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>健康实例</span>}
              value={monitorData.databases.filter(d => d.status === 'healthy').length}
              valueStyle={{ color: '#fff' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable style={{ background: monitorData.alerts.filter(a => a.level !== 'info').length > 0 ? 'linear-gradient(135deg, #ff4d4f 0%, #cf1322 100%)' : 'linear-gradient(135deg, #52c41a 0%, #389e0d 100%)' }}>
            <Statistic
              title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>活跃告警</span>}
              value={monitorData.alerts.filter(a => a.level !== 'info').length}
              valueStyle={{ color: '#fff' }}
              prefix={<AlertOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable style={{ background: 'linear-gradient(135deg, #722ed1 0%, #531dab 100%)' }}>
            <Statistic
              title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>慢查询数</span>}
              value={slowQueriesData.count || slowQueries.length}
              valueStyle={{ color: '#fff' }}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card 
        title={<span><DatabaseOutlined /> 数据库核心性能指标</span>} 
        bordered={false} 
        style={{ marginBottom: '16px' }}
        styles={{ header: { background: 'linear-gradient(90deg, #1890ff 0%, #096dd9 100%)', color: '#fff' } }}
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={6}>
            <Card size="small" style={{ background: 'rgba(24,144,255,0.1)', border: '1px solid rgba(24,144,255,0.3)' }}>
              <Statistic
                title={<span><DashboardOutlined style={{ marginRight: 4 }} /> QPS (每秒查询数)</span>}
                value={safeFormatNumber(performance.qps, 1)}
                valueStyle={{ color: '#1890ff', fontSize: '28px' }}
              />
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '8px' }}>
                TPS: {safeFormatNumber(performance.tps, 1)}
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small" style={{ background: 'rgba(82,196,26,0.1)', border: '1px solid rgba(82,196,26,0.3)' }}>
              <Statistic
                title={<span><ClusterOutlined style={{ marginRight: 4 }} /> 连接数使用率</span>}
                value={safeFormatNumber(connections.usage_percent, 1)}
                suffix="%"
                valueStyle={{ color: getProgressColor(connections.usage_percent || 0), fontSize: '28px' }}
              />
              <Progress 
                percent={Math.round(connections.usage_percent || 0)} 
                showInfo={false}
                strokeColor={getProgressColor(connections.usage_percent || 0)}
              />
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '4px' }}>
                {connections.active || 0} / {connections.max_connections || 100} 活跃连接
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small" style={{ background: 'rgba(250,173,20,0.1)', border: '1px solid rgba(250,173,20,0.3)' }}>
              <Statistic
                title={<span><SafetyOutlined style={{ marginRight: 4 }} /> 缓存命中率</span>}
                value={safeFormatNumber(cache.cache_hit_ratio, 1)}
                suffix="%"
                valueStyle={{ color: getProgressColor(cache.cache_hit_ratio || 100, true), fontSize: '28px' }}
              />
              <Progress 
                percent={Math.round(cache.cache_hit_ratio || 100)} 
                showInfo={false}
                strokeColor={getProgressColor(cache.cache_hit_ratio || 100, true)}
              />
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '4px' }}>
                索引命中率: {safeFormatNumber(cache.index_hit_ratio, 1)}%
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small" style={{ background: locks.blocked_sessions > 0 ? 'rgba(255,77,79,0.1)' : 'rgba(82,196,26,0.1)', border: locks.blocked_sessions > 0 ? '1px solid rgba(255,77,79,0.3)' : '1px solid rgba(82,196,26,0.3)' }}>
              <Statistic
                title={<span><LockOutlined style={{ marginRight: 4 }} /> 锁等待数量</span>}
                value={locks.waiting_locks || 0}
                valueStyle={{ color: locks.blocked_sessions > 0 ? '#ff4d4f' : '#52c41a', fontSize: '28px' }}
              />
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '8px' }}>
                阻塞会话: <Tag color={locks.blocked_sessions > 0 ? 'red' : 'green'}>{locks.blocked_sessions || 0}</Tag>
              </div>
            </Card>
          </Col>
        </Row>
      </Card>

      <Tabs defaultActiveKey="database" items={[
        {
          key: 'database',
          label: <span><DatabaseOutlined /> 数据库实例</span>,
          children: (
            <>
              <Card title="数据库实例详情" bordered={false} style={{ marginBottom: '16px' }}>
                <Table
                  dataSource={monitorData.databases}
                  columns={dbColumns}
                  rowKey="id"
                  pagination={false}
                  size="small"
                />
              </Card>

              <Card title="数据库事务与性能" bordered={false} style={{ marginBottom: '16px' }}>
                <Row gutter={[16, 16]}>
                  <Col xs={24} sm={12} md={6}>
                    <Statistic
                      title="总事务数"
                      value={performance.total_transactions || 0}
                      prefix={<TransactionOutlined />}
                    />
                  </Col>
                  <Col xs={24} sm={12} md={6}>
                    <Statistic
                      title="提交事务"
                      value={performance.commits || 0}
                      valueStyle={{ color: '#52c41a' }}
                    />
                  </Col>
                  <Col xs={24} sm={12} md={6}>
                    <Statistic
                      title="回滚事务"
                      value={performance.rollbacks || 0}
                      valueStyle={{ color: '#ff4d4f' }}
                    />
                  </Col>
                  <Col xs={24} sm={12} md={6}>
                    <Statistic
                      title="回滚率"
                      value={safeFormatNumber(performance.rollback_rate, 2)}
                      suffix="%"
                      valueStyle={{ color: (performance.rollback_rate || 0) > 5 ? '#ff4d4f' : '#52c41a' }}
                    />
                  </Col>
                </Row>
              </Card>

              <Card title="数据库性能趋势" bordered={false}>
                <MetricLineChart 
                  data={monitorData.metrics} 
                  title="数据库性能监控" 
                  height={300} 
                />
              </Card>
            </>
          )
        },
        {
          key: 'slow_queries',
          label: <span><ClockCircleOutlined /> 慢查询监控</span>,
          children: (
            <Card bordered={false}>
              <Alert
                message="慢查询监控"
                description="展示执行时间最长的 SQL 查询，帮助定位性能瓶颈"
                type="info"
                showIcon
                style={{ marginBottom: '16px' }}
              />
              <Table
                dataSource={slowQueries}
                columns={slowQueryColumns}
                rowKey="query_id"
                pagination={{ pageSize: 10 }}
                size="small"
                scroll={{ x: 1000 }}
                locale={{ emptyText: '暂无慢查询数据，或 pg_stat_statements 未启用' }}
              />
            </Card>
          )
        },
        {
          key: 'host',
          label: <span><DesktopOutlined /> 主机系统资源</span>,
          children: (
            <>
              {monitorData.realTime && (
                <Card title="主机系统指标（辅助参考）" bordered={false} style={{ marginBottom: '16px' }}>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} sm={12} md={6}>
                      <Card size="small" style={{ background: 'rgba(255,77,79,0.1)' }}>
                        <Statistic
                          title={<span><DesktopOutlined /> CPU 使用率</span>}
                          value={monitorData.realTime.cpu_percent || 0}
                          suffix="%"
                          valueStyle={{ color: getProgressColor(monitorData.realTime.cpu_percent) }}
                        />
                        <Progress 
                          percent={Math.round(monitorData.realTime.cpu_percent || 0)} 
                          showInfo={false}
                          strokeColor={getProgressColor(monitorData.realTime.cpu_percent)}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                      <Card size="small" style={{ background: 'rgba(82,196,26,0.1)' }}>
                        <Statistic
                          title={<span><CloudOutlined /> 内存使用率</span>}
                          value={monitorData.realTime.memory_percent || 0}
                          suffix="%"
                          valueStyle={{ color: getProgressColor(monitorData.realTime.memory_percent) }}
                        />
                        <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '8px' }}>
                          {monitorData.realTime.memory_used_gb} / {monitorData.realTime.memory_total_gb} GB
                        </div>
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                      <Card size="small" style={{ background: 'rgba(250,173,20,0.1)' }}>
                        <Statistic
                          title={<span><HddOutlined /> 磁盘使用率</span>}
                          value={monitorData.realTime.disk_percent || 0}
                          suffix="%"
                          valueStyle={{ color: getProgressColor(monitorData.realTime.disk_percent) }}
                        />
                        <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '8px' }}>
                          {monitorData.realTime.disk_used_gb} / {monitorData.realTime.disk_total_gb} GB
                        </div>
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                      <Card size="small" style={{ background: 'rgba(24,144,255,0.1)' }}>
                        <Statistic
                          title={<span><ApiOutlined /> 磁盘 I/O</span>}
                          value={(monitorData.realTime.disk_read_mb || 0) + (monitorData.realTime.disk_write_mb || 0)}
                          suffix=" MB"
                          valueStyle={{ color: '#1890ff' }}
                        />
                        <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '8px' }}>
                          读: {monitorData.realTime.disk_read_mb} / 写: {monitorData.realTime.disk_write_mb} MB
                        </div>
                      </Card>
                    </Col>
                  </Row>
                </Card>
              )}
              <Card title="主机资源趋势" bordered={false}>
                <MetricLineChart 
                  data={monitorData.metrics} 
                  title="主机资源监控" 
                  height={300} 
                />
              </Card>
            </>
          )
        },
        {
          key: 'alerts',
          label: <span><AlertOutlined /> 告警历史 <Badge count={alertHistory.length} /></span>,
          children: (
            <Card bordered={false}>
              {alertHistory.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px 0', color: '#8c8c8c' }}>
                  <CheckCircleOutlined style={{ fontSize: '48px', color: '#52c41a', marginBottom: '16px' }} />
                  <p style={{ fontSize: '16px' }}>暂无告警，系统运行正常</p>
                </div>
              ) : (
                <Table
                  dataSource={alertHistory}
                  columns={[
                    {
                      title: '告警级别',
                      dataIndex: 'level',
                      key: 'level',
                      width: 100,
                      render: (level) => (
                        <Tag color={level === 'error' || level === 'critical' ? 'red' : level === 'warning' ? 'orange' : 'blue'}>
                          {level === 'error' || level === 'critical' ? '严重' : level === 'warning' ? '警告' : '信息'}
                        </Tag>
                      )
                    },
                    {
                      title: '告警类型',
                      dataIndex: 'type',
                      key: 'type',
                      width: 180,
                      render: (type) => <Tag color="purple">{type || '-'}</Tag>
                    },
                    {
                      title: '告警时间',
                      dataIndex: 'time',
                      key: 'time',
                      width: 150
                    },
                    {
                      title: '告警内容',
                      dataIndex: 'message',
                      key: 'message'
                    },
                    {
                      title: '处理状态',
                      dataIndex: 'status',
                      key: 'status',
                      width: 140,
                      render: (status, record) => {
                        const config = getStatusConfig(status || 'active', record.level);
                        return (
                          <Dropdown
                            menu={{
                              items: statusMenuItems(record.id, status || 'active'),
                              onClick: ({ key }) => handleStatusChange(record.id, key)
                            }}
                            trigger={['click']}
                          >
                            <Button
                              size="small"
                              style={{
                                background: config.bg,
                                color: config.color,
                                border: 'none',
                                borderRadius: '4px',
                                fontWeight: 500,
                                cursor: 'pointer',
                                transition: 'all 0.3s'
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.background = config.hoverBg;
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.background = config.bg;
                              }}
                            >
                              {config.text} <DownOutlined />
                            </Button>
                          </Dropdown>
                        );
                      }
                    },
                    {
                      title: '操作',
                      key: 'action',
                      width: 100,
                      render: (_, record) => (
                        <Button
                          type="primary"
                          size="small"
                          onClick={() => {
                            // 跳转到诊断页面，传递告警信息
                            navigate('/diagnosis', {
                              state: {
                                alertType: record.type,
                                alertMessage: record.message,
                                alertLevel: record.level,
                                alertTime: record.time
                              }
                            });
                          }}
                        >
                          诊断
                        </Button>
                      )
                    }
                  ]}
                  rowKey="id"
                  pagination={{ pageSize: 10 }}
                  size="small"
                />
              )}
            </Card>
          )
        }
      ]} />
    </div>
  );
};

export default Monitoring;
