/**
 * API 请求配置模块 - 前后端通信统一接口
 * 
 * 本模块封装了所有后端 API 请求，提供统一的调用方式：
 * 1. 请求拦截 - 自动添加认证令牌和时间戳
 * 2. 响应处理 - 统一错误处理和消息提示
 * 3. 接口封装 - 提供诊断、知识库、监控等 API 方法
 * 
 * 技术实现：基于 Axios 封装，支持请求重试和超时控制
 */

import axios from 'axios';
import { message, notification } from 'antd';

// 创建axios实例
const api = axios.create({
  baseURL: '/',
  timeout: 180000, // 180秒超时（3分钟）
  headers: {
    'Content-Type': 'application/json',
  }
});

// 请求拦截器 - 添加认证等
api.interceptors.request.use(
  (config) => {
    // 在请求头中添加认证令牌（如果有）
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // 为POST/PUT请求添加时间戳防止缓存
    if (config.method === 'post' || config.method === 'put') {
      config.params = {
        ...config.params,
        _t: Date.now()
      };
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器 - 统一错误处理
api.interceptors.response.use(
  (response) => {
    // 处理后端BaseResponse格式
    const data = response.data;
    
    // 如果后端返回错误码，转换为错误
    if (data && data.code !== undefined && data.code !== 200) {
      const errorMsg = data.msg || '请求失败';
      
      // 根据错误类型显示不同的提示
      if (data.code === 401) {
        notification.error({
          message: '认证失败',
          description: '请重新登录',
          duration: 3,
        });
        // 跳转到登录页
        window.location.href = '/login';
      } else if (data.code === 500) {
        // 数据库连接失败等严重错误
        notification.error({
          message: '后端服务异常',
          description: `数据库连接失败: ${errorMsg}`,
          duration: 5,
        });
      } else {
        message.error(errorMsg);
      }
      
      return Promise.reject(new Error(errorMsg));
    }
    
    // 返回真正的数据部分
    return data?.data || data;
  },
  (error) => {
    // 网络错误或超时
    if (!error.response) {
      notification.error({
        message: <span style={{ color: '#e6e6e6' }}>网络连接失败</span>,
        description: <span style={{ color: '#b0b0b0' }}>请检查网络连接或后端服务是否启动</span>,
        duration: 5,
        style: {
          backgroundColor: '#2d2d2d',
          border: '1px solid #444',
          borderRadius: '8px',
        },
        closeIcon: <span style={{ color: '#888' }}>×</span>,
      });
    } else {
      // HTTP状态码错误
      const status = error.response?.status;
      const errorMsg = error.response?.data?.msg || error.message || '请求失败';
      
      switch (status) {
        case 400:
          message.error(`请求参数错误: ${errorMsg}`);
          break;
        case 401:
          notification.error({
            message: <span style={{ color: '#e6e6e6' }}>认证失败</span>,
            description: <span style={{ color: '#b0b0b0' }}>请重新登录</span>,
            duration: 3,
            style: {
              backgroundColor: '#2d2d2d',
              border: '1px solid #444',
              borderRadius: '8px',
            },
          });
          break;
        case 403:
          message.error('权限不足，无法访问');
          break;
        case 404:
          message.error(`请求的资源不存在: ${error.response.config.url}`);
          break;
        case 500:
          // 数据库连接失败特殊处理
          if (errorMsg.includes('PostgreSQL') || errorMsg.includes('database') || errorMsg.includes('connection')) {
            notification.error({
              message: <span style={{ color: '#e6e6e6' }}>数据库连接失败</span>,
              description: (
                <div style={{ color: '#b0b0b0' }}>
                  <p>无法连接到 PostgreSQL 数据库，请检查：</p>
                  <ul style={{ margin: '8px 0', paddingLeft: '16px' }}>
                    <li>1. 数据库服务是否启动</li>
                    <li>2. 连接配置是否正确</li>
                    <li>3. 网络连接是否正常</li>
                  </ul>
                  <p style={{ marginTop: '8px' }}>错误详情: {errorMsg}</p>
                </div>
              ),
              duration: 8,
              style: {
                backgroundColor: '#2d2d2d',
                border: '1px solid #444',
                borderRadius: '8px',
              },
            });
          } else {
            notification.error({
              message: <span style={{ color: '#e6e6e6' }}>服务器内部错误</span>,
              description: <span style={{ color: '#b0b0b0' }}>{errorMsg}</span>,
              duration: 5,
              style: {
                backgroundColor: '#2d2d2d',
                border: '1px solid #444',
                borderRadius: '8px',
              },
            });
          }
          break;
        case 502:
        case 503:
        case 504:
          notification.error({
            message: <span style={{ color: '#e6e6e6' }}>服务不可用</span>,
            description: <span style={{ color: '#b0b0b0' }}>后端服务可能未启动或正在重启</span>,
            duration: 5,
            style: {
              backgroundColor: '#2d2d2d',
              border: '1px solid #444',
              borderRadius: '8px',
            },
          });
          break;
        default:
          message.error(`请求失败 (${status}): ${errorMsg}`);
      }
    }
    
    return Promise.reject(error);
  }
);

/**
 * 诊断相关的API调用
 * 核心设计：主请求只提交任务，不等待完成；通过轮询获取状态和结果
 */
export const diagnoseAPI = {
  /**
   * 提交诊断任务（不等待完成）
   * 主请求只负责"提交任务"，后端应立刻返回确认信息
   * 超时时间设为 30 秒，只用于确认后端接收到了请求
   */
  submitDiagnosis: async (anomalyInfo, options = {}) => {
    const { timeout = 30000 } = options;
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeout);
      
      const response = await api.post('/diagnose/quick', anomalyInfo, {
        signal: controller.signal,
      });
      
      clearTimeout(timeoutId);
      
      return {
        success: true,
        data: response,
        message: '诊断任务已提交'
      };
    } catch (error) {
      if (error.response?.status === 429) {
        return {
          success: true,
          data: null,
          message: '诊断任务已在运行中'
        };
      }
      
      if (error.name === 'AbortError') {
        return {
          success: true,
          data: null,
          message: '请求已发送，后端正在处理',
          isTimeout: true
        };
      }
      
      return {
        success: false,
        data: null,
        message: error.message || '提交诊断任务失败',
        error: error
      };
    }
  },
  
  /**
   * 快速诊断（兼容旧接口，但不再等待完成）
   * @deprecated 请使用 submitDiagnosis + 轮询机制
   */
  quickDiagnose: async (anomalyInfo, options = {}) => {
    const { 
      onProgress, 
      maxRetries = 1,
      timeout = 30000
    } = options;
    
    let retryCount = 0;
    
    while (retryCount < maxRetries) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        const response = await api.post('/diagnose/quick', anomalyInfo, {
          signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
        
        return response;
      } catch (error) {
        if (error.response?.status === 429) {
          console.log('诊断任务正在运行中');
          return { status: 'running', message: '诊断任务正在运行中' };
        }
        
        retryCount++;
        
        if (error.name === 'AbortError') {
          console.log('主请求超时，但后端可能仍在处理，将通过轮询获取状态');
          return { 
            status: 'timeout', 
            message: '请求已发送，正在通过轮询获取诊断状态',
            isTimeout: true 
          };
        }
        
        if (retryCount === maxRetries) {
          throw new Error(`诊断提交失败: ${error.message}`);
        }
        
        await new Promise(resolve => setTimeout(resolve, 2000 * retryCount));
        if (onProgress) onProgress(`提交失败，正在重试 (${retryCount}/${maxRetries})`);
      }
    }
  },
  
  /**
   * 获取诊断结果
   */
  getResult: async () => {
    try {
      const response = await api.get('/diagnose/result');
      return response;
    } catch (error) {
      console.error('获取诊断结果失败:', error);
      return null;
    }
  },
  
  /**
   * 获取诊断进度（核心轮询接口）
   */
  getProgress: async () => {
    try {
      const response = await api.get('/diagnose/progress');
      return response;
    } catch (error) {
      console.error('获取诊断进度失败:', error);
      return null;
    }
  },
  
  /**
   * 获取终端输出（实时日志）
   */
  getTerminalOutput: async () => {
    try {
      const response = await api.get('/diagnose/terminal_output');
      return response;
    } catch (error) {
      console.error('获取终端输出失败:', error);
      return null;
    }
  },
  
  /**
   * 获取诊断状态
   */
  getStatus: async () => {
    try {
      const response = await api.get('/diagnose/diagnose_status');
      return response;
    } catch (error) {
      // 如果API完全不可用，返回默认状态
      console.warn('获取诊断状态失败:', error.message);
      return { is_alive: false };
    }
  },
  
  /**
   * 获取数据库连接状态
   */
  getDatabaseStatus: async () => {
    try {
      const response = await api.get('/api/database/status');
      return response;
    } catch (error) {
      // 返回模拟状态
      return {
        connected: false,
        error: error.message,
        config: {
          host: '127.0.0.1',
          port: 5432,
          database: 'dbgpt_metadata'
        }
      };
    }
  },
  
  /**
   * 获取所有诊断任务状态（A/B 类任务隔离）
   */
  getStatusAll: async () => {
    try {
      const response = await api.get('/diagnose/status/all');
      return response;
    } catch (error) {
      console.error('获取所有诊断状态失败:', error);
      return null;
    }
  },
  
  /**
   * 检查自动巡检任务状态
   */
  checkAutoTaskStatus: async () => {
    try {
      const response = await api.get('/diagnose/auto_task/status');
      return response;
    } catch (error) {
      console.error('检查自动任务状态失败:', error);
      return null;
    }
  },
  
  /**
   * 请求取消自动巡检任务（优雅取消）
   */
  cancelAutoTask: async (reason = 'user_request') => {
    try {
      const response = await api.post('/diagnose/auto_task/cancel', { reason });
      return response;
    } catch (error) {
      console.error('取消自动任务失败:', error);
      return null;
    }
  },
  
  /**
   * 重置诊断状态（管理员功能）
   */
  resetStatus: async (taskType = null) => {
    try {
      const response = await api.post('/diagnose/reset_status', 
        taskType ? { task_type: taskType } : {}
      );
      return response;
    } catch (error) {
      console.error('重置诊断状态失败:', error);
      return null;
    }
  }
};


/**
 * 知识库相关API
 */
export const knowledgeAPI = {
  // 获取知识库列表
  listKnowledgeBases: () => api.get('/knowledge_base/list_knowledge_bases'),
  
  // 创建知识库
  createKnowledgeBase: (data) => api.post('/knowledge_base/create_knowledge_base', data),
  
  // 删除知识库
  deleteKnowledgeBase: (name) => api.post('/knowledge_base/delete_knowledge_base', { knowledge_base_name: name }),
  
  // 获取文件列表
  listFiles: (kbName) => api.get('/knowledge_base/list_files', {
    params: { knowledge_base_name: kbName }
  }),
  
  // 上传文档
  uploadDocs: (data) => {
    const formData = new FormData();
    Object.keys(data).forEach(key => {
      if (key === 'files' && Array.isArray(data[key])) {
        data[key].forEach(file => formData.append('files', file));
      } else {
        formData.append(key, data[key]);
      }
    });
    
    return api.post('/knowledge_base/upload_docs', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
  }
};

/**
 * 异常注入API
 */
export const anomalyAPI = {
  // 注入异常
  inject: (data) => api.post('/api/anomaly/inject', data),
  
  // 获取评估结果
  getEvaluationResults: () => api.get('/api/evaluation/results'),
  
  // 获取异常类型
  getAnomalyTypes: () => api.get('/api/anomaly/types')
};

/**
 * 报告相关API
 */
export const reportAPI = {
  // 获取历史报告
  getHistories: () => api.get('/report/histories'),
  
  // 删除报告
  deleteHistory: (id) => api.delete(`/report/histories/${id}`)
};

/**
 * 翻译相关API
 */
export const translateAPI = {
  // 翻译文本 - 使用 DeepSeek API
  translateText: async (text, targetLang = 'zh') => {
    try {
      const response = await api.post('/diagnose/translate_text', {
        text: text,
        target_lang: targetLang
      });
      return response?.translated_text || text;
    } catch (error) {
      console.error('翻译失败:', error);
      return text;
    }
  }
};

/**
 * 测试用例库API
 */
export const testcaseAPI = {
  // 获取测试用例列表
  getList: () => api.get('/api/testcases/list'),
  
  // 获取场景分类列表
  getCategories: () => api.get('/api/testcases/categories'),
  
  // 获取指定分类的测试用例
  getByCategory: (categoryId) => api.get(`/api/testcases/category/${categoryId}`),
  
  // 获取测试用例详情
  getDetail: (caseId) => api.get(`/api/testcases/${caseId}`),
  
  // 获取统计信息
  getStatistics: () => api.get('/api/testcases/statistics')
};

/**
 * 异常检测API
 */
export const anomalyDetectorAPI = {
  // 获取异常检测状态
  getStatus: () => api.get('/api/anomaly/status'),
  
  // 获取告警历史
  getAlerts: (limit = 100) => api.get('/api/anomaly/alerts', { params: { limit } }),
  
  // 清空告警历史
  clearAlerts: () => api.delete('/api/anomaly/alerts'),
  
  // 更新阈值
  updateThresholds: (thresholds) => api.post('/api/anomaly/thresholds', thresholds)
};

/**
 * 调度服务API
 */
export const schedulerAPI = {
  // 获取调度服务状态
  getStatus: () => api.get('/api/scheduler/status'),
  
  // 设置自动诊断开关
  setAutoDiagnosis: (enabled) => api.post('/api/scheduler/auto_diagnosis', { enabled }),
  
  // 启动调度服务
  start: () => api.post('/api/scheduler/start'),
  
  // 停止调度服务
  stop: () => api.post('/api/scheduler/stop')
};

/**
 * 历史数据查询API
 */
export const historyAPI = {
  // 获取监控历史数据
  getMonitoringHistory: (params) => api.get('/api/history/monitoring', { params }),
  
  // 获取告警历史数据
  getAlertHistory: (params) => api.get('/api/history/alerts', { params }),
  
  // 获取统计信息
  getStatistics: (days = 7) => api.get('/api/history/statistics', { params: { days } }),
  
  // 获取趋势数据
  getTrendData: (metricType, hours = 24) => api.get('/api/history/trend', { 
    params: { metric_type: metricType, hours } 
  })
};

/**
 * 通知API
 */
export const notificationAPI = {
  // 获取未读通知列表
  getUnread: (limit = 20) => api.get('/api/notifications/unread', { params: { limit } }),
  
  // 获取所有通知
  getAll: (params) => api.get('/api/notifications/all', { params }),
  
  // 获取未读数量
  getCount: () => api.get('/api/notifications/count'),
  
  // 标记单条已读
  markRead: (notificationId) => api.put('/api/notifications/read', { notification_id: notificationId }),
  
  // 全部标记已读
  markAllRead: () => api.put('/api/notifications/read-all')
};

/**
 * 系统配置 API
 */
export const configAPI = {
  getLLMSettings: () => api.get('/api/settings/llm'),
};

/**
 * SunDB TRC 日志解析 API
 * 提供 SunDB 数据库 .trc 日志文件的上传、解析和查询功能
 */
export const sundbTrcAPI = {
  /**
   * 上传单个 .trc 文件并解析
   * @param {File} file - .trc 文件对象
   * @param {Object} options - 可选参数 { offset, limit }
   * @returns {Promise} 解析结果，包含 header, entries, fault_count 等
   */
  uploadTrc: async (file, options = {}) => {
    const { offset = 0, limit = 0 } = options;
    const formData = new FormData();
    formData.append('file', file);
    
    return api.post('/diagnose/upload_trc', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
      params: { offset, limit }
    });
  },

  /**
   * 上传 .tar.gz 压缩包批量解析
   * @param {File} file - .tar.gz 压缩包（包含 trc 目录）
   * @param {Object} options - 可选参数 { offset, limit }
   * @returns {Promise} 批量解析结果，包含 timeline_range, fault_summary, aeu_list 等
   */
  uploadTrcDirectory: async (file, options = {}) => {
    const { offset = 0, limit = 0 } = options;
    const formData = new FormData();
    formData.append('file', file);
    
    return api.post('/diagnose/upload_trc_directory', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
      params: { offset, limit }
    });
  },

  /**
   * 获取故障事件列表
   * @param {Object} params - 筛选参数 { severity, event_type, limit }
   * @returns {Promise} 故障事件列表
   */
  getFaultEvents: async (params = {}) => {
    return api.get('/diagnose/trc/fault_events', { params });
  },

  /**
   * 获取跨文件统一时间线
   * @param {Object} params - 筛选参数 { start_time, end_time, level, instance, limit }
   * @returns {Promise} 时间线条目列表
   */
  getTimeline: async (params = {}) => {
    return api.get('/diagnose/trc/timeline', { params });
  },

  /**
   * 获取 AEU (原子依据单元) 列表
   * @param {Object} params - 筛选参数 { event_type }
   * @returns {Promise} AEU 列表，用于 Citation 检索
   */
  getAEUList: async (params = {}) => {
    return api.get('/diagnose/trc/aeu_list', { params });
  },

  /**
   * TRC 智能诊断
   * @param {Object} trcData - TRC 解析结果，包含 filename, parser_type, fault_count, entries, entries_by_level
   * @returns {Promise} 诊断结果，包含 root_causes, solutions, reasoning_tree 等
   */
  trcDiagnose: async (trcData) => {
    return api.post('/diagnose/trc_diagnose', trcData, {
      timeout: 180000
    });
  }
};

export default api;