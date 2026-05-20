import React, { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Dropdown, Avatar, Space, message, Modal } from 'antd'
import {
  DashboardOutlined,
  BugOutlined,
  BookOutlined,
  MessageOutlined,
  BarChartOutlined,
  MonitorOutlined,
  SettingOutlined,
  UserOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  DatabaseOutlined,
  ApiOutlined,
  BranchesOutlined,
} from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'
import NotificationBell from '../../components/NotificationBell'
import NotificationPopup from '../../components/NotificationPopup'
import './index.scss'

const { Header, Sider, Content } = Layout

const pageActivityMap = {
  '/evolution': { type: 'evolution', action: '访问自进化中心' },
  '/dashboard': { type: 'dashboard', action: '访问控制台' },
  '/diagnosis': { type: 'diagnose', action: '使用智能诊断' },
  '/monitoring': { type: 'monitor', action: '查看实时监控' },
  '/knowledge': { type: 'knowledge', action: '管理知识库' },
  '/knowledge-chat': { type: 'knowledge', action: '使用知识库对话' },
  '/reports': { type: 'diagnose', action: '查看诊断报告' },
  '/evaluation': { type: 'evaluation', action: '查看评估结果' },
  '/profile': { type: 'dashboard', action: '访问个人中心' },
}

const recordActivity = (pathname) => {
  const activityInfo = pageActivityMap[pathname]
  if (!activityInfo) return
  
  const now = new Date()
  const beijingTime = now.toLocaleString('zh-CN', { 
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).replace(/\//g, '-')
  
  const newActivity = {
    type: activityInfo.type,
    action: activityInfo.action,
    time: beijingTime,
    path: pathname,
  }
  
  try {
    const savedActivities = localStorage.getItem('userActivities')
    let activities = savedActivities ? JSON.parse(savedActivities) : []
    
    if (activities.length > 0 && activities[0].path === pathname) {
      return
    }
    
    activities = [newActivity, ...activities].slice(0, 50)
    localStorage.setItem('userActivities', JSON.stringify(activities))
  } catch (e) {
    console.log('记录活动失败:', e)
  }
}

const menuItems = [
  {
    key: '/evolution',
    icon: <BranchesOutlined />,
    label: '自进化中心',
  },
  {
    key: '/dashboard',
    icon: <DashboardOutlined />,
    label: '控制台',
  },
  {
    key: '/diagnosis',
    icon: <BugOutlined />,
    label: '智能诊断',
  },
  {
    key: '/monitoring',
    icon: <MonitorOutlined />,
    label: '实时监控',
  },
  {
    key: '/knowledge',
    icon: <BookOutlined />,
    label: '知识库管理',
  },
  {
    key: '/knowledge-chat',
    icon: <MessageOutlined />,
    label: '知识库对话',
  },
  {
    key: '/reports',
    icon: <BarChartOutlined />,
    label: '诊断报告',
  },
]

const MainLayout = () => {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    recordActivity(location.pathname)
  }, [location.pathname])

  const handleMenuClick = ({ key }) => {
    navigate(key)
  }

  const userMenuItems = [
    {
      key: 'profile',
      label: '个人中心',
      onClick: () => {
        navigate('/profile')
      },
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      label: '退出登录',
      danger: true,
      onClick: () => {
        Modal.confirm({
          title: '确认退出',
          content: '确定要退出登录吗？',
          okText: '确定',
          cancelText: '取消',
          onOk: () => {
            localStorage.removeItem('token')
            localStorage.removeItem('username')
            localStorage.removeItem('role')
            localStorage.removeItem('userActivities')
            message.success('已退出登录')
            navigate('/login')
          },
        })
      },
    },
  ]

  return (
    <Layout className="main-layout">
      <NotificationPopup />
      {/* 背景动画效果 */}
      <div className="background-effects">
        <div className="grid-overlay" />
        <div className="glow-orb orb-1" />
        <div className="glow-orb orb-2" />
        <div className="glow-orb orb-3" />
      </div>

      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        className="sider"
        width={240}
      >
        <div className="logo-container">
          <motion.div
            className="logo"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <div className="logo-icon">
              <DatabaseOutlined />
            </div>
            <AnimatePresence>
              {!collapsed && (
                <motion.div
                  className="logo-text"
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <span className="text-gradient">智能运维系统</span>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          className="side-menu"
        />

        <div className="sider-footer">
          <div className="system-status">
            <div className="status-item">
              <ApiOutlined className="status-icon" />
              <AnimatePresence>
                {!collapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    API: 正常
                  </motion.span>
                )}
              </AnimatePresence>
            </div>
            <div className="status-item">
              <DatabaseOutlined className="status-icon online" />
              <AnimatePresence>
                {!collapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    数据库: 在线
                  </motion.span>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </Sider>

      <Layout className="main-container">
        <Header className="header">
          <div className="header-left">
            <Button
              type="text"
              className="collapse-btn"
              onClick={() => setCollapsed(!collapsed)}
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            />
          </div>

          <div className="header-right">
            <NotificationBell />
            <Dropdown
              menu={{ items: userMenuItems }}
              placement="bottomRight"
              trigger={['click']}
            >
              <div className="user-info">
                <Avatar
                  size="small"
                  icon={<UserOutlined />}
                  className="user-avatar"
                />
                <span className="user-name">{localStorage.getItem('username') || 'admin'}</span>
              </div>
            </Dropdown>
          </div>
        </Header>

        <Content className="content">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="content-wrapper"
          >
            <Outlet />
          </motion.div>
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout
