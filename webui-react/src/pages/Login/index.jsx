/**
 * Login 页面 - 用户登录和注册
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, message, Tabs } from 'antd';
import { UserOutlined, LockOutlined, DatabaseOutlined } from '@ant-design/icons';
import axios from 'axios';
import './index.scss';

const Login = () => {
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('login');
  const navigate = useNavigate();

  const onFinish = async (values) => {
    setLoading(true);
    try {
      const response = await axios.post('/api/auth/login', {
        username: values.username,
        password: values.password,
      });
      
      if (response.data?.code === 200) {
        const { token, username, role } = response.data.data;
        localStorage.setItem('token', token);
        localStorage.setItem('username', username);
        localStorage.setItem('role', role);
        message.success('登录成功！');
        navigate('/dashboard');
      } else {
        message.error(response.data.msg || '登录失败');
      }
    } catch (error) {
      message.error(error.response?.data?.msg || '登录失败，请检查网络');
    } finally {
      setLoading(false);
    }
  };

  const onRegister = async (values) => {
    setLoading(true);
    try {
      const response = await axios.post('/api/auth/register', {
        username: values.regUsername,
        password: values.regPassword,
      });
      
      if (response.data?.code === 200) {
        message.success('注册成功！请登录');
        setActiveTab('login');
      } else {
        message.error(response.data.msg || '注册失败');
      }
    } catch (error) {
      message.error(error.response?.data?.msg || '注册失败，请检查网络');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-background">
        <div className="particles">
          {[...Array(50)].map((_, i) => (
            <div key={i} className="particle" style={{
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              animationDelay: `${Math.random() * 5}s`,
              animationDuration: `${3 + Math.random() * 4}s`
            }} />
          ))}
        </div>
      </div>
      
      <Card className="login-card">
        <div className="login-header">
          <div className="logo">
            <DatabaseOutlined className="logo-icon" />
          </div>
          <h1 className="title">数据库智能运维系统</h1>
          <p className="subtitle">Database Intelligent Operations System</p>
        </div>

        <Tabs activeKey={activeTab} onChange={setActiveTab} centered>
          <Tabs.TabPane tab="登录" key="login">
            <Form name="login" onFinish={onFinish} autoComplete="off" size="large">
              <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input prefix={<UserOutlined />} placeholder="用户名" />
              </Form.Item>
              <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password prefix={<LockOutlined />} placeholder="密码" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading} block>
                  登录
                </Button>
              </Form.Item>
            </Form>
          </Tabs.TabPane>
          <Tabs.TabPane tab="注册" key="register">
            <Form name="register" onFinish={onRegister} autoComplete="off" size="large">
              <Form.Item
                name="regUsername"
                rules={[
                  { required: true, message: '请输入用户名' },
                  { min: 3, message: '用户名至少3个字符' },
                  { pattern: /^[a-zA-Z0-9]+$/, message: '只能包含英文字母和数字' },
                ]}
              >
                <Input prefix={<UserOutlined />} placeholder="用户名 (至少3位，英文+数字)" />
              </Form.Item>
              <Form.Item
                name="regPassword"
                rules={[
                  { required: true, message: '请输入密码' },
                  { min: 5, message: '密码至少5个字符' },
                  { max: 10, message: '密码最多10个字符' },
                  { pattern: /^[a-zA-Z0-9]+$/, message: '只能包含英文字母和数字' },
                ]}
              >
                <Input.Password prefix={<LockOutlined />} placeholder="密码 (5-10位，英文+数字)" />
              </Form.Item>
              <Form.Item
                name="confirmPassword"
                dependencies={['regPassword']}
                rules={[
                  { required: true, message: '请确认密码' },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('regPassword') === value) {
                        return Promise.resolve();
                      }
                      return Promise.reject(new Error('两次输入的密码不一致'));
                    },
                  }),
                ]}
              >
                <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading} block>
                  注册
                </Button>
              </Form.Item>
            </Form>
          </Tabs.TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default Login;