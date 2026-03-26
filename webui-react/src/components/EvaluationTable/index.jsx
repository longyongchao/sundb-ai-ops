/**
 * 实验评估看板组件
 * 用于展示异常注入和诊断结果的评估表格
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Select, InputNumber,
  message, Popconfirm, Statistic, Row, Col, Divider, Badge,
  Progress, Timeline, Alert, Spin, Tabs
} from 'antd';
import {
  PlayCircleOutlined, ClearOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ThunderboltOutlined, DeleteOutlined,
  UserOutlined, TeamOutlined, MessageOutlined, LoadingOutlined,
  BugOutlined, SyncOutlined, ApiOutlined, BranchesOutlined
} from '@ant-design/icons';
import axios from 'axios';
import MultiExpertCollaboration from '@/components/MultiExpertCollaboration';

const { Option } = Select;

// 异常类型配置
const ANOMALY_TYPES = [
  { value: 'slow_sql', label: '慢SQL (CPU波动)', color: '#a61d24' },
  { value: 'lock', label: '锁竞争 (死锁/行锁)', color: '#ad6800' },
  { value: 'log', label: '错误日志', color: '#1d39c4' }
];

// localStorage 键名
const STORAGE_KEY = 'd-bot-evaluation-results';

const EvaluationTable = () => {
  const [loading, setLoading] = useState(false);
  const [injecting, setInjecting] = useState(false);
  const [results, setResults] = useState([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedType, setSelectedType] = useState('slow_sql');
  const [duration, setDuration] = useState(10);
  const [threads, setThreads] = useState(3);
  const [count, setCount] = useState(50);
  
  // 诊断流程状态
  const [diagnosisProgress, setDiagnosisProgress] = useState(0);
  const [diagnosisSteps, setDiagnosisSteps] = useState([]);
  const [showDiagnosisFlow, setShowDiagnosisFlow] = useState(false);
  const [currentExpert, setCurrentExpert] = useState(null);
  const [multiAgentResult, setMultiAgentResult] = useState(null);
  const [diagnosisPhase, setDiagnosisPhase] = useState('');

  // 加载评估结果
  useEffect(() => {
    loadResults();
  }, []);

  // 从 localStorage 加载结果
  const loadResults = () => {
    setLoading(true);
    
    // 先尝试从后端加载
    axios.get('/api/evaluation/results')
      .then(res => {
        console.log('后端返回数据:', res.data);
        if (res.data?.data && res.data.data.length > 0) {
          // 补充 anomaly_label 字段
          const dataWithLabel = res.data.data.map(item => ({
            ...item,
            anomaly_label: item.anomaly_label || ANOMALY_TYPES.find(t => t.value === item.anomaly_type)?.label || item.anomaly_type
          }));
          setResults(dataWithLabel);
          // 同步到 localStorage
          localStorage.setItem(STORAGE_KEY, JSON.stringify(dataWithLabel));
        } else {
          // 从 localStorage 加载
          const stored = localStorage.getItem(STORAGE_KEY);
          console.log('localStorage 数据:', stored);
          if (stored) {
            const parsedData = JSON.parse(stored);
            console.log('解析后的数据:', parsedData);
            setResults(parsedData);
          }
        }
      })
      .catch((err) => {
        console.log('API 错误:', err);
        // 从 localStorage 加载
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          setResults(JSON.parse(stored));
        }
      })
      .finally(() => setLoading(false));
  };

  // 保存结果到 localStorage
  const saveResults = (data) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  };

  // 一键注入异常
  const handleInject = async () => {
    setInjecting(true);
    setModalVisible(false);
    setShowDiagnosisFlow(true);
    setDiagnosisProgress(0);
    setDiagnosisSteps([]);
    
    // 立即设置初始数据，让组件有内容显示
    setMultiAgentResult({
      anomaly_type: selectedType,
      description: `模拟异常: ${ANOMALY_TYPES.find(t => t.value === selectedType)?.label}`,
      severity: 'high',
      assigned_experts: selectedType === 'slow_sql' 
        ? ['workload_expert', 'cpu_expert', 'io_expert']
        : selectedType === 'lock'
        ? ['workload_expert', 'database_expert']
        : ['cpu_expert', 'memory_expert', 'io_expert'],
      experts: [],
      cross_review: { reviews: [], final_consensus: '' },
      expert_consensus_rate: 0
    });
    
    const startTime = Date.now();

    // 诊断流程步骤
    const flowSteps = [
      { phase: 'inject', progress: 5, msg: '🚀 正在注入异常场景...', type: 'start' },
      { phase: 'detect', progress: 15, msg: '🔍 检测到异常信号', type: 'detect' },
      { phase: 'knowledge', progress: 25, msg: '📚 正在检索 Summary-Tree 知识库...', type: 'knowledge' },
      { phase: 'assigner', progress: 35, msg: '🎯 Expert Assigner 正在分配专家...', type: 'assigner' },
      { phase: 'expert1', progress: 45, msg: '🔥 专家开始并行诊断...', type: 'expert', expert: 'expert_1' },
      { phase: 'expert2', progress: 60, msg: '� 正在分析诊断结果...', type: 'expert', expert: 'expert_2' },
      { phase: 'review', progress: 75, msg: '🔄 专家正在进行 Cross Review...', type: 'review' },
      { phase: 'consensus', progress: 85, msg: '🤝 正在达成专家共识...', type: 'consensus' },
      { phase: 'report', progress: 95, msg: '📝 正在生成诊断报告...', type: 'report' },
    ];

    // 启动进度动画
    let stepIndex = 0;
    const progressInterval = setInterval(() => {
      if (stepIndex < flowSteps.length) {
        const step = flowSteps[stepIndex];
        setDiagnosisProgress(step.progress);
        setDiagnosisSteps(prev => [...prev, { ...step, time: new Date().toLocaleTimeString() }]);
        setDiagnosisPhase(step.phase);
        stepIndex++;
      }
    }, 500);

    try {
      // 调用注入接口
      message.loading({ content: `正在注入 ${selectedType} 异常...`, key: 'inject' });
      const response = await axios.post('/api/anomaly/inject', {
        anomaly_type: selectedType,
        duration: duration,
        threads: threads,
        count: count
      });

      if (response.data?.code === 200) {
        // 自动启动诊断
        const diagResponse = await axios.post('/diagnose/quick', {
          alert_type: selectedType,
          description: `模拟异常: ${ANOMALY_TYPES.find(t => t.value === selectedType)?.label}`,
          severity: 'high'
        });
        
        // 使用后端返回的真实诊断时长
        const diagTime = diagResponse.data?.data?.diagnosis_time || 0;

        clearInterval(progressInterval);
        setDiagnosisProgress(100);
        setDiagnosisSteps(prev => [...prev, { 
          phase: 'done', 
          progress: 100, 
          msg: '✅ 诊断完成！', 
          type: 'done',
          time: new Date().toLocaleTimeString()
        }]);

        // 从后端响应中获取数据
        const rootCause = diagResponse.data?.data?.root_causes?.[0]?.type || '未知';
        const suggestion = diagResponse.data?.data?.solutions?.[0]?.explanation || '无建议';
        const knowledgeMatches = diagResponse.data?.data?.search_stats?.knowledge_matches || 0;
        const isHit = knowledgeMatches > 0;

        // 优先使用后端返回的真实 multi_agent_result
        const backendMultiAgentResult = diagResponse.data?.data?.multi_agent_result;
        
        if (backendMultiAgentResult) {
          // 使用后端返回的真实数据
          setMultiAgentResult({
            ...backendMultiAgentResult,
            anomaly_type: selectedType,
            description: `模拟异常: ${ANOMALY_TYPES.find(t => t.value === selectedType)?.label}`,
            severity: 'high',
          });
        } else {
          // 降级：使用模拟数据
          const assignedExperts = selectedType === 'slow_sql' 
            ? ['workload_expert', 'cpu_expert', 'io_expert']
            : selectedType === 'lock'
            ? ['workload_expert', 'database_expert']
            : ['cpu_expert', 'memory_expert', 'io_expert'];

          const agentResult = {
            anomaly_type: selectedType,
            description: `模拟异常: ${ANOMALY_TYPES.find(t => t.value === selectedType)?.label}`,
            severity: 'high',
            collaboration_time: `${diagTime.toFixed(2)}s`,
            assigner: {
              assigned_experts: assignedExperts
            },
            assigned_experts: assignedExperts,
            experts: [
              {
                expert_type: assignedExperts[0],
                name: assignedExperts[0],
                role: '专家诊断',
                status: 'completed',
                confidence: isHit ? 0.92 : 0.75,
                findings: `诊断完成，根因: ${rootCause}`,
                diagnosis_time: diagTime * 0.35,
              },
              {
                expert_type: assignedExperts[1] || assignedExperts[0],
                name: assignedExperts[1] || assignedExperts[0],
                role: '专家诊断',
                status: 'completed',
                confidence: isHit ? 0.88 : 0.70,
                findings: isHit ? '发现潜在问题，建议进一步分析' : '未发现明显异常',
                diagnosis_time: diagTime * 0.30,
              },
              assignedExperts[2] ? {
                expert_type: assignedExperts[2],
                name: assignedExperts[2],
                role: '专家诊断',
                status: 'completed',
                confidence: isHit ? 0.85 : 0.72,
                findings: isHit ? '支持诊断结论' : '系统运行正常',
                diagnosis_time: diagTime * 0.35,
              } : null
            ].filter(Boolean),
            cross_review: {
              reviews: [
                { reviewer: assignedExperts[0], target: assignedExperts[1] || assignedExperts[0], agreement_score: isHit ? 0.85 : 0.70 },
              ],
              final_consensus: isHit 
                ? `综合各专家意见，根因为: ${rootCause}。建议: ${suggestion}`
                : '各专家未发现明显异常，建议持续监控'
            },
            final_consensus: isHit 
              ? `综合各专家意见，根因为: ${rootCause}。建议: ${suggestion}`
              : '各专家未发现明显异常，建议持续监控',
            expert_consensus_rate: isHit ? 0.85 : 0.70
          };
          setMultiAgentResult(agentResult);
        }
        message.success({ content: '诊断完成', key: 'inject' });

        // 添加评估结果
        const newResult = {
          id: results.length + 1,
          anomaly_type: selectedType,
          anomaly_label: ANOMALY_TYPES.find(t => t.value === selectedType)?.label,
          detection_time: new Date().toLocaleString(),
          diagnosis_time: diagTime,
          root_cause: rootCause,
          is_hit: isHit,
          hit_status: isHit ? 'Hit' : 'Miss',
          suggestion: suggestion
        };

        const updatedResults = [...results, newResult];
        setResults(updatedResults);
        saveResults(updatedResults);

        // 同步到后端
        axios.post('/api/evaluation/add', {
          anomaly_type: selectedType,
          diagnosis_time: diagTime,
          root_cause: rootCause,
          is_hit: isHit,
          suggestion: suggestion
        }).catch(() => {});

        // 通知 Reports 页面刷新诊断报告列表
        window.dispatchEvent(new CustomEvent('diagnosis-completed', {
          detail: {
            anomaly_type: selectedType,
            root_cause: rootCause,
            diagnosis_time: diagTime
          }
        }));

      } else {
        clearInterval(progressInterval);
        message.error({ content: `注入失败: ${response.data?.msg}`, key: 'inject' });
        setShowDiagnosisFlow(false);
      }
    } catch (error) {
      clearInterval(progressInterval);
      message.error({ content: `操作失败: ${error.message}`, key: 'inject' });
      setShowDiagnosisFlow(false);
    } finally {
      setInjecting(false);
    }
  };

  // 检查是否命中知识库
  const checkKnowledgeHit = (rootCause, suggestion) => {
    const keywords = [
      'index', '索引', 'lock', '锁', 'deadlock', '死锁',
      'slow', '慢', 'cpu', 'memory', '内存', 'io', '磁盘',
      'query', '查询', 'scan', '扫描', 'vacuum', 'bloat'
    ];
    
    const text = (rootCause + ' ' + suggestion).toLowerCase();
    return keywords.some(kw => text.includes(kw.toLowerCase()));
  };

  // 清空结果
  const handleClear = async () => {
    setResults([]);
    localStorage.removeItem(STORAGE_KEY);
    await axios.delete('/api/evaluation/clear').catch(() => {});
    message.success('评估结果已清空');
  };

  // 删除单条记录
  const handleDelete = (id) => {
    const updatedResults = results.filter(r => r.id !== id);
    // 重新编号
    const renumberedResults = updatedResults.map((r, index) => ({
      ...r,
      id: index + 1
    }));
    setResults(renumberedResults);
    saveResults(renumberedResults);
    message.success('已删除该记录');
  };

  // 批量删除选中记录
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  
  const handleBatchDelete = () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要删除的记录');
      return;
    }
    const updatedResults = results.filter(r => !selectedRowKeys.includes(r.id));
    const renumberedResults = updatedResults.map((r, index) => ({
      ...r,
      id: index + 1
    }));
    setResults(renumberedResults);
    saveResults(renumberedResults);
    setSelectedRowKeys([]);
    message.success(`已删除 ${selectedRowKeys.length} 条记录`);
  };

  // 表格行选择配置
  const rowSelection = {
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
  };

  // 表格列定义
  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60
    },
    {
      title: '异常场景',
      dataIndex: 'anomaly_label',
      key: 'anomaly_label',
      render: (text, record) => {
        const type = ANOMALY_TYPES.find(t => t.value === record.anomaly_type);
        return <Tag color={type?.color || 'default'}>{text}</Tag>;
      }
    },
    {
      title: '检测时间',
      dataIndex: 'detection_time',
      key: 'detection_time',
      width: 180
    },
    {
      title: '诊断耗时',
      dataIndex: 'diagnosis_time',
      key: 'diagnosis_time',
      render: (time) => <span>{time?.toFixed(2) || '-'}s</span>
    },
    {
      title: '根因命中',
      dataIndex: 'hit_status',
      key: 'hit_status',
      render: (status, record) => (
        <Badge 
          status={record.is_hit ? 'success' : 'error'} 
          text={record.is_hit ? 'Hit' : 'Miss'}
        />
      ),
      filters: [
        { text: 'Hit', value: 'Hit' },
        { text: 'Miss', value: 'Miss' }
      ],
      onFilter: (value, record) => record.hit_status === value
    },
    {
      title: '诊断根因',
      dataIndex: 'root_cause',
      key: 'root_cause',
      ellipsis: true
    },
    {
      title: '建议摘要',
      dataIndex: 'suggestion',
      key: 'suggestion',
      ellipsis: true
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Popconfirm
          title="确定删除此记录？"
          onConfirm={() => handleDelete(record.id)}
          okText="确定"
          cancelText="取消"
        >
          <Button 
            type="text" 
            danger 
            icon={<DeleteOutlined />}
            size="small"
          />
        </Popconfirm>
      )
    }
  ];

  // 统计数据
  const hitCount = results.filter(r => r.is_hit).length;
  const missCount = results.filter(r => !r.is_hit).length;
  const avgTime = results.length > 0 
    ? (results.reduce((sum, r) => sum + (r.diagnosis_time || 0), 0) / results.length).toFixed(2)
    : 0;

  return (
    <Card 
      title={
        <Space>
          <ThunderboltOutlined />
          <span>实验评估看板</span>
        </Space>
      }
      extra={
        <Space>
          {selectedRowKeys.length > 0 && (
            <Popconfirm
              title={`确定删除选中的 ${selectedRowKeys.length} 条记录？`}
              onConfirm={handleBatchDelete}
              okText="确定"
              cancelText="取消"
            >
              <Button danger icon={<DeleteOutlined />}>
                删除选中 ({selectedRowKeys.length})
              </Button>
            </Popconfirm>
          )}
          <Button 
            type="primary" 
            icon={<PlayCircleOutlined />}
            loading={injecting}
            onClick={() => setModalVisible(true)}
          >
            一键注入测试场景
          </Button>
          <Button 
            icon={<ReloadOutlined />}
            onClick={loadResults}
          >
            刷新
          </Button>
          <Popconfirm
            title="确定清空所有评估结果？"
            onConfirm={handleClear}
          >
            <Button danger icon={<ClearOutlined />}>
              清空
            </Button>
          </Popconfirm>
        </Space>
      }
    >
      {/* 诊断流程动画 - 使用新的多专家协作组件 */}
      {showDiagnosisFlow && (
        <Tabs 
          defaultActiveKey="flow" 
          style={{ marginBottom: 16 }}
          items={[
            {
              key: 'flow',
              label: (
                <span>
                  <BranchesOutlined />
                  协作流程
                </span>
              ),
              children: (
                <MultiExpertCollaboration 
                  collaborationData={multiAgentResult}
                  isVisible={true}
                  isRunning={injecting}
                  currentPhase={diagnosisPhase}
                />
              )
            },
            {
              key: 'log',
              label: (
                <span>
                  <ApiOutlined />
                  诊断日志
                </span>
              ),
              children: (
                <Card variant="borderless">
                  <div style={{ marginBottom: 16 }}>
                    <Progress 
                      percent={diagnosisProgress} 
                      status={injecting ? 'active' : 'success'}
                      strokeColor={{ '0%': '#108ee9', '100%': '#87d068' }}
                    />
                  </div>
                  <Timeline
                    items={diagnosisSteps.map((step, index) => ({
                      color: step.type === 'done' ? 'green' : 
                             step.type === 'expert' ? 'blue' :
                             index === diagnosisSteps.length - 1 ? 'processing' : 'gray',
                      children: (
                        <div>
                          <span style={{ color: '#8c8c8c', fontSize: 12 }}>{step.time}</span>
                          <div>{step.msg}</div>
                        </div>
                      )
                    }))}
                  />
                </Card>
              )
            }
          ]}
        />
      )}

      {/* 统计面板 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Statistic 
            title="总测试数" 
            value={results.length} 
            prefix={<ThunderboltOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic 
            title="命中数" 
            value={hitCount}
            valueStyle={{ color: '#3f8600' }}
            prefix={<CheckCircleOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic 
            title="未命中数" 
            value={missCount}
            valueStyle={{ color: '#cf1322' }}
            prefix={<CloseCircleOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic 
            title="平均诊断耗时" 
            value={avgTime}
            suffix="秒"
          />
        </Col>
      </Row>

      <Divider />

      {/* 评估表格 */}
      <Table
        dataSource={results}
        columns={columns}
        rowKey="id"
        loading={loading}
        rowSelection={rowSelection}
        pagination={{ pageSize: 10 }}
        scroll={{ x: 1000 }}
        locale={{ emptyText: '暂无评估数据，点击"一键注入测试场景"开始' }}
      />

      {/* 注入配置弹窗 */}
      <Modal
        title="配置异常注入"
        open={modalVisible}
        onOk={handleInject}
        onCancel={() => setModalVisible(false)}
        okText="开始注入"
        cancelText="取消"
        confirmLoading={injecting}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 8 }}>异常类型:</label>
            <Select 
              value={selectedType} 
              onChange={setSelectedType}
              style={{ width: '100%' }}
            >
              {ANOMALY_TYPES.map(type => (
                <Option key={type.value} value={type.value}>
                  <Tag color={type.color}>{type.label}</Tag>
                </Option>
              ))}
            </Select>
          </div>

          {selectedType !== 'log' && (
            <div>
              <label style={{ display: 'block', marginBottom: 8 }}>持续时间 (秒):</label>
              <InputNumber 
                value={duration}
                onChange={setDuration}
                min={5}
                max={120}
                style={{ width: '100%' }}
              />
            </div>
          )}

          {selectedType === 'lock' && (
            <div>
              <label style={{ display: 'block', marginBottom: 8 }}>线程数:</label>
              <InputNumber 
                value={threads}
                onChange={setThreads}
                min={2}
                max={20}
                style={{ width: '100%' }}
              />
            </div>
          )}

          {selectedType === 'log' && (
            <div>
              <label style={{ display: 'block', marginBottom: 8 }}>日志数量:</label>
              <InputNumber 
                value={count}
                onChange={setCount}
                min={10}
                max={1000}
                style={{ width: '100%' }}
              />
            </div>
          )}

          <Divider />

          <div style={{ color: '#8c8c8c', fontSize: 12 }}>
            <p>说明：</p>
            <ul style={{ paddingLeft: 20 }}>
              <li><b>慢SQL</b>: 向测试表写入数据并执行无索引查询，模拟CPU波动</li>
              <li><b>锁竞争</b>: 多线程并发更新，模拟死锁或行锁</li>
              <li><b>错误日志</b>: 生成PostgreSQL格式的错误日志文件</li>
            </ul>
          </div>
        </Space>
      </Modal>
    </Card>
  );
};

export default EvaluationTable;