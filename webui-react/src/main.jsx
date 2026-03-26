import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './styles/index.scss'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider 
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#00d4ff',
          colorBgContainer: '#0a1628',
          colorText: '#ffffff',
          colorBorder: '#1e3a5f',
          borderRadius: 8,
        },
        components: {
          Menu: {
            darkItemBg: '#0a1628',
            darkItemSelectedBg: '#1e3a5f',
          },
          Card: {
            colorBgContainer: 'rgba(10, 22, 40, 0.8)',
          },
          Table: {
            headerBg: '#0d1f35',
            rowHoverBg: '#1e3a5f',
          },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)