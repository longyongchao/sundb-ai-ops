import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    // 处理 favicon.ico 请求
    {
      name: 'favicon-redirect',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === '/favicon.ico') {
            res.writeHead(302, { Location: '/favicon.svg' });
            res.end();
            return;
          }
          next();
        });
      },
    },
    // SPA 路由回退 - 处理页面刷新
    {
      name: 'spa-fallback',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          // 只处理非 API 请求和非静态资源请求
          if (!req.url.startsWith('/api') && 
              !req.url.startsWith('/diagnose') && 
              !req.url.startsWith('/report') && 
              !req.url.startsWith('/knowledge_base') && 
              !req.url.startsWith('/chat') && 
              !req.url.startsWith('/llm_model') && 
              !req.url.startsWith('/server') && 
              !req.url.startsWith('/@') && 
              !req.url.startsWith('/node_modules') &&
              !req.url.includes('.') &&
              req.headers.accept?.includes('text/html')) {
            req.url = '/index.html';
          }
          next();
        });
      },
    },
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3001,
    proxy: {
      // API 代理 - 不重写路径，直接转发
      '/api': {
        target: 'http://localhost:7861',
        changeOrigin: true,
      },
      // 诊断接口代理
      '/diagnose': {
        target: 'http://localhost:7861',
        changeOrigin: true,
      },
      // 报告接口代理 - 只匹配 /report/ 开头的路径（API请求），不匹配 /reports（前端路由）
      '/report/': {
        target: 'http://localhost:7861',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/report/, '/report'),
      },
      // 知识库接口代理
      '/knowledge_base': {
        target: 'http://localhost:7861',
        changeOrigin: true,
      },
      // 聊天接口代理
      '/chat': {
        target: 'http://localhost:7861',
        changeOrigin: true,
      },
      // LLM 模型接口代理
      '/llm_model': {
        target: 'http://localhost:7861',
        changeOrigin: true,
      },
      // 服务器配置接口代理
      '/server': {
        target: 'http://localhost:7861',
        changeOrigin: true,
      },
    },
  },
  // SPA 路由回退配置
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          antd: ['antd', '@ant-design/icons'],
          echarts: ['echarts', 'echarts-for-react'],
        },
      },
    },
  },
})