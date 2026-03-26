/**
 * KnowledgeChat 页面 - 知识库对话
 * Reference: D-Bot Paper Section 5 - Diagnosis Prompt Generation
 * 对接 DeepSeek API 实现真实对话
 * 支持智能图表生成：折线图、柱状图、饼图、热力图
 */
import React, { useState, useRef, useEffect } from 'react';
import { Row, Col, Card, Input, Button, Select, Avatar, Spin, message, Empty, Space, Tag, Divider, List, Tooltip, Modal, Popconfirm } from 'antd';
import {
  MessageOutlined, SendOutlined, RobotOutlined, UserOutlined,
  ClearOutlined, FileTextOutlined, BarChartOutlined, PlusOutlined,
  MessageFilled, HistoryOutlined, DeleteOutlined,
  FileSearchOutlined, CheckCircleOutlined
} from '@ant-design/icons';
import axios from 'axios';
import { marked } from 'marked';
import { MetricLineChart, AnomalyPieChart, DiagnosisHeatMap, MetricBarChart } from '@/components/Charts';

const { TextArea } = Input;
const { Option } = Select;

const STORAGE_KEY = 'dbgpt_knowledge_chat_history';

const SYSTEM_PROMPT = `你是 D-Bot 数据库智能诊断系统的专业助手，专注于 PostgreSQL 数据库运维领域。

你的专业范围包括：
1. 数据库性能诊断与优化
2. SQL 查询分析与优化建议
3. 索引设计与优化
4. 数据库故障排查
5. 锁等待与死锁分析
6. 慢查询优化
7. 数据库监控指标解读
8. 存储与内存优化

请严格遵守以下规则：
- 只回答与数据库运维、性能诊断、SQL优化相关的问题
- 对于无关问题，礼貌地说明你的专业范围并引导用户提问数据库相关问题
- 回答要专业、准确、有深度
- 结合提供的知识库内容给出具体建议`;

const KnowledgeChat = () => {
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [selectedModel, setSelectedModel] = useState('deepseek-chat');
  const [chartData, setChartData] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [reportModalVisible, setReportModalVisible] = useState(false);
  const [diagnosisReports, setDiagnosisReports] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [loadingReports, setLoadingReports] = useState(false);
  const messagesEndRef = useRef(null);
  
  const modelOptions = [
    { value: 'deepseek-chat', label: 'DeepSeek Chat (大模型+知识库)' },
    { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner (大模型+知识库)' },
    { value: 'local-kb', label: '本地知识库模式 (离线)' },
  ];

  const loadConversations = () => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        setConversations(parsed);
        if (parsed.length > 0) {
          setActiveConversationId(parsed[0].id);
          setMessages(parsed[0].messages || []);
        }
      }
    } catch (e) {
      console.error('加载对话历史失败:', e);
    }
  };

  const saveConversations = (convs) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(convs));
    } catch (e) {
      console.error('保存对话历史失败:', e);
    }
  };

  const createNewConversation = () => {
    const newConv = {
      id: Date.now().toString(),
      title: '新对话',
      messages: [],
      model: selectedModel,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    
    setConversations(prev => {
      const newConvs = [newConv, ...prev];
      saveConversations(newConvs);
      return newConvs;
    });
    setActiveConversationId(newConv.id);
    setMessages([]);
    message.success('已创建新对话');
  };

  const switchConversation = (convId) => {
    const conv = conversations.find(c => c.id === convId);
    if (conv) {
      setActiveConversationId(convId);
      setMessages(conv.messages || []);
      if (conv.model) {
        setSelectedModel(conv.model);
      }
    }
  };

  const deleteConversation = (convId, e) => {
    e.stopPropagation();
    const newConvs = conversations.filter(c => c.id !== convId);
    setConversations(newConvs);
    saveConversations(newConvs);
    
    if (convId === activeConversationId) {
      if (newConvs.length > 0) {
        setActiveConversationId(newConvs[0].id);
        setMessages(newConvs[0].messages || []);
      } else {
        setActiveConversationId(null);
        setMessages([]);
      }
    }
    message.success('对话已删除');
  };

  const fetchDiagnosisReports = async () => {
    setLoadingReports(true);
    try {
      const response = await axios.get('/report/histories', {
        params: { start: '', end: '', model: 'DeepSeek' }
      });
      if (response.data?.code === 200 && response.data?.data) {
        setDiagnosisReports(response.data.data);
      } else if (Array.isArray(response.data?.data)) {
        setDiagnosisReports(response.data.data);
      } else if (Array.isArray(response.data)) {
        setDiagnosisReports(response.data);
      } else {
        setDiagnosisReports([]);
      }
    } catch (error) {
      console.error('获取诊断报告失败:', error);
      setDiagnosisReports([]);
      message.warning('获取诊断报告失败，请稍后重试');
    } finally {
      setLoadingReports(false);
    }
  };

  const openReportModal = () => {
    try {
      setReportModalVisible(true);
      fetchDiagnosisReports();
    } catch (error) {
      console.error('打开报告模态框失败:', error);
      message.error('打开报告选择框失败');
    }
  };

  const selectReport = (report) => {
    setSelectedReport(report);
  };

  const confirmImportReport = () => {
    try {
      if (!selectedReport) {
        message.warning('请先选择一个诊断报告');
        return;
      }
      
      let currentConvId = activeConversationId;
      if (!currentConvId) {
        currentConvId = Date.now().toString();
        setActiveConversationId(currentConvId);
      }
      
      const anomalyType = selectedReport.anomaly_type || '未知异常';
      const userMessage = {
        role: 'user',
        content: `已导入【${anomalyType}】诊断报告`,
        isImportAction: true,
      };
      
      const reportContent = formatReportContent(selectedReport);
      const assistantMessage = {
        role: 'assistant',
        content: `**📋 诊断报告内容**\n\n${reportContent}`,
        isReport: true,
        reportData: selectedReport
      };
      
      const newMessages = [...messages, userMessage, assistantMessage];
      setMessages(newMessages);
      setReportModalVisible(false);
      setSelectedReport(null);
      message.success('诊断报告已导入');
    } catch (error) {
      console.error('导入报告失败:', error);
      message.error('导入报告失败，请重试');
    }
  };

  const formatReportContent = (report) => {
    try {
      let content = '';
      
      if (report.anomaly_info) {
        content += `**异常类型:** ${report.anomaly_info.alert_type || '未知'}\n`;
        content += `**异常描述:** ${report.anomaly_info.description || '无'}\n\n`;
      }
      
      if (report.root_causes && report.root_causes.length > 0) {
        content += `**根因分析:**\n`;
        report.root_causes.forEach((cause, idx) => {
          if (typeof cause === 'string') {
            content += `${idx + 1}. ${cause}\n`;
          } else {
            content += `${idx + 1}. ${cause.type || '未知'}: ${cause.description || ''}\n`;
          }
        });
        content += '\n';
      }
      
      if (report.solutions && report.solutions.length > 0) {
        content += `**解决方案:**\n`;
        report.solutions.forEach((solution, idx) => {
          if (typeof solution === 'string') {
            content += `${idx + 1}. ${solution}\n`;
          } else {
            content += `${idx + 1}. ${solution.action || solution.explanation || ''}\n`;
          }
        });
        content += '\n';
      }
      
      if (report.confidence) {
        content += `**诊断置信度:** ${(report.confidence * 100).toFixed(1)}%\n`;
      }
      
      if (report.diagnosis_time) {
        content += `**诊断耗时:** ${report.diagnosis_time.toFixed(2)}秒\n`;
      }
      
      return content || '报告内容为空';
    } catch (error) {
      console.error('格式化报告失败:', error);
      return '报告解析失败';
    }
  };

  const formatReportTime = (timestamp) => {
    try {
      if (!timestamp) return '未知时间';
      let date;
      if (typeof timestamp === 'number') {
        date = new Date(timestamp * 1000);
      } else if (typeof timestamp === 'string') {
        date = new Date(timestamp);
      } else {
        return '未知时间';
      }
      if (isNaN(date.getTime())) {
        return '未知时间';
      }
      return date.toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    } catch {
      return '未知时间';
    }
  };

  const updateCurrentConversation = (newMessages) => {
    setConversations(prev => {
      const existingConvIndex = prev.findIndex(conv => conv.id === activeConversationId);
      
      if (existingConvIndex === -1 && activeConversationId) {
        const firstUserMsg = newMessages.find(m => m.role === 'user');
        const title = firstUserMsg 
          ? firstUserMsg.content.slice(0, 20) + (firstUserMsg.content.length > 20 ? '...' : '')
          : '新对话';
        const newConv = {
          id: activeConversationId,
          title,
          messages: newMessages,
          model: selectedModel,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        const newConvs = [newConv, ...prev];
        saveConversations(newConvs);
        return newConvs;
      }
      
      const newConvs = prev.map(conv => {
        if (conv.id === activeConversationId) {
          const firstUserMsg = newMessages.find(m => m.role === 'user');
          let title = conv.title;
          if (firstUserMsg && conv.title === '新对话') {
            title = firstUserMsg.content.slice(0, 20) + (firstUserMsg.content.length > 20 ? '...' : '');
          }
          return {
            ...conv,
            messages: newMessages,
            title,
            model: selectedModel,
            updatedAt: new Date().toISOString(),
          };
        }
        return conv;
      });
      newConvs.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
      saveConversations(newConvs);
      return newConvs;
    });
  };

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (activeConversationId && messages.length > 0) {
      updateCurrentConversation(messages);
    }
  }, [messages, activeConversationId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const chartKeywords = {
    line: ['折线图', '线图', '趋势图', '走势图', 'line'],
    bar: ['柱状图', '条形图', '柱图', 'bar'],
    pie: ['饼图', '饼状图', '扇形图', 'pie'],
    heatmap: ['热力图', '热图', '相关性图', 'heatmap', 'heat']
  };

  const parseChartRequest = (query) => {
    const lowerQuery = query.toLowerCase();
    const requestedCharts = [];
    for (const [chartType, keywords] of Object.entries(chartKeywords)) {
      if (keywords.some(kw => lowerQuery.includes(kw))) {
        requestedCharts.push(chartType);
      }
    }
    return requestedCharts;
  };

  const sendMessage = async () => {
    if (!inputValue.trim()) {
      message.warning('请输入内容');
      return;
    }

    if (!activeConversationId) {
      const newConvId = Date.now().toString();
      setActiveConversationId(newConvId);
    }

    const userMessage = { role: 'user', content: inputValue };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInputValue('');
    setLoading(true);

    try {
      let response;
      
      if (selectedModel === 'local-kb') {
        response = await axios.post('/knowledge_base/search_all_docs', {
          query: inputValue,
          top_k: 5,
          score_threshold: 0.5
        });
        
        const knowledgeResults = response.data?.data || [];
        let knowledgeContent = '';
        
        if (knowledgeResults.length > 0) {
          knowledgeContent = `**📚 全库检索结果** (共 ${response.data?.total_count || knowledgeResults.length} 条)\n\n`;
          knowledgeResults.forEach((item, idx) => {
            const doc = item.page_content || item.content || '';
            const score = item.score || 0;
            const kbName = item.kb_name || item.metadata?.kb_name || '未知知识库';
            knowledgeContent += `### ${idx + 1}. [${kbName}] 相关度: ${(score * 100).toFixed(1)}%\n`;
            knowledgeContent += `${doc.slice(0, 500)}${doc.length > 500 ? '...' : ''}\n\n`;
            knowledgeContent += '---\n\n';
          });
        } else {
          knowledgeContent = '未在任何知识库中找到相关内容，请尝试其他关键词或先上传知识文档。';
        }
        
        setMessages(prev => [...prev, { role: 'assistant', content: knowledgeContent }]);
      } else {
        response = await axios.post('/chat/knowledge_base_chat', {
          query: inputValue,
          knowledge_base_name: '__all__',
          model_name: selectedModel,
          history: messages.slice(-10).map(m => ({
            role: m.role,
            content: m.content
          })),
          stream: false,
          top_k: 5,
          score_threshold: 0.5,
          prompt_name: "default"
        }, {
          headers: { 'Content-Type': 'application/json' }
        });
        
        console.log('Knowledge Base Chat API Response:', response.data);
        
        let aiResponse = '抱歉，我无法处理您的请求。';
        try {
          const responseData = typeof response.data === 'string' 
            ? JSON.parse(response.data) 
            : response.data;
          aiResponse = responseData.answer || responseData.response || responseData.message || responseData.content || aiResponse;
        } catch (e) {
          aiResponse = response.data?.answer || response.data || aiResponse;
        }
        
        const charts = parseChartRequest(inputValue);
        
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: aiResponse,
          charts: charts
        }]);
        
        if (charts.length > 0) {
          try {
            const metricsRes = await axios.get('/api/dashboard/metrics');
            if (metricsRes.data?.data) {
              setChartData(metricsRes.data);
            }
          } catch (e) {
            console.log('获取图表数据失败:', e);
          }
        }
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      console.error('错误详情:', error.response?.data || error.message);
      
      let errorMessage = '抱歉，连接服务器失败，请检查网络或稍后重试。';
      if (error.response?.status === 404) {
        errorMessage = '聊天接口未找到，请检查后端服务是否正常运行。';
      } else if (error.response?.status === 500) {
        errorMessage = '服务器内部错误，请查看后端日志。';
      } else if (error.response?.data?.detail) {
        errorMessage = `错误: ${error.response.data.detail}`;
      }
      
      message.error(errorMessage);
      const fallbackResponse = getFallbackResponse(inputValue);
      setMessages(prev => [...prev, { role: 'assistant', content: fallbackResponse }]);
    } finally {
      setLoading(false);
    }
  };

  const getFallbackResponse = (query) => {
    const lowerQuery = query.toLowerCase();
    
    if (lowerQuery.includes('cpu') || lowerQuery.includes('处理器')) {
      return `**CPU 性能分析建议**\n\n针对 CPU 使用率过高的问题，建议检查以下几点：\n\n1. **慢查询分析**: 检查是否有长时间运行的 SQL 查询\n2. **索引优化**: 确保常用查询字段有合适的索引\n3. **连接池配置**: 检查数据库连接数是否合理\n4. **锁等待**: 排查是否存在锁争用问题\n\n如需详细分析，请使用系统的「智能诊断」功能。`;
    }
    
    if (lowerQuery.includes('内存') || lowerQuery.includes('memory')) {
      return `**内存使用分析建议**\n\n针对内存使用率过高的问题，建议检查：\n\n1. **shared_buffers**: PostgreSQL 共享缓冲区配置\n2. **work_mem**: 单个查询的工作内存\n3. **连接数**: 每个连接都会占用内存\n4. **临时表**: 检查是否有大量临时表\n\n建议使用「实时监控」页面查看详细指标。`;
    }
    
    if (lowerQuery.includes('慢查询') || lowerQuery.includes('slow')) {
      return `**慢查询优化建议**\n\n优化慢查询的常见方法：\n\n1. **EXPLAIN 分析**: 使用 EXPLAIN ANALYZE 查看执行计划\n2. **索引优化**: 为 WHERE、JOIN 条件添加索引\n3. **查询重写**: 避免全表扫描，使用 LIMIT\n4. **统计信息更新**: 执行 ANALYZE 更新统计信息\n\n系统已集成慢查询监控，可在「实时监控」页面查看。`;
    }
    
    return `**D-Bot 数据库诊断助手**\n\n我是专业的 PostgreSQL 数据库运维助手，可以帮您：\n\n- 🔍 分析数据库性能问题\n- 📊 优化 SQL 查询\n- 🔧 提供索引建议\n- 🚨 排查故障原因\n\n请描述您遇到的数据库问题，我将为您提供专业建议。`;
  };

  const clearMessages = () => {
    setMessages([]);
    message.success('对话已清空');
  };

  const renderMarkdown = (text) => {
    try {
      if (!text || text.trim() === '') {
        return '<span style="color: #999; font-style: italic;">正在思考中...</span>';
      }
      return marked.parse(String(text));
    } catch (e) {
      console.error('Markdown parse error:', e);
      return String(text || '');
    }
  };

  const renderMessage = (msg, index) => {
    const isUser = msg.role === 'user';
    const content = msg.content || '';
    const charts = msg.charts || [];

    return (
      <div
        key={index}
        style={{
          display: 'flex',
          justifyContent: isUser ? 'flex-end' : 'flex-start',
          marginBottom: '16px',
          width: '100%'
        }}
      >
        <div style={{ display: 'flex', maxWidth: isUser ? '70%' : '100%' }}>
          {!isUser && (
            <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#1890ff', marginRight: '8px' }} />
          )}
          <div
            style={{
              padding: isUser ? '12px 16px' : '16px',
              borderRadius: '8px',
              backgroundColor: isUser ? '#1890ff' : '#2d2d3d',
              color: isUser ? 'white' : '#f0f0f0',
              minHeight: isUser ? 'auto' : '44px',
              minWidth: isUser ? 'auto' : '60px',
              width: isUser ? 'auto' : '100%'
            }}
          >
            {isUser ? (
              <span>{String(content)}</span>
            ) : (
              <>
                <div
                  className="markdown-content"
                  style={{ color: '#f0f0f0' }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
                />
                {charts.length > 0 && content && (
                  <div style={{ marginTop: '16px' }}>
                    <Divider style={{ borderColor: '#3d3d4d', margin: '12px 0' }}>
                      <Tag icon={<BarChartOutlined />} color="blue">数据可视化</Tag>
                    </Divider>
                    <Row gutter={[16, 16]}>
                      {charts.includes('line') && (
                        <Col span={charts.length === 1 ? 24 : charts.length === 2 ? 12 : 12}>
                          <Card size="small" style={{ background: '#1e1e2e', border: '1px solid #3d3d4d' }}>
                            <MetricLineChart 
                              data={chartData?.data?.metrics} 
                              title="资源指标趋势" 
                              height={250}
                            />
                          </Card>
                        </Col>
                      )}
                      {charts.includes('bar') && (
                        <Col span={charts.length === 1 ? 24 : charts.length === 2 ? 12 : 12}>
                          <Card size="small" style={{ background: '#1e1e2e', border: '1px solid #3d3d4d' }}>
                            <MetricBarChart 
                              data={chartData?.data?.metrics ? {
                                categories: ['CPU', '内存', '磁盘I/O', '网络', '连接数'],
                                values: [
                                  chartData.data.metrics.cpu?.slice(-1)[0] || 0,
                                  chartData.data.metrics.memory?.slice(-1)[0] || 0,
                                  chartData.data.metrics.disk_io?.slice(-1)[0] || 0,
                                  chartData.data.metrics.network?.slice(-1)[0] || 0,
                                  chartData.data.stats?.db_connections || 0
                                ]
                              } : null}
                              title="当前指标对比" 
                              height={250}
                            />
                          </Card>
                        </Col>
                      )}
                      {charts.includes('pie') && (
                        <Col span={charts.length === 1 ? 24 : charts.length === 2 ? 12 : 12}>
                          <Card size="small" style={{ background: '#1e1e2e', border: '1px solid #3d3d4d' }}>
                            <AnomalyPieChart 
                              data={chartData?.data?.anomalies} 
                              title="异常类型分布" 
                              height={250}
                            />
                          </Card>
                        </Col>
                      )}
                      {charts.includes('heatmap') && (
                        <Col span={24}>
                          <Card size="small" style={{ background: '#1e1e2e', border: '1px solid #3d3d4d' }}>
                            <DiagnosisHeatMap 
                              data={chartData?.data?.correlation} 
                              title="指标相关性分析" 
                              height={300}
                            />
                          </Card>
                        </Col>
                      )}
                    </Row>
                  </div>
                )}
              </>
            )}
          </div>
          {isUser && (
            <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#52c41a', marginLeft: '8px' }} />
          )}
        </div>
      </div>
    );
  };

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
    return date.toLocaleDateString('zh-CN');
  };

  const renderSidebar = () => (
    <div style={{
      width: sidebarCollapsed ? '0px' : '280px',
      height: '100%',
      backgroundColor: '#1a1a2e',
      borderRight: '1px solid #2d2d3d',
      display: 'flex',
      flexDirection: 'column',
      transition: 'width 0.3s ease',
      overflow: 'hidden',
    }}>
      {!sidebarCollapsed && (
        <>
          <div style={{
            padding: '16px',
            borderBottom: '1px solid #2d2d3d',
          }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={createNewConversation}
              block
              style={{
                height: '44px',
                borderRadius: '8px',
                fontSize: '14px',
              }}
            >
              新建对话
            </Button>
          </div>
          <div style={{
            flex: 1,
            overflow: 'auto',
            padding: '8px',
          }}>
            <div style={{
              padding: '8px 12px',
              color: '#888',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}>
              <HistoryOutlined /> 历史对话 ({conversations.length})
            </div>
            <List
              dataSource={conversations}
              renderItem={(conv) => (
                <List.Item
                  onClick={() => switchConversation(conv.id)}
                  style={{
                    padding: '12px',
                    cursor: 'pointer',
                    backgroundColor: conv.id === activeConversationId ? '#2d2d4d' : 'transparent',
                    borderRadius: '8px',
                    marginBottom: '4px',
                    border: conv.id === activeConversationId ? '1px solid #1890ff' : '1px solid transparent',
                    transition: 'all 0.2s ease',
                    position: 'relative',
                  }}
                  onMouseEnter={(e) => {
                    if (conv.id !== activeConversationId) {
                      e.currentTarget.style.backgroundColor = '#252540';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (conv.id !== activeConversationId) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }
                  }}
                >
                  <div style={{ width: '100%' }}>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      marginBottom: '4px',
                    }}>
                      <MessageFilled style={{ color: '#1890ff', fontSize: '14px' }} />
                      <span style={{
                        color: '#f0f0f0',
                        fontSize: '14px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        flex: 1,
                      }}>
                        {conv.title}
                      </span>
                      <Tooltip title="删除对话">
                        <Button
                          type="text"
                          icon={<DeleteOutlined />}
                          size="small"
                          onClick={(e) => deleteConversation(conv.id, e)}
                          style={{
                            color: '#666',
                            opacity: 0.6,
                            padding: '2px 4px',
                            height: 'auto',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.opacity = 1;
                            e.currentTarget.style.color = '#ff4d4f';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.opacity = 0.6;
                            e.currentTarget.style.color = '#666';
                          }}
                        />
                      </Tooltip>
                    </div>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}>
                      <Tag style={{
                        fontSize: '10px',
                        padding: '0 4px',
                        height: '18px',
                        lineHeight: '18px',
                        background: conv.model === 'local-kb' ? '#2d2d3d' : '#1a3a5c',
                        color: conv.model === 'local-kb' ? '#52c41a' : '#64b5f6',
                        border: 'none',
                      }}>
                        {conv.model === 'local-kb' ? '本地' : '大模型'}
                      </Tag>
                      <span style={{ color: '#666', fontSize: '11px' }}>
                        {formatDate(conv.updatedAt)}
                      </span>
                    </div>
                  </div>
                </List.Item>
              )}
            />
          </div>
        </>
      )}
    </div>
  );

  const renderReportModal = () => (
    <Modal
      title={
        <span>
          <FileSearchOutlined style={{ marginRight: 8, color: '#1890ff' }} />
          选择诊断报告
        </span>
      }
      open={reportModalVisible}
      onCancel={() => {
        setReportModalVisible(false);
        setSelectedReport(null);
      }}
      onOk={confirmImportReport}
      okText="导入报告"
      cancelText="取消"
      width={700}
      style={{ top: 50 }}
      okButtonProps={{ disabled: !selectedReport }}
      styles={{ 
        header: { background: '#1E293B', borderBottom: '1px solid #334155' },
        body: { background: '#0F172A', padding: '20px', maxHeight: '70vh', overflowY: 'auto' },
        content: { background: '#0F172A' }
      }}
    >
      <div style={{ marginBottom: 16 }}>
        <span style={{ color: '#888', fontSize: 13 }}>
          选择一个诊断报告导入到当前对话中，AI 将基于报告内容进行分析和回答
        </span>
      </div>
      
      {loadingReports ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip="加载诊断报告中..." />
        </div>
      ) : diagnosisReports.length === 0 ? (
        <Empty description={<span style={{ color: '#666' }}>暂无诊断报告</span>} />
      ) : (
        <List
          style={{ maxHeight: 400, overflow: 'auto' }}
          dataSource={diagnosisReports}
          renderItem={(report) => (
            <List.Item
              onClick={() => selectReport(report)}
              style={{
                padding: '12px 16px',
                cursor: 'pointer',
                backgroundColor: selectedReport?.time === report.time ? '#1a3a5c' : '#1e1e2e',
                borderRadius: '8px',
                marginBottom: '8px',
                border: selectedReport?.time === report.time ? '2px solid #1890ff' : '1px solid #3d3d4d',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <Space>
                    {selectedReport?.time === report.time && (
                      <CheckCircleOutlined style={{ color: '#1890ff', fontSize: 16 }} />
                    )}
                    <Tag style={{
                      background: report.anomaly_type?.includes('CPU') ? 'rgba(250,173,20,0.2)' : report.anomaly_type?.includes('IO') ? 'rgba(34,211,238,0.2)' : 'rgba(24,144,255,0.2)',
                      color: report.anomaly_type?.includes('CPU') ? '#ffc53d' : report.anomaly_type?.includes('IO') ? '#22d3ee' : '#40a9ff',
                      border: `1px solid ${report.anomaly_type?.includes('CPU') ? '#ffc53d' : report.anomaly_type?.includes('IO') ? '#22d3ee' : '#40a9ff'}`,
                      fontWeight: 500,
                      padding: '2px 8px',
                    }}>
                      {report.anomaly_type || '未知异常'}
                    </Tag>
                  </Space>
                  <span style={{ color: '#b0b0b0', fontSize: 12, fontWeight: 500 }}>
                    {formatReportTime(report.time)}
                  </span>
                </div>
                <div style={{ color: '#e0e0e0', fontSize: 13 }}>
                  {report.anomaly_info?.description || '无描述'}
                </div>
                {report.root_causes && report.root_causes.length > 0 && (
                  <div style={{ color: '#a0a0a0', fontSize: 12, marginTop: 8 }}>
                    <strong style={{ color: '#c0c0c0' }}>根因:</strong> {typeof report.root_causes[0] === 'string' ? report.root_causes[0].slice(0, 50) : report.root_causes[0]?.type || '未知'}...
                  </div>
                )}
                {report.confidence && (
                  <div style={{ marginTop: 8 }}>
                    <Tag style={{
                      fontSize: 11,
                      background: 'rgba(82,196,26,0.2)',
                      border: '1px solid #52c41a',
                      color: '#73d13d',
                      fontWeight: 500,
                    }}>
                      置信度: {(report.confidence * 100).toFixed(1)}%
                    </Tag>
                  </div>
                )}
              </div>
            </List.Item>
          )}
        />
      )}
    </Modal>
  );

  return (
    <div className="knowledge-chat-page" style={{ height: 'calc(100vh - 72px)', display: 'flex', backgroundColor: '#0f0f1a' }}>
      {renderSidebar()}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
        <Button
          type="text"
          icon={sidebarCollapsed ? <span style={{ fontSize: '16px' }}>{'>>'}</span> : <span style={{ fontSize: '16px' }}>{'<<'}</span>}
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          style={{
            position: 'absolute',
            left: '8px',
            top: '12px',
            zIndex: 10,
            color: '#888',
            width: '32px',
            height: '32px',
            padding: 0,
          }}
        />
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid #2d2d3d',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          backgroundColor: '#1a1a2e',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: '40px' }}>
            <MessageOutlined style={{ fontSize: '18px', color: '#1890ff' }} />
            <span style={{ fontSize: '18px', fontWeight: 500, color: '#f0f0f0' }}>
              知识库对话
            </span>
            <Tag style={{
              background: '#2d2d3d',
              color: selectedModel === 'local-kb' ? '#52c41a' : '#1890ff',
              border: `1px solid ${selectedModel === 'local-kb' ? '#52c41a' : '#1890ff'}`,
            }}>
              {selectedModel === 'local-kb' ? '本地知识库' : '大模型+知识库'}
            </Tag>
          </div>
          <Space>
            <Tooltip title="导入诊断报告">
              <Button 
                icon={<FileSearchOutlined />} 
                onClick={openReportModal}
                style={{ borderColor: '#1890ff', color: '#1890ff', background: 'transparent' }}
              >
                导入报告
              </Button>
            </Tooltip>
            <Select
              value={selectedModel}
              onChange={setSelectedModel}
              style={{ width: 280 }}
              placeholder="选择模式"
              dropdownStyle={{ background: '#2d2d3d' }}
              dropdownMatchSelectWidth
            >
              {modelOptions.map(model => (
                <Option key={model.value} value={model.value}>
                  <span style={{ color: '#e0e0e0' }}>{model.label}</span>
                </Option>
              ))}
            </Select>
            <Popconfirm
              title="确认清空"
              description="确定要清空当前对话吗？"
              onConfirm={clearMessages}
              okText="确定"
              cancelText="取消"
            >
              <Button icon={<ClearOutlined />} style={{ background: 'transparent', borderColor: '#3d3d4d', color: '#e0e0e0' }}>
                清空当前对话
              </Button>
            </Popconfirm>
          </Space>
        </div>
        <div style={{
          flex: 1,
          overflow: 'auto',
          padding: '16px',
          backgroundColor: '#12121f',
        }}>
          {messages.length === 0 ? (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: '#666',
            }}>
              <MessageOutlined style={{ fontSize: '48px', marginBottom: '16px', color: '#2d2d3d' }} />
              <div style={{ fontSize: '16px', marginBottom: '8px' }}>
                {selectedModel === 'local-kb' ? '开始查询本地知识库' : '开始与 AI 对话'}
              </div>
              <div style={{ fontSize: '12px', color: '#555' }}>
                点击左侧「新建对话」或直接输入问题开始
              </div>
            </div>
          ) : (
            messages.map((msg, index) => renderMessage(msg, index))
          )}
          <div ref={messagesEndRef} />
        </div>
        <div style={{
          padding: '16px 24px',
          borderTop: '1px solid #2d2d3d',
          backgroundColor: '#1a1a2e',
        }}>
          <div style={{ display: 'flex', gap: '12px', maxWidth: '1200px', margin: '0 auto' }}>
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="请输入数据库运维、性能诊断、SQL优化相关问题，我将结合知识库与实时监控数据为您解答..."
              autoSize={{ minRows: 1, maxRows: 4 }}
              style={{
                backgroundColor: '#2d2d3d',
                border: '1px solid #3d3d4d',
                color: '#f0f0f0',
                borderRadius: '8px',
              }}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={sendMessage}
              loading={loading}
              style={{ minWidth: '100px', height: 'auto', borderRadius: '8px' }}
            >
              {selectedModel === 'local-kb' ? '搜索' : '发送'}
            </Button>
          </div>
        </div>
      </div>
      {renderReportModal()}
    </div>
  );
};

export default KnowledgeChat;
