/**
 * @fileoverview Dashboard 页面 - 数据库监控仪表盘
 * @author [Your Name]
 * @date 2024/01/01
 * @description 实现论文 D-Bot Section 2 - 数据库性能异常监控
 *              支持实时系统指标监控（CPU、内存、磁盘、网络）
 *              提供异常类型分布、指标相关性分析等可视化功能
 */
import React, { useState, useEffect } from 'react';
import { Row, Col, Card, Statistic, Alert, Spin, message, Progress, Tag, Button } from 'antd';
import {
  DashboardOutlined,
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  HddOutlined,
  CloudOutlined,
  SyncOutlined
} from '@ant-design/icons';
import { MetricLineChart, AnomalyPieChart, DiagnosisHeatMap } from '@/components/Charts';
import axios from 'axios';

const Dashboard = () => {
  const [loading, setLoading] = useState(false);
  const [metricsData, setMetricsData] = useState(null);
  const [anomalyData, setAnomalyData] = useState(null);
  const [correlationData, setCorrelationData] = useState(null);
  const [realTimeMetrics, setRealTimeMetrics] = useState(null);
  const [systemStatus, setSystemStatus] = useState({
    totalDatabases: 0,
    activeAnomalies: 0,
    resolvedToday: 0,
    dbConnections: 0,
    dbConnected: false
  });

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 10000);
    return () => clearInterval(interval);
  }, []);

  /**
   * 获取仪表盘数据
   * 从后端 API 获取实时指标、异常分布、相关性矩阵等数据
   */
  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/api/dashboard/metrics').catch(() => null);
      if (response?.data?.data) {
        const data = response.data.data;
        
        if (data.metrics) {
          setMetricsData({
            timestamps: data.metrics.timestamps || [],
            cpu: data.metrics.cpu || [],
            memory: data.metrics.memory || [],
            disk_io: data.metrics.disk_io || [],
            network: data.metrics.network || []
          });
          
          if (data.metrics.real_time) {
            setRealTimeMetrics(data.metrics.real_time);
          }
        }
        
        if (data.anomalies && Array.isArray(data.anomalies)) {
          setAnomalyData(data.anomalies);
        }
        
        if (data.correlation) {
          setCorrelationData({
            metrics: data.correlation.metrics || [],
            correlation_matrix: data.correlation.correlation_matrix || []
          });
        }
        
        if (data.database_status) {
          setSystemStatus(prev => ({
            ...prev,
            dbConnected: data.database_status.connected,
            dbConnections: data.stats?.db_connections || data.metrics?.connections || 0,
            activeQueries: data.metrics?.active_queries || 0
          }));
        }
        
        if (data.stats) {
          const avgTime = data.stats.avg_response_time;
          let avgTimeStr = '-';
          if (avgTime) {
            if (avgTime < 1) {
              avgTimeStr = `${Math.round(avgTime * 1000)}ms`;
            } else if (avgTime < 60) {
              avgTimeStr = `${avgTime.toFixed(1)}s`;
            } else {
              avgTimeStr = `${(avgTime / 60).toFixed(1)}min`;
            }
          }
          setSystemStatus(prev => ({
            ...prev,
            totalDatabases: data.stats.total_databases || 0,
            activeAnomalies: data.stats.active_anomalies || 0,
            resolvedToday: data.stats.resolved_today || 0,
            dbConnections: data.stats.db_connections || prev.dbConnections,
            avgResponseTime: avgTimeStr,
            hallucinationInterceptions: data.stats.hallucination_interceptions || 0,
            environmentMismInterceptions: data.stats.environment_mismatches || 0,
            dataAnomalyInterceptions: data.stats.data_anomaly_interceptions || 0
          }));
        }
      }
    } catch (error) {
      console.log('获取数据失败:', error);
      setMetricsData({
        timestamps: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'],
        cpu: [45, 52, 78, 95, 88, 65, 42],
        memory: [60, 62, 75, 82, 78, 70, 65],
        disk_io: [20, 25, 45, 85, 72, 35, 22],
        network: [10, 15, 30, 55, 48, 25, 18]
      });
      setAnomalyData([
        { value: 35, name: '慢查询执行' },
        { value: 25, name: '资源耗尽' },
        { value: 20, name: '数据库挂起' },
        { value: 15, name: '数据库崩溃' },
        { value: 5, name: '其他异常' }
      ]);
    } finally {
      setLoading(false);
    }
  };
  
  /**
   * 根据百分比获取进度条颜色
   * @param {number} percent - 百分比值
   * @returns {string} 颜色值
   */
  const getProgressColor = (percent) => {
    if (percent >= 90) return '#ff4d4f';
    if (percent >= 70) return '#faad14';
    return '#52c41a';
  };

  return (
    <div className="dashboard-page" style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', marginBottom: '8px' }}>
            <DashboardOutlined /> 数据库监控仪表盘
          </h1>
          <p style={{ color: '#8c8c8c' }}>实时监控数据库性能指标和异常状态（每10秒自动刷新）</p>
        </div>
        <Button 
          type="primary" 
          icon={<SyncOutlined spin={loading} />} 
          onClick={fetchDashboardData}
          loading={loading}
        >
          刷新数据
        </Button>
      </div>

      {realTimeMetrics && (
        <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
          <Col xs={24} sm={12} md={6}>
            <Card 
              hoverable 
              title={<span><DesktopOutlined /> CPU 使用率</span>}
              extra={<Tag style={{ background: realTimeMetrics.cpu_percent >= 80 ? 'rgba(255, 77, 79, 0.15)' : realTimeMetrics.cpu_percent >= 60 ? 'rgba(250, 173, 20, 0.15)' : 'rgba(82, 196, 26, 0.15)', color: realTimeMetrics.cpu_percent >= 80 ? '#ff4d4f' : realTimeMetrics.cpu_percent >= 60 ? '#faad14' : '#52c41a', border: '1px solid ' + (realTimeMetrics.cpu_percent >= 80 ? 'rgba(255, 77, 79, 0.3)' : realTimeMetrics.cpu_percent >= 60 ? 'rgba(250, 173, 20, 0.3)' : 'rgba(82, 196, 26, 0.3)') }}>实时</Tag>}
            >
              <Progress 
                type="dashboard" 
                percent={realTimeMetrics.cpu_percent} 
                strokeColor={getProgressColor(realTimeMetrics.cpu_percent)}
                format={percent => `${percent}%`}
              />
              <div style={{ textAlign: 'center', marginTop: 8, color: '#8c8c8c', fontSize: 12 }}>
                {realTimeMetrics.cpu_cores || '-'} 核心
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card 
              hoverable 
              title={<span><CloudOutlined /> 内存使用率</span>}
              extra={<Tag style={{ background: realTimeMetrics.memory_percent >= 80 ? 'rgba(255, 77, 79, 0.15)' : realTimeMetrics.memory_percent >= 60 ? 'rgba(250, 173, 20, 0.15)' : 'rgba(82, 196, 26, 0.15)', color: realTimeMetrics.memory_percent >= 80 ? '#ff4d4f' : realTimeMetrics.memory_percent >= 60 ? '#faad14' : '#52c41a', border: '1px solid ' + (realTimeMetrics.memory_percent >= 80 ? 'rgba(255, 77, 79, 0.3)' : realTimeMetrics.memory_percent >= 60 ? 'rgba(250, 173, 20, 0.3)' : 'rgba(82, 196, 26, 0.3)') }}>实时</Tag>}
            >
              <Progress 
                type="dashboard" 
                percent={realTimeMetrics.memory_percent} 
                strokeColor={getProgressColor(realTimeMetrics.memory_percent)}
                format={percent => `${percent}%`}
              />
              <div style={{ textAlign: 'center', marginTop: 8, color: '#8c8c8c', fontSize: 12 }}>
                {realTimeMetrics.memory_used_gb} / {realTimeMetrics.memory_total_gb} GB
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card 
              hoverable 
              title={<span><HddOutlined /> 磁盘使用率</span>}
              extra={<Tag style={{ background: realTimeMetrics.disk_percent >= 80 ? 'rgba(255, 77, 79, 0.15)' : realTimeMetrics.disk_percent >= 60 ? 'rgba(250, 173, 20, 0.15)' : 'rgba(82, 196, 26, 0.15)', color: realTimeMetrics.disk_percent >= 80 ? '#ff4d4f' : realTimeMetrics.disk_percent >= 60 ? '#faad14' : '#52c41a', border: '1px solid ' + (realTimeMetrics.disk_percent >= 80 ? 'rgba(255, 77, 79, 0.3)' : realTimeMetrics.disk_percent >= 60 ? 'rgba(250, 173, 20, 0.3)' : 'rgba(82, 196, 26, 0.3)') }}>实时</Tag>}
            >
              <Progress 
                type="dashboard" 
                percent={realTimeMetrics.disk_percent} 
                strokeColor={getProgressColor(realTimeMetrics.disk_percent)}
                format={percent => `${percent}%`}
              />
              <div style={{ textAlign: 'center', marginTop: 8, color: '#8c8c8c', fontSize: 12 }}>
                {realTimeMetrics.disk_used_gb} / {realTimeMetrics.disk_total_gb} GB
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card 
              hoverable 
              title={<span><DatabaseOutlined /> 数据库连接</span>}
              extra={<Tag style={{ background: systemStatus.dbConnected ? 'rgba(82, 196, 26, 0.15)' : 'rgba(255, 77, 79, 0.15)', color: systemStatus.dbConnected ? '#52c41a' : '#ff4d4f', border: '1px solid ' + (systemStatus.dbConnected ? 'rgba(82, 196, 26, 0.3)' : 'rgba(255, 77, 79, 0.3)') }}>{systemStatus.dbConnected ? '已连接' : '未连接'}</Tag>}
            >
              <Statistic
                title="活跃连接数"
                value={systemStatus.dbConnections || 0}
                suffix={`/ ${systemStatus.activeQueries || 0} 查询`}
              />
              <div style={{ marginTop: 16 }}>
                <Statistic
                  title="进程数"
                  value={realTimeMetrics.process_count || '-'}
                  valueStyle={{ fontSize: 16 }}
                />
              </div>
            </Card>
          </Col>
        </Row>
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable>
            <Statistic
              title="监控数据库数"
              value={systemStatus.totalDatabases}
              prefix={<DatabaseOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable>
            <Statistic
              title="活跃异常"
              value={systemStatus.activeAnomalies}
              prefix={<AlertOutlined style={{ color: '#ff4d4f' }} />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable>
            <Statistic
              title="今日已解决"
              value={systemStatus.resolvedToday}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable>
            <Statistic
              title="平均响应时间"
              value={systemStatus.avgResponseTime}
              prefix={<ClockCircleOutlined style={{ color: '#722ed1' }} />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
      </Row>

      {systemStatus.activeAnomalies > 0 && (
        <Alert
          message="检测到活跃异常"
          description={`当前有 ${systemStatus.activeAnomalies} 个未处理的数据库异常，请及时查看诊断报告。`}
          type="info"
          showIcon
          closable
          style={{ marginBottom: '24px' }}
        />
      )}
      
      {/* 新增：幻觉拦截监控卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col span={24}>
          <Card 
            title={
              <span>
                <AlertOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
                一致性防火墙 - 幻觉拦截监控
              </span>
            }
            bordered={false}
            style={{ backgroundColor: '#1e1e1e' }}
          >
            <Row gutter={[16, 16]}>
              <Col span={8}>
                <Statistic 
                  title="幻觉拦截次数"
                  value={systemStatus.hallucinationInterceptions || 0}
                  valueStyle={{ color: '#52c41a', fontSize: 24 }}
                />
              </Col>
              <Col span={8}>
                <Statistic 
                  title="环境不匹配拦截"
                  value={systemStatus.environmentMismInterceptions || 0}
                  valueStyle={{ color: '#faad14', fontSize: 24 }}
                />
              </Col>
              <Col span={8}>
                <Statistic 
                  title="数据异常拦截"
                  value={systemStatus.dataAnomalyInterceptions || 0}
                  valueStyle={{ color: '#ff4d4f', fontSize: 24 }}
                />
              </Col>
            </Row>
            <div style={{ marginTop: 16, color: '#8c8c8c', fontSize: 12 }}>
              一. 一致性防火墙会在推理链终点检测到结论与推导矛盾时，会强制修正结论，确保诊断结果的的真实性。
              2. 诚实地报告"环境不匹配"比给出一个错误的根因更重要
            </div>
            <div style={{ marginTop: 16, color: '#8c8c8c', fontSize: 12 }}>
              <Tag color="green">系统鲁棒性指标</Tag>
              <Tag color="blue">拦截记录</Tag>
            </div>
            <div style={{ marginTop: 16, fontSize: 13, color: '#8c8c8c' }}>
              一致性防火墙模块已自动检测推理链与结论的逻辑一致性。当检测到矛盾时，会强制修正结论，确保诊断结果的真实性。
            </div>
          </Card>
        </Col>
      </Row>

      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={16}>
            <Card title="资源指标监控" bordered={false}>
              <MetricLineChart 
                data={metricsData} 
                title="实时资源使用率"
                height={350}
              />
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="异常类型分布" bordered={false}>
              <AnomalyPieChart 
                data={anomalyData}
                title="本周异常统计"
                height={350}
              />
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
          <Col span={24}>
            <Card 
              title="指标相关性分析" 
              bordered={false}
              extra={<span style={{ color: '#8c8c8c', fontSize: '12px' }}>指标相关性分析</span>}
            >
              <DiagnosisHeatMap 
                data={correlationData}
                title="数据库指标相关性矩阵"
                height={450}
              />
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
};

export default Dashboard;
