/**
 * TestCaseSelector - 测试用例库选择组件
 * 
 * 功能：
 * 1. 按场景分类展示测试用例
 * 2. 查看用例详情和预期结果
 * 3. 一键选择并填充诊断配置
 */
import React, { useState, useEffect } from 'react';
import {
  Modal, Card, Collapse, Tag, Button, Descriptions, Spin, Empty,
  List, Typography, Badge, Tooltip, Space, Divider, Alert
} from 'antd';
import {
  FolderOutlined, FileTextOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, ThunderboltOutlined,
  ClockCircleOutlined, BulbOutlined, ToolOutlined
} from '@ant-design/icons';
import { testcaseAPI } from '@/utils/api';

const { Panel } = Collapse;
const { Text, Title, Paragraph } = Typography;

const DIFFICULTY_COLORS = {
  easy: 'green',
  medium: 'orange',
  hard: 'red'
};

const DIFFICULTY_LABELS = {
  easy: '简单',
  medium: '中等',
  hard: '困难'
};

const SEVERITY_COLORS = {
  info: 'blue',
  warning: 'orange',
  critical: 'red'
};

const SEVERITY_LABELS = {
  info: '信息',
  warning: '警告',
  critical: '严重'
};

const CATEGORY_NAMES = {
  '01_cpu_high': 'CPU 高负载',
  '02_slow_queries': '慢查询',
  '03_lock_contention': '锁竞争',
  '04_memory_high': '内存高使用',
  '05_io_bottleneck': 'IO 瓶颈',
  '06_mixed_scenarios': '混合场景',
  '07_edge_cases': '边界场景'
};

const TestCaseSelector = ({ visible, onClose, onSelect }) => {
  const [loading, setLoading] = useState(false);
  const [categories, setCategories] = useState([]);
  const [testcases, setTestcases] = useState([]);
  const [selectedCase, setSelectedCase] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [caseDetail, setCaseDetail] = useState(null);

  useEffect(() => {
    if (visible) {
      loadData();
    }
  }, [visible]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [categoriesData, testcasesData] = await Promise.all([
        testcaseAPI.getCategories(),
        testcaseAPI.getList()
      ]);
      setCategories(categoriesData || []);
      setTestcases(testcasesData || []);
    } catch (error) {
      console.error('加载测试用例失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadCaseDetail = async (caseId) => {
    setDetailLoading(true);
    try {
      const detail = await testcaseAPI.getDetail(caseId);
      setCaseDetail(detail);
    } catch (error) {
      console.error('加载用例详情失败:', error);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCaseClick = (caseId) => {
    setSelectedCase(caseId);
    loadCaseDetail(caseId);
  };

  const handleUseCase = () => {
    if (caseDetail && onSelect) {
      onSelect(caseDetail);
      handleClose();
    }
  };

  const handleClose = () => {
    setSelectedCase(null);
    setCaseDetail(null);
    onClose();
  };

  const getTestcasesByCategory = (categoryId) => {
    return testcases.filter(tc => tc.category === categoryId);
  };

  return (
    <Modal
      title={
        <span>
          <FolderOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
          从测试文件库选择
        </span>
      }
      open={visible}
      onCancel={handleClose}
      width={1100}
      footer={null}
      bodyStyle={{ padding: '16px', maxHeight: '70vh', overflow: 'auto' }}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <Spin size="large" />
          <p style={{ marginTop: '16px', color: '#8c8c8c' }}>加载测试用例...</p>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: '16px' }}>
          {/* 左侧：用例列表 */}
          <div style={{ flex: '0 0 400px', overflow: 'auto', maxHeight: '60vh' }}>
            <Alert
              message="共 19 个测试用例，覆盖 7 大场景"
              type="info"
              showIcon
              style={{ marginBottom: '16px' }}
            />
            
            <Collapse
              accordion
              defaultActiveKey={['01_cpu_high']}
              style={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
            >
              {categories.map(cat => (
                <Panel
                  header={
                    <span>
                      <Badge count={cat.case_count} style={{ marginRight: '8px' }} />
                      {CATEGORY_NAMES[cat.category_id] || cat.category_name}
                    </span>
                  }
                  key={cat.category_id}
                  style={{ backgroundColor: '#252525', marginBottom: '4px' }}
                >
                  <List
                    dataSource={getTestcasesByCategory(cat.category_id)}
                    renderItem={item => (
                      <List.Item
                        onClick={() => handleCaseClick(item.case_id)}
                        style={{
                          cursor: 'pointer',
                          backgroundColor: selectedCase === item.case_id ? '#1890ff20' : 'transparent',
                          padding: '8px 12px',
                          borderRadius: '4px',
                          border: selectedCase === item.case_id ? '1px solid #1890ff' : '1px solid transparent'
                        }}
                      >
                        <List.Item.Meta
                          avatar={<FileTextOutlined style={{ color: '#1890ff' }} />}
                          title={
                            <span style={{ color: '#e6e6e6' }}>
                              {item.case_name}
                              <Tag 
                                color={DIFFICULTY_COLORS[item.difficulty]} 
                                style={{ marginLeft: '8px', fontSize: '11px' }}
                              >
                                {DIFFICULTY_LABELS[item.difficulty]}
                              </Tag>
                            </span>
                          }
                          description={
                            <Text ellipsis style={{ color: '#8c8c8c', fontSize: '12px' }}>
                              {item.description}
                            </Text>
                          }
                        />
                      </List.Item>
                    )}
                  />
                </Panel>
              ))}
            </Collapse>
          </div>

          {/* 右侧：用例详情 */}
          <div style={{ flex: 1, overflow: 'auto', maxHeight: '60vh' }}>
            {detailLoading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <Spin size="large" />
              </div>
            ) : caseDetail ? (
              <div>
                <Card
                  title={
                    <span>
                      <FileTextOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
                      {caseDetail.case_name}
                    </span>
                  }
                  extra={
                    <Space>
                      <Tag color={DIFFICULTY_COLORS[caseDetail.difficulty]}>
                        {DIFFICULTY_LABELS[caseDetail.difficulty]}
                      </Tag>
                      <Tag color={SEVERITY_COLORS[caseDetail.severity]}>
                        {SEVERITY_LABELS[caseDetail.severity]}
                      </Tag>
                    </Space>
                  }
                  style={{ backgroundColor: '#1e1e1e', border: '1px solid #333', marginBottom: '16px' }}
                  headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333' }}
                >
                  <Paragraph style={{ color: '#b0b0b0' }}>
                    {caseDetail.case_description}
                  </Paragraph>
                  
                  <Descriptions column={2} size="small">
                    <Descriptions.Item label="告警类型">
                      <Tag color="blue">{caseDetail.alert_type}</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="场景分类">
                      {CATEGORY_NAMES[caseDetail.category] || caseDetail.category}
                    </Descriptions.Item>
                  </Descriptions>
                </Card>

                {/* 异常标签 */}
                <Card
                  title={<span><ExclamationCircleOutlined style={{ marginRight: '8px', color: '#faad14' }} />异常标签</span>}
                  size="small"
                  style={{ backgroundColor: '#1e1e1e', border: '1px solid #333', marginBottom: '16px' }}
                  headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333' }}
                >
                  <Space wrap>
                    {caseDetail.labels?.map((label, idx) => (
                      <Tag key={idx} color="orange">{label}</Tag>
                    ))}
                  </Space>
                </Card>

                {/* 预期根因 */}
                <Card
                  title={<span><BulbOutlined style={{ marginRight: '8px', color: '#52c41a' }} />预期根因</span>}
                  size="small"
                  style={{ backgroundColor: '#1e1e1e', border: '1px solid #333', marginBottom: '16px' }}
                  headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333' }}
                >
                  {caseDetail.expected_root_causes?.map((cause, idx) => (
                    <div key={idx} style={{ marginBottom: '8px' }}>
                      <Text strong style={{ color: '#52c41a' }}>
                        {idx + 1}. {cause.cause}
                      </Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: '12px' }}>
                        {cause.description}
                      </Text>
                      <Tag style={{ marginLeft: '8px' }} color="green">
                        置信度: {(cause.confidence * 100).toFixed(0)}%
                      </Tag>
                    </div>
                  ))}
                </Card>

                {/* 预期解决方案 */}
                <Card
                  title={<span><ToolOutlined style={{ marginRight: '8px', color: '#1890ff' }} />预期解决方案</span>}
                  size="small"
                  style={{ backgroundColor: '#1e1e1e', border: '1px solid #333', marginBottom: '16px' }}
                  headStyle={{ backgroundColor: '#252525', borderBottom: '1px solid #333' }}
                >
                  {caseDetail.expected_solutions?.map((solution, idx) => (
                    <div key={idx} style={{ marginBottom: '12px', padding: '8px', backgroundColor: '#252525', borderRadius: '4px' }}>
                      <Text strong style={{ color: '#1890ff' }}>
                        {idx + 1}. {solution.solution}
                      </Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: '12px' }}>
                        {solution.description}
                      </Text>
                      {solution.sql_example && (
                        <pre style={{ 
                          marginTop: '8px',
                          padding: '8px', 
                          backgroundColor: '#1a1a1a', 
                          borderRadius: '4px',
                          fontSize: '11px',
                          color: '#52c41a',
                          overflow: 'auto'
                        }}>
                          {solution.sql_example}
                        </pre>
                      )}
                    </div>
                  ))}
                </Card>

                {/* 使用按钮 */}
                <Button
                  type="primary"
                  size="large"
                  block
                  icon={<CheckCircleOutlined />}
                  onClick={handleUseCase}
                >
                  使用此测试用例
                </Button>
              </div>
            ) : (
              <Empty
                description="请从左侧选择一个测试用例"
                style={{ padding: '40px' }}
              />
            )}
          </div>
        </div>
      )}
    </Modal>
  );
};

export default TestCaseSelector;
