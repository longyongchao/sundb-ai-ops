/**
 * NotificationBell - 通知铃铛组件
 * 
 * 功能：
 * 1. 右上角通知铃铛图标
 * 2. 显示未读数量红点
 * 3. 点击展开通知列表
 */
import React, { useState, useEffect } from 'react';
import {
  Badge, Dropdown, List, Button, Empty, Spin, Tag, Typography, Space, Divider
} from 'antd';
import {
  BellOutlined, CheckOutlined, DeleteOutlined,
  FileTextOutlined, AlertOutlined, InfoCircleOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { notificationAPI } from '../../utils/api';

const { Text } = Typography;

const NOTIFICATION_TYPE_MAP = {
  'diagnosis': { text: '诊断', color: 'blue', icon: <FileTextOutlined /> },
  'alert': { text: '告警', color: 'orange', icon: <AlertOutlined /> },
  'system': { text: '系统', color: 'green', icon: <InfoCircleOutlined /> }
};

const SEVERITY_MAP = {
  'info': { color: 'blue' },
  'warning': { color: 'orange' },
  'critical': { color: 'red' }
};

const NotificationBell = () => {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchUnreadCount();
    fetchNotifications();
    
    const interval = setInterval(() => {
      fetchUnreadCount();
    }, 10000);
    
    return () => clearInterval(interval);
  }, []);

  const fetchUnreadCount = async () => {
    try {
      const res = await notificationAPI.getCount();
      setUnreadCount(res?.count || 0);
    } catch (error) {
      console.error('获取未读数量失败:', error);
    }
  };

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const res = await notificationAPI.getUnread(10);
      setNotifications(res || []);
    } catch (error) {
      console.error('获取通知列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleMarkRead = async (notificationId) => {
    try {
      await notificationAPI.markRead(notificationId);
      fetchNotifications();
      fetchUnreadCount();
    } catch (error) {
      console.error('标记已读失败:', error);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationAPI.markAllRead();
      fetchNotifications();
      fetchUnreadCount();
    } catch (error) {
      console.error('全部标记已读失败:', error);
    }
  };

  const handleNotificationClick = (notification) => {
    handleMarkRead(notification.id);
    if (notification.action_url) {
      navigate(notification.action_url);
    }
    setVisible(false);
  };

  const formatTime = (timeStr) => {
    if (!timeStr) return '';
    const date = new Date(timeStr);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);
    
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
    return date.toLocaleDateString('zh-CN');
  };

  const notificationList = (
    <div style={{
      width: 360,
      maxHeight: 480,
      backgroundColor: '#1e1e1e',
      borderRadius: 8,
      boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
    }}>
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid #333',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <Text strong style={{ color: '#e6e6e6' }}>
          <BellOutlined style={{ marginRight: 8 }} />
          通知中心
        </Text>
        {unreadCount > 0 && (
          <Button
            type="link"
            size="small"
            onClick={handleMarkAllRead}
            style={{ color: '#1890ff' }}
          >
            全部已读
          </Button>
        )}
      </div>
      
      <div style={{ maxHeight: 360, overflow: 'auto' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : notifications.length === 0 ? (
          <Empty
            description={<Text style={{ color: '#888' }}>暂无通知</Text>}
            style={{ padding: 40 }}
          />
        ) : (
          <List
            dataSource={notifications}
            renderItem={item => {
              const typeInfo = NOTIFICATION_TYPE_MAP[item.notification_type] || NOTIFICATION_TYPE_MAP['system'];
              const severityInfo = SEVERITY_MAP[item.severity] || SEVERITY_MAP['info'];
              
              return (
                <List.Item
                  style={{
                    padding: '12px 16px',
                    borderBottom: '1px solid #333',
                    cursor: 'pointer',
                    backgroundColor: item.is_read ? 'transparent' : '#1890ff10'
                  }}
                  onClick={() => handleNotificationClick(item)}
                >
                  <div style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Space>
                        <Tag color={typeInfo.color} style={{ margin: 0 }}>
                          {typeInfo.icon} {typeInfo.text}
                        </Tag>
                        <Tag color={severityInfo.color} style={{ margin: 0 }}>
                          {item.severity}
                        </Tag>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {formatTime(item.created_at)}
                      </Text>
                    </div>
                    <Text strong style={{ color: '#e6e6e6', display: 'block', marginBottom: 4 }}>
                      {item.title}
                    </Text>
                    {item.content && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {item.content}
                      </Text>
                    )}
                    {item.action_text && (
                      <Button
                        type="link"
                        size="small"
                        style={{ padding: '4px 0', color: '#1890ff' }}
                      >
                        {item.action_text} →
                      </Button>
                    )}
                  </div>
                </List.Item>
              );
            }}
          />
        )}
      </div>
      
      <Divider style={{ margin: 0 }} />
      
      <div style={{ padding: 12, textAlign: 'center' }}>
        <Button
          type="link"
          onClick={() => {
            navigate('/notifications');
            setVisible(false);
          }}
        >
          查看全部通知
        </Button>
      </div>
    </div>
  );

  return (
    <Dropdown
      overlay={notificationList}
      trigger={['click']}
      visible={visible}
      onVisibleChange={setVisible}
      placement="bottomRight"
    >
      <Badge count={unreadCount} size="small" offset={[-2, 2]}>
        <Button
          type="text"
          icon={<BellOutlined style={{ fontSize: 18, color: unreadCount > 0 ? '#1890ff' : '#888' }} />}
          style={{ padding: '4px 8px' }}
        />
      </Badge>
    </Dropdown>
  );
};

export default NotificationBell;
