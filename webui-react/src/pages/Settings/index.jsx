/**
 * @fileoverview Settings 页面 - 系统配置管理
 * @author [Your Name]
 * @date 2024/01/01
 * @description 提供 LLM、数据库、通知、安全等系统配置的管理界面
 *              支持配置的加载、保存和连接测试
 */
import React, { useState, useEffect } from 'react';
import {
  Row, Col, Card, Form, Input, Select, Switch, Button, Divider,
  message, Tabs, Typography, Spin, Space, Alert
} from 'antd';
import {
  SettingOutlined, ApiOutlined, DatabaseOutlined,
  SafetyOutlined, BellOutlined, CheckCircleOutlined, CloseCircleOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Option } = Select;
const { Title, Text } = Typography;

const API_BASE = 'http://localhost:7861';

/**
 * @function Settings
 * @brief 系统设置页面组件
 * @returns {JSX.Element} 设置页面 JSX 元素
 */
const Settings = () => {
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [llmForm] = Form.useForm();
  const [dbForm] = Form.useForm();
  const [notifyForm] = Form.useForm();
  const [securityForm] = Form.useForm();
  const [testResult, setTestResult] = useState({ llm: null, db: null });

  useEffect(() => {
    fetchAllSettings();
  }, []);

  /**
   * @function fetchAllSettings
   * @brief 获取所有配置数据
   */
  const fetchAllSettings = async () => {
    setInitialLoading(true);
    try {
      const response = await axios.get(`${API_BASE}/api/settings/all`);
      if (response.data.code === 200) {
        const settings = response.data.data;
        if (settings.llm) llmForm.setFieldsValue(settings.llm);
        if (settings.database) dbForm.setFieldsValue(settings.database);
        if (settings.notification) notifyForm.setFieldsValue(settings.notification);
        if (settings.security) securityForm.setFieldsValue(settings.security);
      }
    } catch (error) {
      message.warning('无法加载配置，使用默认值');
    } finally {
      setInitialLoading(false);
    }
  };

  /**
   * @function onSaveLLMSettings
   * @brief 保存 LLM 配置
   * @param {Object} values - 表单值
   */
  const onSaveLLMSettings = async (values) => {
    setLoading(true);
    try {
      const response = await axios.post(`${API_BASE}/api/settings/llm`, values);
      if (response.data.code === 200) {
        message.success('LLM 配置保存成功');
      } else {
        message.error(response.data.msg || '保存失败');
      }
    } catch (error) {
      message.error('保存失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * @function onTestLLMConnection
   * @brief 测试 LLM 连接
   */
  const onTestLLMConnection = async () => {
    const values = llmForm.getFieldsValue();
    if (!values.api_key) {
      message.warning('请先填写 API Key');
      return;
    }
    setLoading(true);
    setTestResult({ ...testResult, llm: 'testing' });
    try {
      const response = await axios.post(`${API_BASE}/api/settings/llm/test`, values);
      if (response.data.code === 200) {
        setTestResult({ ...testResult, llm: 'success' });
        message.success(response.data.msg);
      } else {
        setTestResult({ ...testResult, llm: 'failed' });
        message.error(response.data.msg);
      }
    } catch (error) {
      setTestResult({ ...testResult, llm: 'failed' });
      message.error('连接测试失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * @function onSaveDBSettings
   * @brief 保存数据库配置
   * @param {Object} values - 表单值
   */
  const onSaveDBSettings = async (values) => {
    setLoading(true);
    try {
      const response = await axios.post(`${API_BASE}/api/settings/database`, values);
      if (response.data.code === 200) {
        message.success('数据库配置保存成功');
      } else {
        message.error(response.data.msg || '保存失败');
      }
    } catch (error) {
      message.error('保存失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * @function onTestDBConnection
   * @brief 测试数据库连接
   */
  const onTestDBConnection = async () => {
    const values = dbForm.getFieldsValue();
    setLoading(true);
    setTestResult({ ...testResult, db: 'testing' });
    try {
      const response = await axios.post(`${API_BASE}/api/settings/database/test`, values);
      if (response.data.code === 200) {
        setTestResult({ ...testResult, db: 'success' });
        message.success(response.data.msg);
      } else {
        setTestResult({ ...testResult, db: 'failed' });
        message.error(response.data.msg);
      }
    } catch (error) {
      setTestResult({ ...testResult, db: 'failed' });
      message.error('连接测试失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * @function onSaveNotifySettings
   * @brief 保存通知配置
   */
  const onSaveNotifySettings = async () => {
    setLoading(true);
    try {
      const values = notifyForm.getFieldsValue();
      const response = await axios.post(`${API_BASE}/api/settings/notification`, values);
      if (response.data.code === 200) {
        message.success('通知配置保存成功');
      } else {
        message.error(response.data.msg || '保存失败');
      }
    } catch (error) {
      message.error('保存失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * @function onSaveSecuritySettings
   * @brief 保存安全配置
   */
  const onSaveSecuritySettings = async () => {
    setLoading(true);
    try {
      const values = securityForm.getFieldsValue();
      const response = await axios.post(`${API_BASE}/api/settings/security`, values);
      if (response.data.code === 200) {
        message.success('安全配置保存成功');
      } else {
        message.error(response.data.msg || '保存失败');
      }
    } catch (error) {
      message.error('保存失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  if (initialLoading) {
    return (
      <div style={{ padding: '24px', textAlign: 'center' }}>
        <Spin size="large" />
        <p style={{ marginTop: '16px' }}>加载配置中...</p>
      </div>
    );
  }

  return (
    <div className="settings-page" style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', marginBottom: '8px' }}>
          <SettingOutlined /> 系统设置
        </h1>
        <p style={{ color: '#8c8c8c' }}>配置 D-Bot 系统参数</p>
      </div>

      <Tabs defaultActiveKey="llm" tabPosition="left">
        <Tabs.TabPane
          tab={<span><ApiOutlined /> LLM 配置</span>}
          key="llm"
        >
          <Card bordered={false}>
            <Alert
              message="配置说明"
              description="配置大语言模型 API 参数，用于数据库诊断推理。推荐使用 DeepSeek 模型。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />
            <Form
              form={llmForm}
              layout="vertical"
              onFinish={onSaveLLMSettings}
            >
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item label="模型类型" name="model_type">
                    <Select>
                      <Option value="deepseek">DeepSeek (推荐)</Option>
                      <Option value="openai">OpenAI</Option>
                      <Option value="local">本地模型</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="模型名称" name="model_name">
                    <Select>
                      <Option value="deepseek-chat">DeepSeek-V3 (推荐)</Option>
                      <Option value="deepseek-reasoner">DeepSeek-R1 (推理增强)</Option>
                      <Option value="deepseek-coder">DeepSeek-Coder</Option>
                      <Option value="gpt-4">GPT-4</Option>
                      <Option value="gpt-3.5-turbo">GPT-3.5-Turbo</Option>
                      <Option value="local-llm">Local-LLM (本地)</Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item label="API Key" name="api_key">
                <Input.Password placeholder="sk-..." />
              </Form.Item>

              <Form.Item label="API Base URL" name="api_base">
                <Input placeholder="https://api.deepseek.com" />
              </Form.Item>

              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item label="Temperature" name="temperature">
                    <Select>
                      <Option value={0}>0 (最精确)</Option>
                      <Option value={0.3}>0.3</Option>
                      <Option value={0.7}>0.7 (默认)</Option>
                      <Option value={1.0}>1.0 (最随机)</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Max Tokens" name="max_tokens">
                    <Select>
                      <Option value={2048}>2048</Option>
                      <Option value={4096}>4096</Option>
                      <Option value={8192}>8192</Option>
                      <Option value={16384}>16384</Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>

              <Space>
                <Button type="primary" htmlType="submit" loading={loading}>
                  保存配置
                </Button>
                <Button onClick={onTestLLMConnection} loading={loading}>
                  {testResult.llm === 'success' && <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 4 }} />}
                  {testResult.llm === 'failed' && <CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 4 }} />}
                  测试连接
                </Button>
              </Space>
            </Form>
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane
          tab={<span><DatabaseOutlined /> 数据库配置</span>}
          key="database"
        >
          <Card bordered={false}>
            <Alert
              message="配置说明"
              description="配置待诊断的数据库连接参数。支持 PostgreSQL、MySQL、SQLite 三种数据库类型。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />
            <Form
              form={dbForm}
              layout="vertical"
              onFinish={onSaveDBSettings}
            >
              <Row gutter={24}>
                <Col span={8}>
                  <Form.Item label="数据库类型" name="db_type">
                    <Select>
                      <Option value="postgresql">PostgreSQL</Option>
                      <Option value="mysql">MySQL</Option>
                      <Option value="sqlite">SQLite</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="主机地址" name="host">
                    <Input placeholder="localhost" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="端口" name="port">
                    <Input type="number" placeholder="5432" />
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={24}>
                <Col span={8}>
                  <Form.Item label="用户名" name="username">
                    <Input placeholder="postgres" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="密码" name="password">
                    <Input.Password />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="数据库名" name="database">
                    <Input placeholder="postgres" />
                  </Form.Item>
                </Col>
              </Row>

              <Space>
                <Button type="primary" htmlType="submit" loading={loading}>
                  保存配置
                </Button>
                <Button onClick={onTestDBConnection} loading={loading}>
                  {testResult.db === 'success' && <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 4 }} />}
                  {testResult.db === 'failed' && <CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 4 }} />}
                  测试连接
                </Button>
              </Space>
            </Form>
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane
          tab={<span><BellOutlined /> 通知设置</span>}
          key="notification"
        >
          <Card bordered={false}>
            <Alert
              message="配置说明"
              description="配置告警通知方式和阈值。当系统指标超过阈值时，将触发告警通知。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />
            <Form form={notifyForm} layout="vertical">
              <Row gutter={24}>
                <Col span={8}>
                  <Form.Item label="启用邮件通知" name="email_enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="启用钉钉通知" name="dingtalk_enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="启用企业微信通知" name="wechat_enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>
              <Divider />
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item label="告警阈值 - CPU使用率" name="cpu_threshold">
                    <Select style={{ width: 200 }}>
                      <Option value={70}>70%</Option>
                      <Option value={80}>80%</Option>
                      <Option value={90}>90%</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="告警阈值 - 内存使用率" name="memory_threshold">
                    <Select style={{ width: 200 }}>
                      <Option value={75}>75%</Option>
                      <Option value={85}>85%</Option>
                      <Option value={95}>95%</Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" onClick={onSaveNotifySettings} loading={loading}>
                保存配置
              </Button>
            </Form>
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane
          tab={<span><SafetyOutlined /> 安全设置</span>}
          key="security"
        >
          <Card bordered={false}>
            <Alert
              message="配置说明"
              description="配置系统安全相关参数。修改这些参数可能会影响系统安全性，请谨慎操作。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />
            <Form form={securityForm} layout="vertical">
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item label="启用 API 认证" name="api_auth_enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="允许跨域请求 (CORS)" name="cors_enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="日志级别" name="log_level">
                <Select style={{ width: 200 }}>
                  <Option value="DEBUG">DEBUG</Option>
                  <Option value="INFO">INFO</Option>
                  <Option value="WARNING">WARNING</Option>
                  <Option value="ERROR">ERROR</Option>
                </Select>
              </Form.Item>
              <Button type="primary" onClick={onSaveSecuritySettings} loading={loading}>
                保存配置
              </Button>
            </Form>
          </Card>
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default Settings;
