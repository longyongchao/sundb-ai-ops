import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  BranchesOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CommentOutlined,
  DatabaseOutlined,
  EyeOutlined,
  FieldTimeOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  ReloadOutlined,
  StarOutlined,
} from '@ant-design/icons';
import { evolutionAPI } from '@/utils/api';
import './index.scss';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

const EMPTY_METRICS = {
  total_cases: 0,
  total_feedback: 0,
  avg_outcome_score: 0,
  labels: {},
  statuses: {},
};

const LABEL_META = {
  positive_case: { color: 'success', text: '正样本', icon: <CheckCircleOutlined /> },
  negative_case: { color: 'error', text: '负样本', icon: <CloseCircleOutlined /> },
  uncertain_case: { color: 'warning', text: '待确认', icon: <HistoryOutlined /> },
};

const STATUS_META = {
  captured: { color: 'processing', text: '已采集' },
  evaluated: { color: 'success', text: '已评分' },
};

const formatDate = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatJson = (value) => {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch (error) {
    return String(value ?? '');
  }
};

const normalizeList = (value) => {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
};

const scoreToPercent = (value) => {
  const number = Number(value || 0);
  const percent = number <= 1 ? number * 100 : number;
  return Math.max(0, Math.min(100, Math.round(percent)));
};

const renderLabelTag = (label) => {
  const meta = LABEL_META[label] || { color: 'default', text: label || '未标注', icon: <HistoryOutlined /> };
  return (
    <Tag color={meta.color} icon={meta.icon}>
      {meta.text}
    </Tag>
  );
};

const renderStatusTag = (status) => {
  const meta = STATUS_META[status] || { color: 'default', text: status || '未知' };
  return <Tag color={meta.color}>{meta.text}</Tag>;
};

const JsonBlock = ({ value }) => (
  <pre className="evolution-json-block">{formatJson(value)}</pre>
);

const Evolution = () => {
  const [cases, setCases] = useState([]);
  const [metrics, setMetrics] = useState(EMPTY_METRICS);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ label: undefined, status: undefined, anomaly_type: undefined });
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [caseDetail, setCaseDetail] = useState(null);
  const [previewCase, setPreviewCase] = useState(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackTarget, setFeedbackTarget] = useState(null);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackForm] = Form.useForm();

  const loadCases = useCallback(async (next = {}) => {
    const nextPagination = next.pagination || pagination;
    const nextFilters = next.filters || filters;
    const query = {
      limit: nextPagination.pageSize,
      offset: (nextPagination.current - 1) * nextPagination.pageSize,
      ...nextFilters,
    };

    Object.keys(query).forEach((key) => {
      if (query[key] === undefined || query[key] === '') {
        delete query[key];
      }
    });

    setLoading(true);
    try {
      const [caseResponse, metricResponse] = await Promise.all([
        evolutionAPI.listCases(query),
        evolutionAPI.getMetrics(),
      ]);

      setCases(caseResponse?.cases || []);
      setMetrics(metricResponse || EMPTY_METRICS);
      setPagination({
        ...nextPagination,
        total: caseResponse?.total || 0,
      });
    } catch (error) {
      setCases([]);
      setMetrics(EMPTY_METRICS);
    } finally {
      setLoading(false);
    }
  }, [filters, pagination]);

  useEffect(() => {
    loadCases();
  }, []);

  const labelCounts = metrics.labels || {};
  const statusCounts = metrics.statuses || {};
  const avgScorePercent = scoreToPercent(metrics.avg_outcome_score);

  const metricCards = [
    {
      key: 'cases',
      title: '案例总数',
      value: metrics.total_cases || 0,
      icon: <DatabaseOutlined />,
      suffix: '条',
    },
    {
      key: 'feedback',
      title: '反馈数',
      value: metrics.total_feedback || 0,
      icon: <CommentOutlined />,
      suffix: '条',
    },
    {
      key: 'score',
      title: '平均评分',
      value: avgScorePercent,
      icon: <StarOutlined />,
      suffix: '%',
    },
    {
      key: 'evaluated',
      title: '已评分案例',
      value: statusCounts.evaluated || 0,
      icon: <CheckCircleOutlined />,
      suffix: '条',
    },
  ];

  const handleRefresh = () => loadCases();

  const handleFilterChange = (key, value) => {
    const nextFilters = { ...filters, [key]: value || undefined };
    const nextPagination = { ...pagination, current: 1 };
    setFilters(nextFilters);
    setPagination(nextPagination);
    loadCases({ filters: nextFilters, pagination: nextPagination });
  };

  const handleTableChange = (nextPagination) => {
    const updated = {
      current: nextPagination.current,
      pageSize: nextPagination.pageSize,
      total: pagination.total,
    };
    setPagination(updated);
    loadCases({ pagination: updated });
  };

  const openDetail = async (record) => {
    setPreviewCase(record);
    setCaseDetail(null);
    setDrawerOpen(true);
    setDetailLoading(true);
    try {
      const response = await evolutionAPI.getCase(record.id);
      setCaseDetail(response || { case: record, feedback: [] });
    } catch (error) {
      setCaseDetail({ case: record, feedback: [] });
    } finally {
      setDetailLoading(false);
    }
  };

  const openFeedback = (record) => {
    setFeedbackTarget(record);
    feedbackForm.setFieldsValue({
      score: 85,
      accepted: true,
      recovered: true,
      recurrence: false,
      reason: '',
    });
    setFeedbackOpen(true);
  };

  const submitFeedback = async () => {
    const values = await feedbackForm.validateFields();
    setFeedbackSubmitting(true);
    try {
      await evolutionAPI.createFeedback({
        evolution_case_id: feedbackTarget?.id,
        score: values.score,
        reason: values.reason || '',
        accepted: values.accepted,
        recurrence: values.recurrence,
        metric_recovery: {
          recovered: values.recovered,
        },
        raw_feedback: {
          source: 'webui_evolution_demo',
          submitted_at: new Date().toISOString(),
        },
      });
      message.success('反馈已写入，自进化评分已更新');
      setFeedbackOpen(false);
      await loadCases();
      if (drawerOpen && (caseDetail?.case?.id === feedbackTarget?.id || previewCase?.id === feedbackTarget?.id)) {
        await openDetail(feedbackTarget);
      }
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const activeCase = caseDetail?.case || previewCase;
  const feedbackItems = caseDetail?.feedback || [];
  const traceSnapshot = activeCase?.trace_snapshot || {};
  const knowledgeSnapshot = activeCase?.knowledge_snapshot || {};
  const outputSnapshot = activeCase?.output_snapshot || {};
  const assetVersions = activeCase?.asset_versions || {};
  const rootCauses = normalizeList(outputSnapshot.root_causes);
  const solutions = normalizeList(outputSnapshot.solutions);
  const reasoningSteps = normalizeList(traceSnapshot.reasoning_steps);
  const retrievedKnowledge = normalizeList(knowledgeSnapshot.retrieved_knowledge);

  const detailTabs = useMemo(() => {
    if (!activeCase) return [];

    return [
      {
        key: 'summary',
        label: '概览',
        children: (
          <div className="evolution-detail-section">
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="案例ID">{activeCase.id}</Descriptions.Item>
              <Descriptions.Item label="诊断记录ID">{activeCase.record_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="诊断任务ID">{activeCase.diagnosis_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="异常类型">{activeCase.anomaly_type || '-'}</Descriptions.Item>
              <Descriptions.Item label="案例标签">{renderLabelTag(activeCase.label)}</Descriptions.Item>
              <Descriptions.Item label="状态">{renderStatusTag(activeCase.status)}</Descriptions.Item>
              <Descriptions.Item label="评分">
                <Progress
                  percent={scoreToPercent(activeCase.outcome_score)}
                  size="small"
                  status={activeCase.label === 'negative_case' ? 'exception' : 'normal'}
                />
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDate(activeCase.create_time)}</Descriptions.Item>
            </Descriptions>
            <div className="evolution-fingerprint">
              <Text type="secondary">Fingerprint</Text>
              <Text copyable>{activeCase.case_fingerprint || '-'}</Text>
            </div>
          </div>
        ),
      },
      {
        key: 'trace',
        label: '推理轨迹',
        children: reasoningSteps.length ? (
          <Timeline
            className="evolution-timeline"
            items={reasoningSteps.map((step, index) => ({
              color: index === reasoningSteps.length - 1 ? 'green' : 'blue',
              children: (
                <div className="evolution-step">
                  <Text strong>Step {index + 1}</Text>
                  <Paragraph>
                    {typeof step === 'string'
                      ? step
                      : step.thought || step.action || step.observation || step.description || formatJson(step)}
                  </Paragraph>
                </div>
              ),
            }))}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无推理轨迹" />
        ),
      },
      {
        key: 'knowledge',
        label: '知识命中',
        children: (
          <div className="evolution-detail-section">
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="命中片段数">
                {knowledgeSnapshot.knowledge_chunks_used ?? retrievedKnowledge.length}
              </Descriptions.Item>
              <Descriptions.Item label="资产版本">
                {assetVersions.knowledge?.sha256 ? assetVersions.knowledge.sha256.slice(0, 12) : '-'}
              </Descriptions.Item>
            </Descriptions>
            {retrievedKnowledge.length ? (
              <div className="evolution-list">
                {retrievedKnowledge.map((item, index) => (
                  <div className="evolution-list-item" key={`${index}-${typeof item === 'string' ? item : item.id || item.title || index}`}>
                    <Text strong>{typeof item === 'string' ? `知识片段 ${index + 1}` : item.title || item.source || `知识片段 ${index + 1}`}</Text>
                    <Paragraph>
                      {typeof item === 'string' ? item : item.content || item.text || item.description || formatJson(item)}
                    </Paragraph>
                  </div>
                ))}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无知识命中" />
            )}
          </div>
        ),
      },
      {
        key: 'output',
        label: '诊断输出',
        children: (
          <div className="evolution-output-grid">
            <section>
              <Title level={5}>根因</Title>
              {rootCauses.length ? rootCauses.map((cause, index) => (
                <div className="evolution-list-item" key={`${index}-${typeof cause === 'string' ? cause : cause.type || index}`}>
                  <Space wrap>
                    <Tag color="volcano">{typeof cause === 'string' ? `Root ${index + 1}` : cause.type || `Root ${index + 1}`}</Tag>
                    {cause?.confidence !== undefined && <Tag color="gold">置信度 {scoreToPercent(cause.confidence)}%</Tag>}
                  </Space>
                  <Paragraph>{typeof cause === 'string' ? cause : cause.description || cause.reason || formatJson(cause)}</Paragraph>
                </div>
              )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无根因" />}
            </section>
            <section>
              <Title level={5}>解决方案</Title>
              {solutions.length ? solutions.map((solution, index) => (
                <div className="evolution-list-item" key={`${index}-${typeof solution === 'string' ? solution : solution.title || index}`}>
                  <Text strong>{typeof solution === 'string' ? `方案 ${index + 1}` : solution.title || solution.action || `方案 ${index + 1}`}</Text>
                  <Paragraph>{typeof solution === 'string' ? solution : solution.description || solution.detail || formatJson(solution)}</Paragraph>
                </div>
              )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无解决方案" />}
            </section>
          </div>
        ),
      },
      {
        key: 'feedback',
        label: '反馈记录',
        children: feedbackItems.length ? (
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={feedbackItems}
            columns={[
              { title: 'ID', dataIndex: 'id', width: 72 },
              { title: '评分', dataIndex: 'score', width: 90, render: (value) => value ?? '-' },
              { title: '采纳', dataIndex: 'accepted', width: 90, render: (value) => value === undefined || value === null ? '-' : value ? '是' : '否' },
              { title: '复发', dataIndex: 'recurrence', width: 90, render: (value) => value === undefined || value === null ? '-' : value ? '是' : '否' },
              { title: '原因', dataIndex: 'reason', ellipsis: true },
              { title: '时间', dataIndex: 'create_time', width: 160, render: formatDate },
            ]}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无反馈记录" />
        ),
      },
      {
        key: 'raw',
        label: '原始快照',
        children: (
          <Tabs
            size="small"
            items={[
              { key: 'input', label: '输入', children: <JsonBlock value={activeCase.input_snapshot} /> },
              { key: 'trace-json', label: '轨迹', children: <JsonBlock value={traceSnapshot} /> },
              { key: 'knowledge-json', label: '知识', children: <JsonBlock value={knowledgeSnapshot} /> },
              { key: 'output-json', label: '输出', children: <JsonBlock value={outputSnapshot} /> },
              { key: 'asset-json', label: '资产', children: <JsonBlock value={assetVersions} /> },
            ]}
          />
        ),
      },
    ];
  }, [activeCase, assetVersions, feedbackItems, knowledgeSnapshot, outputSnapshot, reasoningSteps, retrievedKnowledge, rootCauses, solutions, traceSnapshot]);

  const columns = [
    {
      title: '案例ID',
      dataIndex: 'id',
      width: 96,
      fixed: 'left',
      render: (value) => <Text strong>#{value}</Text>,
    },
    {
      title: '诊断记录',
      dataIndex: 'record_id',
      width: 110,
      render: (value) => value || '-',
    },
    {
      title: '异常类型',
      dataIndex: 'anomaly_type',
      ellipsis: true,
      render: (value) => value || '-',
    },
    {
      title: '标签',
      dataIndex: 'label',
      width: 120,
      render: renderLabelTag,
    },
    {
      title: '评分',
      dataIndex: 'outcome_score',
      width: 160,
      render: (value, record) => (
        <Progress
          percent={scoreToPercent(value)}
          size="small"
          status={record.label === 'negative_case' ? 'exception' : 'normal'}
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: renderStatusTag,
    },
    {
      title: '采集时间',
      dataIndex: 'create_time',
      width: 170,
      render: formatDate,
    },
    {
      title: '操作',
      width: 150,
      fixed: 'right',
      render: (_, record) => (
        <Space size={6}>
          <Tooltip title="查看详情">
            <Button type="text" icon={<EyeOutlined />} onClick={() => openDetail(record)} />
          </Tooltip>
          <Tooltip title="写入反馈">
            <Button type="text" icon={<CommentOutlined />} onClick={() => openFeedback(record)} />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div className="evolution-page">
      <div className="evolution-header">
        <div>
          <Space align="center" wrap>
            <BranchesOutlined className="evolution-title-icon" />
            <Title level={2}>自进化中心</Title>
            <Tag color="cyan">V0.1 旁路闭环</Tag>
          </Space>
          <Text type="secondary">诊断案例采集、反馈关联、结果评分与样本标签</Text>
        </div>
        <Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={handleRefresh}>
          刷新
        </Button>
      </div>

      <Row gutter={[16, 16]} className="evolution-metrics">
        {metricCards.map((item) => (
          <Col xs={24} sm={12} xl={6} key={item.key}>
            <Card className="evolution-metric-card">
              <div className="evolution-metric-icon">{item.icon}</div>
              <Statistic title={item.title} value={item.value} suffix={item.suffix} />
            </Card>
          </Col>
        ))}
      </Row>

      <Card className="evolution-band">
        <div className="evolution-band-grid">
          <div>
            <Text type="secondary">标签分布</Text>
            <Space wrap className="evolution-tags-row">
              <Tag color="success">正样本 {labelCounts.positive_case || 0}</Tag>
              <Tag color="error">负样本 {labelCounts.negative_case || 0}</Tag>
              <Tag color="warning">待确认 {labelCounts.uncertain_case || 0}</Tag>
            </Space>
          </div>
          <div>
            <Text type="secondary">状态分布</Text>
            <Space wrap className="evolution-tags-row">
              <Tag color="processing">已采集 {statusCounts.captured || 0}</Tag>
              <Tag color="success">已评分 {statusCounts.evaluated || 0}</Tag>
            </Space>
          </div>
          <div className="evolution-score-ring">
            <Progress type="circle" percent={avgScorePercent} size={78} />
            <Text type="secondary">平均结果评分</Text>
          </div>
        </div>
      </Card>

      <Card
        className="evolution-table-card"
        title={(
          <Space>
            <FileSearchOutlined />
            <span>案例池</span>
          </Space>
        )}
        extra={(
          <Space wrap>
            <Select
              allowClear
              placeholder="标签"
              value={filters.label}
              style={{ width: 132 }}
              onChange={(value) => handleFilterChange('label', value)}
              options={[
                { value: 'positive_case', label: '正样本' },
                { value: 'negative_case', label: '负样本' },
                { value: 'uncertain_case', label: '待确认' },
              ]}
            />
            <Select
              allowClear
              placeholder="状态"
              value={filters.status}
              style={{ width: 132 }}
              onChange={(value) => handleFilterChange('status', value)}
              options={[
                { value: 'captured', label: '已采集' },
                { value: 'evaluated', label: '已评分' },
              ]}
            />
            <Input
              allowClear
              placeholder="异常类型"
              value={filters.anomaly_type}
              style={{ width: 180 }}
              onChange={(event) => handleFilterChange('anomaly_type', event.target.value)}
            />
          </Space>
        )}
      >
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={cases}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无自进化案例" /> }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          scroll={{ x: 980 }}
          onChange={handleTableChange}
        />
      </Card>

      <Drawer
        title={activeCase ? `自进化案例 #${activeCase.id}` : '自进化案例'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={920}
        rootClassName="evolution-drawer"
        extra={activeCase && (
          <Button icon={<CommentOutlined />} onClick={() => openFeedback(activeCase)}>
            写反馈
          </Button>
        )}
      >
        <Spin spinning={detailLoading}>
          {activeCase ? <Tabs items={detailTabs} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </Spin>
      </Drawer>

      <Modal
        title={feedbackTarget ? `写入反馈 #${feedbackTarget.id}` : '写入反馈'}
        open={feedbackOpen}
        onOk={submitFeedback}
        confirmLoading={feedbackSubmitting}
        onCancel={() => setFeedbackOpen(false)}
        okText="提交"
        cancelText="取消"
        rootClassName="evolution-modal"
        destroyOnClose
      >
        <Form form={feedbackForm} layout="vertical">
          <Form.Item
            label="用户评分"
            name="score"
            rules={[{ required: true, message: '请输入评分' }]}
          >
            <InputNumber min={0} max={100} addonAfter="分" style={{ width: '100%' }} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="建议采纳" name="accepted" valuePropName="checked">
                <Switch checkedChildren="是" unCheckedChildren="否" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="指标恢复" name="recovered" valuePropName="checked">
                <Switch checkedChildren="是" unCheckedChildren="否" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="是否复发" name="recurrence" valuePropName="checked">
                <Switch checkedChildren="是" unCheckedChildren="否" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="反馈原因" name="reason">
            <TextArea rows={4} placeholder="例如：根因命中，执行建议后指标恢复" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Evolution;
