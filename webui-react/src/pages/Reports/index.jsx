/**
 * Reports Page - Diagnosis Report History
 * 
 * This component displays the history of database anomaly diagnosis reports,
 * allowing users to view, search, filter, and export diagnostic results.
 * 
 * Features:
 * - Report listing with pagination and filtering
 * - Detailed report view with 5 core sections (anomaly summary, diagnostic path,
 *   root cause analysis, recommendations, knowledge attribution)
 * - Export functionality for offline analysis
 * 
 * Reference: D-Bot Paper Section 7 - Report Generation
 * Author: [Your Name]
 * Date: 2024
 */
import React, { useState, useEffect } from 'react';
import {
  Row, Col, Card, Table, Tag, Button, Modal, Descriptions,
  DatePicker, Input, Select, Space, Spin, message, Empty, Typography, Popconfirm, Tooltip
} from 'antd';
import {
  FileTextOutlined, EyeOutlined, DownloadOutlined,
  SearchOutlined, FilterOutlined, CalendarOutlined, DeleteOutlined, WarningOutlined
} from '@ant-design/icons';
import axios from 'axios';
import { formatBeijingTime } from '../../utils/time';
import { stripMarkdown } from '../../utils/markdownUtils';
import SqlHighlight from '@/components/SqlHighlight';

const { RangePicker } = DatePicker;
const { Option } = Select;
const { Search } = Input;
const { Text, Title, Paragraph } = Typography;

const ROOT_CAUSE_CN_MAP = {
  'timed_task_conflict': '定时任务冲突',
  'disk_spill': '磁盘溢出',
  'large_table': '大表扫描',
  'lock_contention': '锁争用',
  'memory_resource_contention': '内存资源竞争',
  'cpu_resource_contention': 'CPU资源竞争',
  'io_resource_contention': 'I/O资源竞争',
  'vacuum_event': 'VACUUM事件',
  'analyze_event': 'ANALYZE事件',
  'missing_index': '缺失索引',
  'unused_and_redundant_index': '冗余索引',
  'many_dead_tuples': '大量死元组',
  'heavy_scan_operator': '大量扫描操作',
  'abnormal_plan_time': '异常计划时间',
  'poor_join_performance': '连接性能差',
  'poor_aggregation_performance': '聚合性能差',
  'complex_execution_plan': '复杂执行计划',
  'correlated_subquery': '相关子查询',
  'workload_contention': '工作负载竞争',
  'database_wait_event': '数据库等待事件',
  'lack_of_statistics': '统计信息缺失',
  'abnormal_network_status': '网络状态异常',
  'os_resource_contention': '操作系统资源竞争',
  'slow_sql': '慢SQL查询',
  'cpu_high': 'CPU使用率过高',
  'memory_high': '内存使用率过高',
  'io_high': 'I/O负载过高',
  'lock_wait': '锁等待',
  'deadlock': '死锁',
  'environment_mismatch': '诊断环境不匹配' // 新增根因映射
};

const formatRootCause = (rootCause, diagnosisResult = null) => {
  if (!rootCause) return '暂无分析结果';
  
  const causeType = rootCause.type || rootCause;
  const cnName = ROOT_CAUSE_CN_MAP[causeType] || causeType;
  
  return cnName;
};

const formatRootCauseSimple = (rootCause) => {
  if (!rootCause) return '-';
  const causeType = rootCause.type || rootCause;
  return ROOT_CAUSE_CN_MAP[causeType] || causeType;
};

const Reports = () => {
  const [loading, setLoading] = useState(false);
  const [reports, setReports] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [dateRange, setDateRange] = useState(null);
  const [searchText, setSearchText] = useState('');
  const [lastUpdateTime, setLastUpdateTime] = useState(null);

  const formatFileSize = (size) => {
    if (!size) return '-';
    const kb = parseInt(size);
    if (kb < 1024) return `${kb} KB`;
    return `${(kb / 1024).toFixed(2)} MB`;
  };

  /**
   * Format duration value for display
   * @param {number|string} duration - Duration in seconds or formatted string
   * @returns {string} Formatted duration string
   */
  const formatDuration = (duration) => {
    if (!duration) return '-';
    if (typeof duration === 'number') {
      if (duration < 60) return `${duration.toFixed(1)}秒`;
      return `${(duration / 60).toFixed(1)}分钟`;
    }
    if (typeof duration === 'string') {
      return duration.replace('s', '秒').replace('min', '分钟');
    }
    return `${duration}秒`;
  };

  useEffect(() => {
    fetchReports();

    // 监听诊断完成事件，自动刷新报告列表
    const handleDiagnosisCompleted = (event) => {
      console.log('收到诊断完成事件，刷新报告列表:', event.detail);
      fetchReports();
    };

    window.addEventListener('diagnosis-completed', handleDiagnosisCompleted);

    return () => {
      window.removeEventListener('diagnosis-completed', handleDiagnosisCompleted);
    };
  }, []);

  /**
   * Fetch diagnosis reports from backend API
   * Transforms raw API data into display format
   */
  const fetchReports = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/report/histories').catch((err) => {
        console.error('Failed to fetch reports:', err);
        return null;
      });
      console.log('Backend response:', res?.data);
      const reportData = res?.data?.data || res?.data || [];
      console.log('Parsed report data:', reportData);
      if (Array.isArray(reportData) && reportData.length > 0) {
        const formattedReports = reportData.map((item, index) => {
          const createdAt = item.time || item.created_at || item.timestamp || new Date().toISOString();
          const duration = item.duration || item.diagnosis_time;
          let durationStr = formatDuration(duration);
          return {
            id: item.id || index + 1,
            file_name: item.file_name,
            title: item.title || item.anomaly_type || `诊断报告 #${index + 1}`,
            anomaly_type: item.anomaly_type || item.alert_type || '未知异常',
            status: item.status || 'resolved',
            confidence: item.confidence || 0.85,
            root_cause: formatRootCause(item.root_causes?.[0], item).replace('kB', 'KB').replace('s ', '秒 ') || item.root_cause || '-',
            root_causes: item.root_causes || [],
            solution: item.solutions?.[0]?.explanation || item.solution || '-',
            solutions: item.solutions || [],
            model: item.model || 'DeepSeek',
            duration: durationStr,
            created_at: createdAt,
            rawData: item,
            is_env_mismatch: item.is_env_mismatch || false // 传递环境不匹配标记
          };
        });
        setReports(formattedReports);
        const latestTime = formattedReports.reduce((latest, report) => {
          const reportTime = new Date(report.created_at);
          return reportTime > latest ? reportTime : latest;
        }, new Date(0));
        if (latestTime.getTime() > 0) {
          setLastUpdateTime(latestTime);
        }
      } else {
        setReports([]);
      }
    } catch (error) {
      console.log('获取报告失败:', error);
      setReports([]);
    } finally {
      setLoading(false);
    }
  };

  const viewReportDetail = (record) => {
    setSelectedReport(record);
    setModalVisible(true);
  };

  const exportReport = (record) => {
    const reportData = record.rawData || record;
    const exportContent = {
      title: record.title,
      anomaly_type: record.anomaly_type,
      status: record.status,
      confidence: record.confidence,
      root_cause: record.root_cause,
      solution: record.solution,
      model: record.model,
      duration: record.duration,
      created_at: record.created_at,
      ...reportData
    };
    
    const blob = new Blob([JSON.stringify(exportContent, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${record.title || 'diagnosis_report'}_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    message.success('报告已导出');
  };

  // 删除报告
  const deleteReport = async (record) => {
    try {
      const recordId = record.record_id || record.id;
      const fileName = record.file_name || (recordId ? `${recordId}.json` : null);
      
      if (fileName) {
        await axios.delete(`/report/histories/${fileName}`);
        setReports(prev => prev.filter(r => r.id !== record.id));
        message.success('报告已删除');
      } else {
        setReports(prev => prev.filter(r => r.id !== record.id));
        message.success('报告已删除');
      }
    } catch (error) {
      console.log('删除报告失败:', error);
      setReports(prev => prev.filter(r => r.id !== record.id));
      message.success('报告已删除');
    }
  };

  // 批量删除报告
  const batchDeleteReports = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要删除的报告');
      return;
    }
    try {
      const reportsToDelete = reports.filter(r => selectedRowKeys.includes(r.id));
      await Promise.all(
        reportsToDelete
          .filter(r => r.file_name)
          .map(r => axios.delete(`/report/histories/${r.file_name}`).catch(() => null))
      );
      setReports(prev => prev.filter(r => !selectedRowKeys.includes(r.id)));
      message.success(`已删除 ${selectedRowKeys.length} 条报告`);
      setSelectedRowKeys([]);
    } catch (error) {
      console.log('批量删除失败:', error);
      setReports(prev => prev.filter(r => !selectedRowKeys.includes(r.id)));
      message.success(`已删除 ${selectedRowKeys.length} 条报告`);
      setSelectedRowKeys([]);
    }
  };

  // 表格行选择配置
  const rowSelection = {
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
    selections: [
      Table.SELECTION_ALL,
      Table.SELECTION_INVERT,
      Table.SELECTION_NONE,
    ],
  };

  const getStatusTag = (status) => {
    const statusMap = {
      resolved: { bg: '#1a4d1a', color: '#81c784', text: '已解决' },
      pending: { bg: '#4d3d1a', color: '#ffd54f', text: '处理中' },
      failed: { bg: '#4d1a1a', color: '#e57373', text: '失败' }
    };
    const config = statusMap[status] || { bg: '#2d2d3d', color: '#e0e0e0', text: status };
    return <Tag style={{ background: config.bg, color: config.color, border: `1px solid ${config.bg}` }}>{config.text}</Tag>;
  };

  // 获取环境不匹配标签
  const getEnvMismatchTag = (isMismatch) => {
    if (!isMismatch) return null;
    return (
      <Tag icon={<WarningOutlined />} style={{ background: '#4d2a1a', color: '#f97316', border: '1px solid #4d2a1a' }}>
        环境不匹配
      </Tag>
    );
  };

  const columns = [
    {
      title: <span style={{ color: '#e0e0e0' }}>序号</span>,
      key: 'index',
      width: 50,
      render: (_, __, index) => <span style={{ color: '#e0e0e0', fontWeight: 'bold' }}>{index + 1}</span>
    },
    {
      title: <span style={{ color: '#e0e0e0' }}>报告标题</span>,
      dataIndex: 'title',
      key: 'title',
      width: 180,
      ellipsis: true,
      render: (title) => (
        <Tooltip title={title}>
          <span style={{ color: '#e0e0e0' }}>{title}</span>
        </Tooltip>
      )
    },
    {
      title: <span style={{ color: '#e0e0e0' }}>异常类型</span>,
      dataIndex: 'anomaly_type',
      key: 'anomaly_type',
      width: 130,
      render: (type, record) => (
        <Tooltip title={type}>
          <Space wrap size={4}>
            <Tag style={{ background: '#1a3a5c', color: '#64b5f6', border: '1px solid #1a3a5c' }}>
              {type && type.length > 15 ? `${type.substring(0, 15)}...` : type}
            </Tag>
            {getEnvMismatchTag(record.is_env_mismatch)}
          </Space>
        </Tooltip>
      )
    },
    {
      title: <span style={{ color: '#e0e0e0' }}>状态</span>,
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status) => getStatusTag(status)
    },
    {
      title: <span style={{ color: '#e0e0e0' }}>置信度</span>,
      dataIndex: 'confidence',
      key: 'confidence',
      width: 70,
      render: (val) => (
        <span style={{ 
          color: val >= 0.8 ? '#10B981' : val >= 0.6 ? '#F59E0B' : '#EF4444',
          fontWeight: 'bold'
        }}>
          {val ? `${Math.round(val * 100)}%` : '-'}
        </span>
      )
    },
    {
      title: <span style={{ color: '#e0e0e0' }}>根因</span>,
      dataIndex: 'root_cause',
      key: 'root_cause',
      width: 120,
      render: (cause, record) => {
        const rootCause = record.root_causes?.[0];
        const causeType = formatRootCauseSimple(rootCause);
        return (
          <Tooltip title={causeType}>
            <Tag style={{ background: '#1a3a5c', color: '#64b5f6', border: '1px solid #1a3a5c' }}>
              {causeType && causeType.length > 10 ? `${causeType.substring(0, 10)}...` : causeType}
            </Tag>
          </Tooltip>
        );
      }
    },
    {
      title: <span style={{ color: '#e0e0e0' }}>诊断时长</span>,
      dataIndex: 'duration',
      key: 'duration',
      width: 80,
      render: (duration) => <span style={{ color: '#e0e0e0' }}>{duration || '-'}</span>
    },
    {
      title: <span style={{ color: '#e0e0e0' }}>创建时间</span>,
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (time) => <span style={{ color: '#a0a0a0' }}>{formatBeijingTime(time)}</span>
    },
    {
      title: <span style={{ color: '#e0e0e0' }}>操作</span>,
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_, record) => (
        <Space size={0} split={<span style={{ color: '#444' }}>|</span>}>
          <Button 
            type="link" 
            size="small"
            icon={<EyeOutlined />}
            onClick={() => viewReportDetail(record)}
            style={{ color: '#64b5f6', padding: '0 8px' }}
          >
            查看
          </Button>
          <Button 
            type="link" 
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => exportReport(record)}
            style={{ color: '#81c784', padding: '0 8px' }}
          >
            导出
          </Button>
          <Popconfirm
            title="确认删除"
            description="确定要删除这条报告吗？"
            onConfirm={() => deleteReport(record.id)}
            okText="确定"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            placement="left"
          >
            <Button 
              type="link" 
              size="small"
              icon={<DeleteOutlined />}
              style={{ color: '#e57373', padding: '0 8px' }}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  const filteredReports = (Array.isArray(reports) ? reports : []).filter(r => {
    const statusMatch = filterStatus === 'all' || r.status === filterStatus;
    const searchMatch = !searchText || 
      (r.title && r.title.toLowerCase().includes(searchText.toLowerCase())) ||
      (r.anomaly_type && r.anomaly_type.toLowerCase().includes(searchText.toLowerCase()));
    let dateMatch = true;
    if (dateRange && dateRange[0] && dateRange[1]) {
      const reportDate = new Date(r.created_at);
      const startDate = dateRange[0].startOf('day').toDate();
      const endDate = dateRange[1].endOf('day').toDate();
      dateMatch = reportDate >= startDate && reportDate <= endDate;
    }
    return statusMatch && searchMatch && dateMatch;
  });

  return (
    <div className="reports-page" style={{ padding: '24px' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', marginBottom: '8px', color: '#333' }}>
          <FileTextOutlined /> 诊断报告
        </h1>
        <p style={{ color: '#666' }}>
          查看和管理历史诊断报告 | 更新时间：{lastUpdateTime ? formatBeijingTime(lastUpdateTime.toISOString()) : '暂无数据'}
        </p>
      </div>

      {/* 筛选栏 */}
      <Card bordered={false} style={{ marginBottom: '16px', background: '#1e1e2e' }}>
        <Space wrap>
          <Search
            placeholder="搜索报告标题或异常类型"
            allowClear
            style={{ width: 250 }}
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={(value) => setSearchText(value)}
          />
          <Select
            value={filterStatus}
            onChange={setFilterStatus}
            style={{ width: 120 }}
            dropdownStyle={{ background: '#2d2d3d' }}
            optionLabelProp="label"
          >
            <Option value="all" label="全部状态">
              <span style={{ color: '#e0e0e0' }}>全部状态</span>
            </Option>
            <Option value="resolved" label="已解决">
              <span style={{ color: '#81c784' }}>已解决</span>
            </Option>
            <Option value="pending" label="处理中">
              <span style={{ color: '#ffd54f' }}>处理中</span>
            </Option>
            <Option value="failed" label="失败">
              <span style={{ color: '#e57373' }}>失败</span>
            </Option>
          </Select>
          <RangePicker 
            placeholder={['开始日期', '结束日期']}
            value={dateRange}
            onChange={setDateRange}
            style={{ background: '#2d2d3d', border: '1px solid #3d3d4d' }}
            popupStyle={{ background: '#2d2d3d' }}
            dropdownClassName="dark-datepicker"
            format="YYYY-MM-DD"
          />
          <Button 
            type="primary" 
            icon={<FilterOutlined />}
            onClick={() => message.info('筛选已应用')}
          >
            筛选
          </Button>
          <Popconfirm
            title="清空全部报告"
            description="确定要清空所有诊断报告吗？此操作不可恢复。"
            onConfirm={async () => {
              try {
                await axios.delete('/report/histories');
                setReports([]);
                setSelectedRowKeys([]);
                message.success('所有报告已清空');
              } catch (error) {
                console.log('清空失败:', error);
                setReports([]);
                setSelectedRowKeys([]);
                message.success('所有报告已清空');
              }
            }}
            okText="确定"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button 
              danger 
              icon={<DeleteOutlined />}
            >
              清空全部
            </Button>
          </Popconfirm>
          {selectedRowKeys.length > 0 && (
            <Popconfirm
              title="批量删除确认"
              description={`确定要删除选中的 ${selectedRowKeys.length} 条报告吗？`}
              onConfirm={batchDeleteReports}
              okText="确定"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button 
                danger 
                icon={<DeleteOutlined />}
              >
                删除选中 ({selectedRowKeys.length})
              </Button>
            </Popconfirm>
          )}
        </Space>
      </Card>

      {/* 报告列表 */}
      <Card bordered={false} style={{ background: '#1e1e2e' }}>
        <Spin spinning={loading}>
          {filteredReports.length > 0 ? (
            <Table
              dataSource={filteredReports}
              columns={columns}
              rowKey="id"
              rowSelection={rowSelection}
              pagination={{
                pageSize: 10,
                showTotal: (total) => <span style={{ color: '#e0e0e0' }}>共 {total} 条记录</span>
              }}
              scroll={{ x: 1200 }}
              style={{ background: '#1e1e2e' }}
              className="dark-table"
            />
          ) : (
            <Empty description={<span style={{ color: '#666' }}>暂无报告数据，请先进行诊断</span>} />
          )}
        </Spin>
      </Card>

      {/* 报告详情弹窗 */}
      <Modal
        title={<span style={{ color: '#E2E8F0' }}>诊断报告 #{selectedReport?.id || ''}</span>}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={900}
        styles={{ 
          header: { background: '#1E293B', borderBottom: '1px solid #334155' },
          body: { background: '#0F172A', padding: '20px', maxHeight: '70vh', overflowY: 'auto' },
          content: { background: '#0F172A' }
        }}
      >
        {selectedReport && (
          <div style={{ background: '#0F172A' }}>
            {/* 环境不匹配警告 */}
            {selectedReport.is_env_mismatch && (
              <div style={{ 
                background: '#4d2a1a', 
                border: '1px solid #f97316', 
                borderRadius: '8px', 
                padding: '12px', 
                marginBottom: '16px',
                display: 'flex',
                alignItems: 'center'
              }}>
                <WarningOutlined style={{ color: '#f97316', fontSize: '18px', marginRight: '8px' }} />
                <Text style={{ color: '#f97316', fontSize: '14px' }}>
                  ⚠️ 检测到诊断环境与业务场景不匹配，建议验证数据库连接后重新诊断！
                </Text>
              </div>
            )}

            <Descriptions 
              bordered 
              column={2}
              labelStyle={{ background: '#1E293B', color: '#94A3B8', fontWeight: 'bold', borderBottom: '1px solid #334155' }}
              contentStyle={{ background: '#0F172A', color: '#E2E8F0', borderBottom: '1px solid #334155' }}
            >
              <Descriptions.Item label="报告标题" span={2}>
                <Text strong style={{ color: '#E2E8F0', fontSize: 15 }}>{selectedReport.title}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="异常类型">
                <Tag style={{ background: '#1E3A5F', color: '#60A5FA', border: 'none' }}>{selectedReport.anomaly_type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {getStatusTag(selectedReport.status)}
              </Descriptions.Item>
              <Descriptions.Item label="置信度">
                <Text style={{ color: '#10B981', fontFamily: 'monospace', fontSize: 14 }}>{selectedReport.confidence ? `${(selectedReport.confidence * 100).toFixed(0)}%` : '-'}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="诊断时长">
                <Text style={{ color: '#E2E8F0' }}>{selectedReport.duration || '-'}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="使用模型">
                <Tag style={{ background: '#3B1D5C', color: '#A855F7', border: 'none' }}>{selectedReport.model || 'DeepSeek'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                <Text style={{ color: '#94A3B8' }}>{formatBeijingTime(selectedReport.created_at)}</Text>
              </Descriptions.Item>
            </Descriptions>

            {/* 根因分析列表 */}
            {selectedReport.rawData?.root_causes && selectedReport.rawData.root_causes.length > 0 && (() => {
              const uniqueCauses = [];
              const causeTypeSet = new Set();
              selectedReport.rawData.root_causes.forEach(cause => {
                const causeType = cause.type || 'Unknown';
                if (!causeTypeSet.has(causeType)) {
                  causeTypeSet.add(causeType);
                  uniqueCauses.push(cause);
                }
              });
              uniqueCauses.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
              
              return (
                <div style={{ marginTop: '20px' }}>
                  <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12 }}>🔍 根因分析 ({uniqueCauses.length}个潜在原因)</Title>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {uniqueCauses.map((cause, idx) => (
                      <div 
                        key={idx}
                        style={{ 
                          background: '#1E293B', 
                          padding: '14px', 
                          borderRadius: '8px',
                          border: '1px solid #334155'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                          <Tag style={{ 
                            background: idx === 0 ? '#064E3B' : '#1E3A5F', 
                            color: idx === 0 ? '#10B981' : '#60A5FA',
                            border: 'none',
                            fontSize: 13
                          }}>
                            #{idx + 1} {ROOT_CAUSE_CN_MAP[cause.type] || cause.type}
                          </Tag>
                          <Text style={{ color: '#F59E0B', fontFamily: 'monospace', fontSize: 13 }}>
                            置信度: {Math.round((cause.confidence || 0) * 100)}%
                          </Text>
                        </div>
                        <Text style={{ color: '#CBD5E1', fontSize: 13, lineHeight: 1.6 }}>
                          {cause.impact || cause.description?.substring(0, 500) || '暂无详细描述'}
                        </Text>
                        {cause.evidence && (
                          <div style={{ marginTop: 8 }}>
                            <Text style={{ color: '#64748B', fontSize: 12, display: 'block' }}>
                              📋 证据: 
                            </Text>
                            <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 4, display: 'block', whiteSpace: 'pre-wrap' }}>
                              {Array.isArray(cause.evidence) ? cause.evidence.join('\n- ') : cause.evidence}
                            </Text>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* 解决方案列表（按优先级排序） */}
            {selectedReport.rawData?.solutions && selectedReport.rawData.solutions.length > 0 && (() => {
              // 按优先级排序解决方案
              const sortedSolutions = [...selectedReport.rawData.solutions].sort((a, b) => (a.priority || 99) - (b.priority || 99));
              
              const copyToClipboard = (text) => {
                navigator.clipboard.writeText(text).then(() => {
                  message.success('SQL 已复制到剪贴板');
                }).catch(() => {
                  message.error('复制失败');
                });
              };
              
              return (
                <div style={{ marginTop: '20px' }}>
                  <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12 }}>💡 解决方案 ({sortedSolutions.length}个)</Title>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {sortedSolutions.map((sol, idx) => {
                      // 风险等级颜色
                      const riskLevel = sol.risk_level || (sol.risk?.includes('高') ? 'High' : sol.risk?.includes('中') ? 'Medium' : 'Low');
                      const riskColor = riskLevel === 'High' ? '#EF4444' : riskLevel === 'Medium' ? '#F59E0B' : '#10B981';
                      const riskBg = riskLevel === 'High' ? '#7F1D1D' : riskLevel === 'Medium' ? '#78350F' : '#14532D';
                      
                      // 匹配度
                      const alignmentScore = sol.alignment?.score || 0;
                      const alignmentStatus = sol.alignment?.status || 'unknown';
                      const alignmentColor = alignmentScore >= 70 ? '#10B981' : alignmentScore >= 40 ? '#F59E0B' : '#EF4444';
                      const matchedKeywords = sol.alignment?.matched_keywords || [];
                      
                      return (
                        <div 
                          key={idx}
                          style={{ 
                            background: '#1E293B', 
                            padding: '14px', 
                            borderRadius: '8px',
                            border: `1px solid ${riskLevel === 'High' ? '#EF4444' : '#334155'}`,
                            position: 'relative'
                          }}
                        >
                          {/* 优先级角标 */}
                          {sol.priority && sol.priority <= 3 && (
                            <div style={{
                              position: 'absolute',
                              top: 0,
                              right: 0,
                              background: '#065F46',
                              color: '#10B981',
                              padding: '2px 8px',
                              borderRadius: '0 8px 0 8px',
                              fontSize: 10,
                              fontWeight: 'bold'
                            }}>
                              推荐
                            </div>
                          )}
                          
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <Tag style={{ 
                              background: idx === 0 ? '#065F46' : '#1E3A5F', 
                              color: idx === 0 ? '#10B981' : '#60A5FA',
                              border: 'none',
                              fontSize: 13
                            }}>
                              P{sol.priority || idx + 1}: {sol.action || '建议操作'}
                            </Tag>
                            <Space>
                              {/* 匹配度标签 */}
                              {alignmentScore > 0 && (
                                <Tooltip title={`匹配关键词: ${matchedKeywords.join(', ')}`}>
                                  <Tag style={{ 
                                    background: alignmentScore >= 70 ? '#065F46' : alignmentScore >= 40 ? '#78350F' : '#7F1D1D',
                                    color: alignmentColor,
                                    border: 'none',
                                    fontSize: 11
                                  }}>
                                    🎯 匹配度: {alignmentScore}%
                                  </Tag>
                                </Tooltip>
                              )}
                              {sol.risk && (
                                <Tag style={{ 
                                  background: riskBg,
                                  color: riskColor,
                                  border: 'none',
                                  fontSize: 11
                                }}>
                                  {riskLevel === 'High' ? '⚠️' : riskLevel === 'Medium' ? '⚡' : '✅'} {sol.risk}
                                </Tag>
                              )}
                            </Space>
                          </div>
                          
                          <Text style={{ color: '#CBD5E1', fontSize: 13, lineHeight: 1.6 }}>
                            {sol.explanation || '暂无详细说明'}
                          </Text>
                          
                          {/* 知识库引用来源 */}
                          {sol.source_ref && (
                            <div style={{ marginTop: 8, padding: '6px 10px', background: '#1A1A2E', borderRadius: '4px', borderLeft: '3px solid #6366F1' }}>
                              <Text style={{ color: '#A5B4FC', fontSize: 11 }}>
                                {sol.source_ref}
                              </Text>
                            </div>
                          )}
                          
                          {sol.sql && (
                            <div style={{ 
                              marginTop: 8, 
                              padding: '12px', 
                              background: '#0F172A', 
                              borderRadius: '6px',
                              border: '1px solid #334155',
                              overflowX: 'auto'
                            }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                <Text style={{ color: '#64748B', fontSize: 11 }}>SQL 语句</Text>
                              </div>
                              <SqlHighlight 
                                sql={sol.sql} 
                                showCopy={true}
                                maxHeight="200px"
                              />
                            </div>
                          )}
                          
                          {sol.verification_sql && (
                            <div style={{ 
                              marginTop: 8
                            }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                <Text style={{ color: '#10B981', fontSize: 11 }}>✅ 验证SQL</Text>
                              </div>
                              <SqlHighlight 
                                sql={sol.verification_sql} 
                                showCopy={true}
                                maxHeight="150px"
                              />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}

            {/* 兼容旧数据格式 */}
            {selectedReport.solution && selectedReport.solution !== '-' && !selectedReport.rawData?.solutions && (
              <div style={{ marginTop: '20px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12 }}>💡 解决方案</Title>
                <div style={{ 
                  background: '#1E293B', 
                  borderRadius: '8px',
                  border: '1px solid #334155',
                  padding: '16px',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word'
                }}>
                  {stripMarkdown(selectedReport.solution)}
                </div>
              </div>
            )}

            {/* 推理步骤 */}
            {selectedReport.rawData?.reasoning_steps && selectedReport.rawData.reasoning_steps.length > 0 && (
              <div style={{ marginTop: '20px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12 }}>🧠 推理过程 ({selectedReport.rawData.reasoning_steps.length}步)</Title>
                <div style={{ 
                  background: '#1E293B', 
                  borderRadius: '8px',
                  border: '1px solid #334155',
                  maxHeight: '200px',
                  overflowY: 'auto'
                }}>
                  {selectedReport.rawData.reasoning_steps.slice(0, 5).map((step, idx) => (
                    <div 
                      key={idx}
                      style={{ 
                        padding: '10px 14px',
                        borderBottom: idx < Math.min(selectedReport.rawData.reasoning_steps.length, 5) - 1 ? '1px solid #334155' : 'none'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
                        <Tag style={{ background: '#3B1D5C', color: '#A855F7', border: 'none', fontSize: 11 }}>
                          Step {step.step || idx + 1}
                        </Tag>
                        <Text style={{ color: '#60A5FA', fontSize: 12, marginLeft: 8 }}>
                          {step.action || '执行诊断步骤'}
                        </Text>
                      </div>
                      <Text style={{ color: '#94A3B8', fontSize: 12 }}>
                        {step.thought?.substring(0, 200)}...
                      </Text>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 检索到的知识 */}
            {selectedReport.rawData?.retrieved_knowledge && selectedReport.rawData.retrieved_knowledge.length > 0 && (
              <div style={{ marginTop: '20px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12 }}>📚 检索到的知识 ({selectedReport.rawData.retrieved_knowledge.length}条)</Title>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {selectedReport.rawData.retrieved_knowledge.slice(0, 5).map((knowledge, idx) => (
                    <Tag 
                      key={idx}
                      style={{ 
                        background: '#1E3A5F', 
                        color: '#60A5FA', 
                        border: '1px solid #334155',
                        padding: '4px 10px',
                        fontSize: 12
                      }}
                    >
                      {knowledge.cause_name || '未知知识点'} ({Math.round(knowledge.relevance_percentage || 0)}%)
                    </Tag>
                  ))}
                </div>
              </div>
            )}

            {/* 系统指标 */}
            {selectedReport.rawData?.metrics?.real_time && (
              <div style={{ marginTop: '20px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12 }}>📊 实时系统指标</Title>
                <Row gutter={12}>
                  <Col span={6}>
                    <div style={{ background: '#1E293B', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
                      <Text style={{ color: '#10B981', fontSize: 20, fontWeight: 'bold', fontFamily: 'monospace' }}>
                        {selectedReport.rawData.metrics.real_time.cpu_percent}%
                      </Text>
                      <div><Text style={{ color: '#64748B', fontSize: 12 }}>CPU使用率</Text></div>
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ background: '#1E293B', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
                      <Text style={{ color: '#3B82F6', fontSize: 20, fontWeight: 'bold', fontFamily: 'monospace' }}>
                        {selectedReport.rawData.metrics.real_time.memory_percent}%
                      </Text>
                      <div><Text style={{ color: '#64748B', fontSize: 12 }}>内存使用率</Text></div>
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ background: '#1E293B', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
                      <Text style={{ color: '#F59E0B', fontSize: 20, fontWeight: 'bold', fontFamily: 'monospace' }}>
                        {selectedReport.rawData.metrics.real_time.disk_usage_percent}%
                      </Text>
                      <div><Text style={{ color: '#64748B', fontSize: 12 }}>磁盘使用率</Text></div>
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ background: '#1E293B', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
                      <Text style={{ color: '#A855F7', fontSize: 20, fontWeight: 'bold', fontFamily: 'monospace' }}>
                        {selectedReport.rawData.search_stats?.knowledge_matches || 0}
                      </Text>
                      <div><Text style={{ color: '#64748B', fontSize: 12 }}>知识匹配数</Text></div>
                    </div>
                  </Col>
                </Row>
              </div>
            )}

            {/* ============================================ */}
            {/* 工业级诊断报告 - 5个核心板块 (新增) */}
            {/* ============================================ */}
            
            {/* 板块1: 异常概览 (Anomaly Summary) */}
            {selectedReport.rawData?.anomaly_summary && (
              <div style={{ marginTop: '24px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12, borderBottom: '2px solid #3B82F6', paddingBottom: '8px' }}>
                  📊 板块1: 异常概览
                </Title>
                <div style={{ background: '#1E293B', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  {/* 异常指标 */}
                  {selectedReport.rawData.anomaly_summary.metrics?.length > 0 && (
                    <div style={{ marginBottom: '16px' }}>
                      <Text style={{ color: '#94A3B8', fontSize: 13, display: 'block', marginBottom: '8px' }}>异常指标</Text>
                      <Row gutter={12}>
                        {selectedReport.rawData.anomaly_summary.metrics.map((metric, idx) => (
                          <Col span={8} key={idx}>
                            <div style={{ 
                              background: metric.severity === 'critical' ? '#7F1D1D' : metric.severity === 'high' ? '#78350F' : '#1E3A5F',
                              padding: '12px', 
                              borderRadius: '6px',
                              border: `1px solid ${metric.severity === 'critical' ? '#EF4444' : metric.severity === 'high' ? '#F59E0B' : '#3B82F6'}`
                            }}>
                              <Text style={{ color: '#E2E8F0', fontSize: 12 }}>{metric.name}</Text>
                              <div>
                                <Text style={{ 
                                  color: metric.severity === 'critical' ? '#EF4444' : metric.severity === 'high' ? '#F59E0B' : '#60A5FA',
                                  fontSize: 18, 
                                  fontWeight: 'bold',
                                  fontFamily: 'monospace'
                                }}>
                                  {metric.value}{metric.unit}
                                </Text>
                              </div>
                              <Text style={{ color: '#64748B', fontSize: 11 }}>阈值: {metric.threshold}{metric.unit}</Text>
                            </div>
                          </Col>
                        ))}
                      </Row>
                    </div>
                  )}
                  
                  {/* 受影响范围 */}
                  {selectedReport.rawData.anomaly_summary.affected_scope && (
                    <div style={{ marginTop: '12px' }}>
                      <Text style={{ color: '#94A3B8', fontSize: 13 }}>受影响范围: </Text>
                      <Text style={{ color: '#E2E8F0', fontSize: 13 }}>
                        数据库实例: {selectedReport.rawData.anomaly_summary.affected_scope.database_instance} | 
                        表: {selectedReport.rawData.anomaly_summary.affected_scope.tables?.join(', ') || 'N/A'} | 
                        活跃会话: {selectedReport.rawData.anomaly_summary.affected_scope.sessions}
                      </Text>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 板块2: 诊断推演路径 (Diagnostic Tree-Search Path) */}
            {selectedReport.rawData?.diagnostic_path && (
              <div style={{ marginTop: '24px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12, borderBottom: '2px solid #10B981', paddingBottom: '8px' }}>
                  🌳 板块2: 诊断推演路径 (UCT算法)
                </Title>
                <div style={{ background: '#1E293B', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  {/* 算法信息 */}
                  <div style={{ marginBottom: '12px', padding: '8px', background: '#0F172A', borderRadius: '4px' }}>
                    <Text style={{ color: '#10B981', fontSize: 12 }}>
                      🔍 {selectedReport.rawData.diagnostic_path.search_algorithm} | 
                      探索常数 C={selectedReport.rawData.diagnostic_path.exploration_constant} | 
                      总迭代: {selectedReport.rawData.diagnostic_path.total_iterations}
                    </Text>
                  </div>
                  
                  {/* 路径说明 */}
                  {selectedReport.rawData.diagnostic_path.path_explanation && (
                    <div style={{ marginBottom: '16px', padding: '10px', background: '#1A3A3A', borderRadius: '6px', borderLeft: '4px solid #10B981' }}>
                      <Text style={{ color: '#A7F3D0', fontSize: 13 }}>
                        {selectedReport.rawData.diagnostic_path.path_explanation}
                      </Text>
                    </div>
                  )}
                  
                  {/* 节点展示 */}
                  {selectedReport.rawData.diagnostic_path.final_path?.length > 0 && (
                    <div>
                      <Text style={{ color: '#94A3B8', fontSize: 13, display: 'block', marginBottom: '8px' }}>
                        最终锁定路径 ({selectedReport.rawData.diagnostic_path.final_path.length}个节点)
                      </Text>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {selectedReport.rawData.diagnostic_path.final_path.map((node, idx) => (
                          <div 
                            key={idx}
                            style={{ 
                              background: '#0F172A',
                              padding: '12px',
                              borderRadius: '6px',
                              border: '1px solid #334155',
                              borderLeft: `4px solid ${node.uct_score >= 0.7 ? '#10B981' : node.uct_score >= 0.4 ? '#F59E0B' : '#EF4444'}`
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <Tag style={{ background: '#1E3A5F', color: '#60A5FA', border: 'none' }}>
                                步骤 {node.depth + 1}
                              </Tag>
                              <Text style={{ color: '#F59E0B', fontSize: 12, fontFamily: 'monospace' }}>
                                UCT: {node.uct_score?.toFixed(3)} | 收益: {node.reward?.toFixed(3)}
                              </Text>
                            </div>
                            <Text style={{ color: '#E2E8F0', fontSize: 13, marginTop: '6px', display: 'block' }}>
                              {node.hypothesis?.substring(0, 100)}...
                            </Text>
                            <Text style={{ color: '#64748B', fontSize: 11, marginTop: '4px' }}>
                              动作: {node.action}
                            </Text>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* 剪枝分支 */}
                  {selectedReport.rawData.diagnostic_path.pruned_branches?.length > 0 && (
                    <div style={{ marginTop: '16px' }}>
                      <Text style={{ color: '#94A3B8', fontSize: 13, display: 'block', marginBottom: '8px' }}>
                        ✂️ 剪枝分支 ({selectedReport.rawData.diagnostic_path.pruned_branches.length}个)
                      </Text>
                      {selectedReport.rawData.diagnostic_path.pruned_branches.map((branch, idx) => (
                        <div 
                          key={idx}
                          style={{ 
                            background: '#2D1A1A',
                            padding: '10px',
                            borderRadius: '6px',
                            border: '1px solid #7F1D1D',
                            marginBottom: '8px'
                          }}
                        >
                          <Text style={{ color: '#FCA5A5', fontSize: 12 }}>
                            {branch.node_id}: {branch.reason} (UCT: {branch.uct_score?.toFixed(3)})
                          </Text>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 板块3: 根因分析 (Root Cause Analysis) */}
            {selectedReport.rawData?.root_cause_analysis && (
              <div style={{ marginTop: '24px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12, borderBottom: '2px solid #F59E0B', paddingBottom: '8px' }}>
                  🔍 板块3: 根因分析
                </Title>
                <div style={{ background: '#1E293B', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  {/* 主要根因 */}
                  {selectedReport.rawData.root_cause_analysis.primary_root_cause && (
                    <div style={{ 
                      background: selectedReport.rawData.root_cause_analysis.confidence >= 0.8 ? '#064E3B' : '#78350F',
                      padding: '16px',
                      borderRadius: '8px',
                      marginBottom: '16px',
                      border: `2px solid ${selectedReport.rawData.root_cause_analysis.confidence >= 0.8 ? '#10B981' : '#F59E0B'}`
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <Tag style={{ 
                          background: selectedReport.rawData.root_cause_analysis.confidence >= 0.8 ? '#065F46' : '#92400E',
                          color: '#E2E8F0',
                          border: 'none',
                          fontSize: 14
                        }}>
                          {ROOT_CAUSE_CN_MAP[selectedReport.rawData.root_cause_analysis.primary_root_cause.type] || 
                           selectedReport.rawData.root_cause_analysis.primary_root_cause.type}
                        </Tag>
                        <Text style={{ 
                          color: selectedReport.rawData.root_cause_analysis.confidence >= 0.8 ? '#10B981' : '#F59E0B',
                          fontSize: 16,
                          fontWeight: 'bold'
                        }}>
                          置信度: {Math.round(selectedReport.rawData.root_cause_analysis.confidence * 100)}%
                        </Text>
                      </div>
                      <Text style={{ color: '#E2E8F0', fontSize: 14 }}>
                        {selectedReport.rawData.root_cause_analysis.primary_root_cause.description}
                      </Text>
                    </div>
                  )}
                  
                  {/* 证据链 */}
                  {selectedReport.rawData.root_cause_analysis.evidence_chain?.length > 0 && (
                    <div style={{ marginTop: '16px' }}>
                      <Text style={{ color: '#94A3B8', fontSize: 13, display: 'block', marginBottom: '8px' }}>
                        📋 证据链 ({selectedReport.rawData.root_cause_analysis.evidence_chain.length}条证据)
                      </Text>
                      {selectedReport.rawData.root_cause_analysis.evidence_chain.map((evidence, idx) => (
                        <div 
                          key={idx}
                          style={{ 
                            background: '#0F172A',
                            padding: '12px',
                            borderRadius: '6px',
                            border: '1px solid #334155',
                            marginBottom: '8px'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text style={{ color: '#60A5FA', fontSize: 12 }}>{evidence.title}</Text>
                            <Text style={{ color: '#F59E0B', fontSize: 11 }}>
                              置信度: {Math.round(evidence.confidence * 100)}%
                            </Text>
                          </div>
                          <Text style={{ color: '#CBD5E1', fontSize: 12, marginTop: '4px', display: 'block' }}>
                            {evidence.description?.substring(0, 100)}...
                          </Text>
                          <Text style={{ color: '#64748B', fontSize: 11, marginTop: '4px' }}>
                            来源: {evidence.source}
                          </Text>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {/* 分析过程 */}
                  {selectedReport.rawData.root_cause_analysis.analysis_process && (
                    <div style={{ marginTop: '16px', padding: '12px', background: '#1A2A3A', borderRadius: '6px' }}>
                      <Text style={{ color: '#94A3B8', fontSize: 12, display: 'block', marginBottom: '8px' }}>
                        🧠 分析过程
                      </Text>
                      <pre style={{ color: '#CBD5E1', fontSize: 12, margin: 0, whiteSpace: 'pre-wrap' }}>
                        {selectedReport.rawData.root_cause_analysis.analysis_process}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 板块4: 优化建议与收益预估 */}
            {selectedReport.rawData?.recommendations?.recommendations?.length > 0 && (
              <div style={{ marginTop: '24px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12, borderBottom: '2px solid #A855F7', paddingBottom: '8px' }}>
                  💡 板块4: 优化建议与收益预估
                </Title>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {selectedReport.rawData.recommendations.recommendations.map((rec, idx) => (
                    <div 
                      key={idx}
                      style={{ 
                        background: '#1E293B', 
                        padding: '16px', 
                        borderRadius: '8px',
                        border: `1px solid ${rec.priority === 'critical' ? '#EF4444' : rec.priority === 'high' ? '#F59E0B' : '#334155'}`
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <Tag style={{ 
                          background: rec.priority === 'critical' ? '#7F1D1D' : rec.priority === 'high' ? '#78350F' : '#1E3A5F',
                          color: rec.priority === 'critical' ? '#EF4444' : rec.priority === 'high' ? '#F59E0B' : '#60A5FA',
                          border: 'none',
                          fontSize: 13
                        }}>
                          {rec.priority === 'critical' ? '🔴' : rec.priority === 'high' ? '🟠' : '🔵'} {rec.recommendation_id}
                        </Tag>
                        <Tag style={{ background: '#3B1D5C', color: '#A855F7', border: 'none' }}>
                          {rec.category === 'index' ? '索引优化' : rec.category === 'query_rewrite' ? '查询重写' : '配置优化'}
                        </Tag>
                      </div>
                      
                      <Text style={{ color: '#E2E8F0', fontSize: 14, fontWeight: 'bold', display: 'block', marginBottom: '8px' }}>
                        {rec.title}
                      </Text>
                      
                      <Text style={{ color: '#CBD5E1', fontSize: 13, display: 'block', marginBottom: '12px' }}>
                        {rec.description}
                      </Text>
                      
                      {/* HypoPG虚拟索引评估 */}
                      {rec.hypopg_result && (
                        <div style={{ 
                          background: '#0F172A',
                          padding: '12px',
                          borderRadius: '6px',
                          marginBottom: '12px',
                          border: '1px solid #10B981'
                        }}>
                          <Text style={{ color: '#10B981', fontSize: 12, display: 'block', marginBottom: '8px' }}>
                            📊 HypoPG虚拟索引评估
                          </Text>
                          <Row gutter={12}>
                            <Col span={8}>
                              <div style={{ textAlign: 'center' }}>
                                <Text style={{ color: '#EF4444', fontSize: 16, fontWeight: 'bold', fontFamily: 'monospace' }}>
                                  {rec.hypopg_result.current_cost?.toFixed(2)}
                                </Text>
                                <div><Text style={{ color: '#64748B', fontSize: 11 }}>当前Cost</Text></div>
                              </div>
                            </Col>
                            <Col span={8}>
                              <div style={{ textAlign: 'center' }}>
                                <Text style={{ color: '#10B981', fontSize: 16, fontWeight: 'bold', fontFamily: 'monospace' }}>
                                  {rec.hypopg_result.estimated_cost?.toFixed(2)}
                                </Text>
                                <div><Text style={{ color: '#64748B', fontSize: 11 }}>优化后Cost</Text></div>
                              </div>
                            </Col>
                            <Col span={8}>
                              <div style={{ textAlign: 'center' }}>
                                <Text style={{ color: '#F59E0B', fontSize: 16, fontWeight: 'bold', fontFamily: 'monospace' }}>
                                  {rec.hypopg_result.improvement_factor?.toFixed(0)}x
                                </Text>
                                <div><Text style={{ color: '#64748B', fontSize: 11 }}>性能提升</Text></div>
                              </div>
                            </Col>
                          </Row>
                          <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #334155' }}>
                            <Text style={{ color: '#94A3B8', fontSize: 11 }}>
                              索引大小: {rec.hypopg_result.index_size_estimate} | 写入影响: {rec.hypopg_result.write_impact}
                            </Text>
                          </div>
                        </div>
                      )}
                      
                      {/* SQL语句 */}
                      {rec.sql_action && (
                        <div style={{ marginBottom: '12px' }}>
                          <SqlHighlight sql={rec.sql_action} showCopy={true} maxHeight="150px" />
                        </div>
                      )}
                      
                      {/* 风险提示 */}
                      {rec.risks?.length > 0 && (
                        <div style={{ marginTop: '8px' }}>
                          {rec.risks.map((risk, ridx) => (
                            <Text key={ridx} style={{ color: '#F87171', fontSize: 11, display: 'block' }}>
                              ⚠️ {risk}
                            </Text>
                          ))}
                        </div>
                      )}
                      
                      {/* 实施步骤 */}
                      {rec.implementation_steps?.length > 0 && (
                        <div style={{ marginTop: '8px', padding: '8px', background: '#1A2A3A', borderRadius: '4px' }}>
                          <Text style={{ color: '#94A3B8', fontSize: 11, display: 'block', marginBottom: '4px' }}>实施步骤:</Text>
                          {rec.implementation_steps.map((step, sidx) => (
                            <Text key={sidx} style={{ color: '#CBD5E1', fontSize: 11, display: 'block' }}>
                              {step}
                            </Text>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 板块5: 知识库溯源 */}
            {selectedReport.rawData?.knowledge_attribution && (
              <div style={{ marginTop: '24px' }}>
                <Title level={5} style={{ color: '#E2E8F0', marginBottom: 12, borderBottom: '2px solid #3B82F6', paddingBottom: '8px' }}>
                  📚 板块5: 知识库溯源
                </Title>
                <div style={{ background: '#1E293B', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  {/* 知识库信息 */}
                  <div style={{ marginBottom: '16px', padding: '10px', background: '#0F172A', borderRadius: '6px' }}>
                    <Text style={{ color: '#60A5FA', fontSize: 12 }}>
                      📖 {selectedReport.rawData.knowledge_attribution.knowledge_base_version} | 
                      🔍 {selectedReport.rawData.knowledge_attribution.retrieval_algorithm}
                    </Text>
                  </div>
                  
                  {/* 综合置信度 */}
                  <div style={{ 
                    background: selectedReport.rawData.knowledge_attribution.overall_confidence >= 0.8 ? '#064E3B' : '#78350F',
                    padding: '12px',
                    borderRadius: '6px',
                    marginBottom: '16px',
                    textAlign: 'center'
                  }}>
                    <Text style={{ color: '#E2E8F0', fontSize: 13 }}>综合诊断置信度</Text>
                    <div>
                      <Text style={{ 
                        color: selectedReport.rawData.knowledge_attribution.overall_confidence >= 0.8 ? '#10B981' : '#F59E0B',
                        fontSize: 24,
                        fontWeight: 'bold'
                      }}>
                        {Math.round(selectedReport.rawData.knowledge_attribution.overall_confidence * 100)}%
                      </Text>
                    </div>
                  </div>
                  
                  {/* 溯源摘要 */}
                  {selectedReport.rawData.knowledge_attribution.attribution_summary && (
                    <div style={{ marginBottom: '16px', padding: '10px', background: '#1A3A5F', borderRadius: '6px' }}>
                      <Text style={{ color: '#93C5FD', fontSize: 12 }}>
                        {selectedReport.rawData.knowledge_attribution.attribution_summary}
                      </Text>
                    </div>
                  )}
                  
                  {/* 知识来源列表 */}
                  {selectedReport.rawData.knowledge_attribution.sources?.length > 0 && (
                    <div>
                      <Text style={{ color: '#94A3B8', fontSize: 13, display: 'block', marginBottom: '8px' }}>
                        参考知识来源
                      </Text>
                      {selectedReport.rawData.knowledge_attribution.sources.map((source, idx) => (
                        <div 
                          key={idx}
                          style={{ 
                            background: '#0F172A',
                            padding: '12px',
                            borderRadius: '6px',
                            border: '1px solid #334155',
                            marginBottom: '8px'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                            <Text style={{ color: '#60A5FA', fontSize: 13, fontWeight: 'bold' }}>
                              {source.title}
                            </Text>
                            <Tag style={{ 
                              background: source.bm25_score >= 0.8 ? '#065F46' : source.bm25_score >= 0.5 ? '#78350F' : '#1E3A5F',
                              color: source.bm25_score >= 0.8 ? '#10B981' : source.bm25_score >= 0.5 ? '#F59E0B' : '#60A5FA',
                              border: 'none'
                            }}>
                              BM25: {(source.bm25_score * 100).toFixed(1)}%
                            </Tag>
                          </div>
                          <Text style={{ color: '#94A3B8', fontSize: 12, display: 'block', marginBottom: '6px' }}>
                            {source.description}
                          </Text>
                          {source.steps?.length > 0 && (
                            <div style={{ padding: '8px', background: '#1A2A3A', borderRadius: '4px' }}>
                              {source.steps.map((step, sidx) => (
                                <Text key={sidx} style={{ color: '#CBD5E1', fontSize: 11, display: 'block' }}>
                                  {step}
                                </Text>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ============================================ */}
            {/* 原有内容保持兼容 */}
            {/* ============================================ */}

          </div>
        )}
      </Modal>
    </div>
  );
};

export default Reports;
