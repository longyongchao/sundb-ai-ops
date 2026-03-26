/**
 * Profile 页面 - 个人中心
 * 用户信息管理和系统使用统计
 */
import React, { useState, useEffect } from 'react';
import {
  Row, Col, Card, Avatar, Descriptions, Tag, Progress, Statistic,
  Button, Upload, message, Tabs, Timeline, Typography, Divider, Modal, Form, Input, Spin
} from 'antd';
import {
  UserOutlined,
  ClockCircleOutlined, CheckCircleOutlined, FileTextOutlined,
  BugOutlined, EditOutlined, DashboardOutlined, BookOutlined, 
  MonitorOutlined, BarChartOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;

const Profile = () => {
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [userInfo, setUserInfo] = useState({
    name: localStorage.getItem('username') || 'admin',
    role: localStorage.getItem('role') || 'admin',
    lastLogin: '-',
  });

  const [usageStats, setUsageStats] = useState({
    totalDiagnoses: 0,
    successRate: 0,
    savedReports: 0,
  });

  const [recentActivities, setRecentActivities] = useState([]);

  useEffect(() => {
    fetchUserStats();
    const now = new Date();
    const beijingTime = now.toLocaleString('zh-CN', { 
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    }).replace(/\//g, '-');
    setUserInfo(prev => ({ ...prev, lastLogin: beijingTime }));
    
    const savedActivities = localStorage.getItem('userActivities');
    if (savedActivities) {
      setRecentActivities(JSON.parse(savedActivities));
    }
  }, []);

  const fetchUserStats = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/report/histories');
      if (response.data?.code === 200 && response.data?.data) {
        const reports = response.data.data;
        const totalDiagnoses = reports.length;
        const savedReports = reports.filter(r => r.file_name).length;
        const successCount = reports.filter(r => r.success !== false).length;
        const successRate = totalDiagnoses > 0 ? Math.round((successCount / totalDiagnoses) * 100) : 0;
        
        setUsageStats({
          totalDiagnoses,
          successRate,
          savedReports,
        });
      }
    } catch (error) {
      console.log('获取统计数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAvatarChange = (info) => {
    if (info.file.status === 'done') {
      message.success('头像更新成功');
    } else if (info.file.status === 'error') {
      message.error('头像上传失败');
    }
  };

  const handleEditClick = () => {
    form.setFieldsValue(userInfo);
    setEditModalVisible(true);
  };

  const handleEditSave = () => {
    form.validateFields().then(values => {
      setUserInfo(prev => ({ ...prev, ...values }));
      setEditModalVisible(false);
      message.success('资料更新成功');
    });
  };

  const getActivityIcon = (type) => {
    switch (type) {
      case 'dashboard':
        return <DashboardOutlined style={{ color: '#00d4ff' }} />;
      case 'diagnose':
        return <BugOutlined style={{ color: '#52c41a' }} />;
      case 'knowledge':
        return <BookOutlined style={{ color: '#7b2cbf' }} />;
      case 'monitor':
        return <MonitorOutlined style={{ color: '#faad14' }} />;
      case 'evaluation':
        return <BarChartOutlined style={{ color: '#eb2f96' }} />;
      default:
        return <ClockCircleOutlined style={{ color: '#00d4ff' }} />;
    }
  };

  return (
    <div className="profile-page" style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px' }}>
        <Title level={3} style={{ color: '#fff', margin: 0 }}>
          <UserOutlined /> 个人中心
        </Title>
        <Text style={{ color: 'rgba(255,255,255,0.65)' }}>
          管理您的个人信息
        </Text>
      </div>

      <Spin spinning={loading}>
        <Row gutter={[24, 24]}>
          <Col xs={24} sm={24} md={10} lg={8}>
            <Card 
              bordered={false} 
              style={{ background: '#1e1e2e', textAlign: 'center' }}
            >
              <Upload
                showUploadList={false}
                onChange={handleAvatarChange}
                accept="image/*"
              >
                <Avatar 
                  size={100} 
                  icon={<UserOutlined />} 
                  style={{ 
                    background: 'linear-gradient(135deg, #00d4ff 0%, #7b2cbf 100%)',
                    cursor: 'pointer',
                    marginBottom: 16,
                  }}
                />
              </Upload>
              <Title level={4} style={{ color: '#fff', margin: '8px 0' }}>
                {userInfo.name}
              </Title>
              <Tag style={{ marginBottom: 16, background: 'rgba(0, 212, 255, 0.15)', color: '#00d4ff', border: '1px solid rgba(0, 212, 255, 0.3)' }}>
                {userInfo.role}
              </Tag>
              <br />
              <Button 
                type="primary" 
                icon={<EditOutlined />}
                onClick={handleEditClick}
                style={{ 
                  background: 'rgba(0, 212, 255, 0.15)',
                  border: '1px solid rgba(0, 212, 255, 0.3)',
                  color: '#00d4ff',
                }}
              >
                编辑资料
              </Button>

              <Divider style={{ borderColor: 'rgba(255,255,255,0.1)' }} />

              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    title={<span style={{ color: 'rgba(255,255,255,0.65)' }}>诊断次数</span>}
                    value={usageStats.totalDiagnoses}
                    prefix={<BugOutlined />}
                    valueStyle={{ color: '#00d4ff', fontSize: 24 }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    title={<span style={{ color: 'rgba(255,255,255,0.65)' }}>成功率</span>}
                    value={usageStats.successRate}
                    suffix="%"
                    prefix={<CheckCircleOutlined />}
                    valueStyle={{ color: '#52c41a', fontSize: 24 }}
                  />
                </Col>
              </Row>
            </Card>
          </Col>

          <Col xs={24} sm={24} md={14} lg={16}>
            <Card bordered={false} style={{ background: '#1e1e2e' }}>
              <Tabs defaultActiveKey="info" tabBarStyle={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                <Tabs.TabPane 
                  tab={<span style={{ color: 'rgba(255,255,255,0.85)' }}>基本信息</span>} 
                  key="info"
                >
                  <Descriptions 
                    column={1}
                    labelStyle={{ color: 'rgba(255,255,255,0.65)', background: 'rgba(0,0,0,0.2)', width: 120 }}
                    contentStyle={{ color: '#fff' }}
                  >
                    <Descriptions.Item label={<><UserOutlined /> 用户名</>}>
                      {userInfo.name}
                    </Descriptions.Item>
                    <Descriptions.Item label={<><ClockCircleOutlined /> 最后登录</>}>
                      {userInfo.lastLogin}
                    </Descriptions.Item>
                  </Descriptions>
                </Tabs.TabPane>

                <Tabs.TabPane 
                  tab={<span style={{ color: 'rgba(255,255,255,0.85)' }}>使用统计</span>} 
                  key="stats"
                >
                  <Row gutter={[24, 24]}>
                    <Col span={12}>
                      <Card 
                        size="small" 
                        style={{ background: 'rgba(0,0,0,0.2)', textAlign: 'center' }}
                      >
                        <Statistic
                          title={<span style={{ color: 'rgba(255,255,255,0.65)' }}>总诊断次数</span>}
                          value={usageStats.totalDiagnoses}
                          prefix={<BugOutlined style={{ color: '#00d4ff' }} />}
                          valueStyle={{ color: '#fff' }}
                        />
                        <Progress 
                          percent={Math.min(usageStats.totalDiagnoses * 5, 100)} 
                          showInfo={false}
                          strokeColor="#00d4ff"
                          trailColor="rgba(255,255,255,0.1)"
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card 
                        size="small" 
                        style={{ background: 'rgba(0,0,0,0.2)', textAlign: 'center' }}
                      >
                        <Statistic
                          title={<span style={{ color: 'rgba(255,255,255,0.65)' }}>保存报告数</span>}
                          value={usageStats.savedReports}
                          prefix={<FileTextOutlined style={{ color: '#7b2cbf' }} />}
                          valueStyle={{ color: '#fff' }}
                        />
                        <Progress 
                          percent={Math.min(usageStats.savedReports * 5, 100)} 
                          showInfo={false}
                          strokeColor="#7b2cbf"
                          trailColor="rgba(255,255,255,0.1)"
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card 
                        size="small" 
                        style={{ background: 'rgba(0,0,0,0.2)', textAlign: 'center' }}
                      >
                        <Statistic
                          title={<span style={{ color: 'rgba(255,255,255,0.65)' }}>诊断成功率</span>}
                          value={usageStats.successRate}
                          suffix="%"
                          prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                          valueStyle={{ color: '#fff' }}
                        />
                        <Progress 
                          percent={usageStats.successRate} 
                          showInfo={false}
                          strokeColor="#52c41a"
                          trailColor="rgba(255,255,255,0.1)"
                        />
                      </Card>
                    </Col>
                  </Row>
                </Tabs.TabPane>

                <Tabs.TabPane 
                  tab={<span style={{ color: 'rgba(255,255,255,0.85)' }}>最近活动</span>} 
                  key="activity"
                >
                  {recentActivities.length > 0 ? (
                    <Timeline
                      items={recentActivities.slice(0, 10).map(item => ({
                        color: '#00d4ff',
                        dot: getActivityIcon(item.type),
                        children: (
                          <div>
                            <Text style={{ color: '#fff' }}>{item.action}</Text>
                            <br />
                            <Text style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>
                              {item.time}
                            </Text>
                          </div>
                        ),
                      }))}
                    />
                  ) : (
                    <div style={{ textAlign: 'center', padding: '40px 0', color: 'rgba(255,255,255,0.45)' }}>
                      暂无活动记录
                    </div>
                  )}
                </Tabs.TabPane>
              </Tabs>
            </Card>
          </Col>
        </Row>
      </Spin>

      <Modal
        title="编辑资料"
        open={editModalVisible}
        onOk={handleEditSave}
        onCancel={() => setEditModalVisible(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="用户名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Profile;
