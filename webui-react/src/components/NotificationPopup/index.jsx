/**
 * NotificationPopup - 通知弹窗组件
 * 
 * 功能：
 * 1. 自动诊断完成后弹出通知
 * 2. 显示「发现新的诊断报告」
 * 3. 点击「查看」跳转到报告详情页
 */
import React, { useState, useEffect, useRef } from 'react';
import { notification, Button, Space } from 'antd';
import {
  FileTextOutlined, AlertOutlined, CheckCircleOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { notificationAPI } from '../../utils/api';

const NotificationPopup = () => {
  const [lastNotificationId, setLastNotificationId] = useState(null);
  const hasShownRef = useRef(new Set());
  const navigate = useNavigate();

  useEffect(() => {
    checkNewNotifications();
    
    const interval = setInterval(() => {
      checkNewNotifications();
    }, 10000);
    
    return () => clearInterval(interval);
  }, []);

  const checkNewNotifications = async () => {
    try {
      const res = await notificationAPI.getUnread(5);
      if (res && res.length > 0) {
        const notifications = res;
        
        notifications.forEach(item => {
          if (!hasShownRef.current.has(item.id)) {
            hasShownRef.current.add(item.id);
            showNotification(item);
          }
        });
        
        const latestId = notifications[0]?.id;
        if (latestId && latestId !== lastNotificationId) {
          setLastNotificationId(latestId);
        }
      }
    } catch (error) {
      console.error('检查新通知失败:', error);
    }
  };

  const showNotification = (item) => {
    const isDiagnosis = item.notification_type === 'diagnosis';
    const isAlert = item.notification_type === 'alert';
    
    let icon = <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    let btn = null;
    
    if (isDiagnosis) {
      icon = <FileTextOutlined style={{ color: '#1890ff' }} />;
    } else if (isAlert) {
      icon = <AlertOutlined style={{ color: '#faad14' }} />;
    }
    
    if (item.action_url) {
      btn = (
        <Space>
          <Button
            type="primary"
            size="small"
            onClick={() => {
              markAsRead(item.id);
              navigate(item.action_url);
              notification.destroy();
            }}
          >
            {item.action_text || '查看详情'}
          </Button>
          <Button
            size="small"
            style={{
              backgroundColor: 'rgba(255, 255, 255, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.3)',
              color: 'rgba(255, 255, 255, 0.85)'
            }}
            onClick={() => {
              markAsRead(item.id);
              notification.destroy();
            }}
          >
            知道了
          </Button>
        </Space>
      );
    }

    notification.open({
      message: item.title,
      description: item.content,
      icon: icon,
      btn: btn,
      duration: isAlert ? 0 : 6,
      placement: 'topRight',
      style: {
        backgroundColor: '#1e1e1e',
        border: '1px solid #333',
        borderRadius: 8,
      },
      className: 'custom-notification-popup',
    });
  };

  const markAsRead = async (notificationId) => {
    try {
      await notificationAPI.markRead(notificationId);
    } catch (error) {
      console.error('标记已读失败:', error);
    }
  };

  return null;
};

export default NotificationPopup;
