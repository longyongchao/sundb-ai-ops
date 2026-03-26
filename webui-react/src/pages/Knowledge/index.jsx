 /**
 * Knowledge 页面 - 知识库管理
 * Reference: D-Bot Paper Section 4 - Offline Preparation
 * 支持五大类文件上传：知识类、数据类、日志类、配置类、代码类
 * 更新时间：2026年2月
 * 
 * 知识文件位置：
 * - doc2knowledge/docs/ - 知识文档目录
 * - doc2knowledge/uploaded/ - 上传的文档
 * - knowledge_base/ - 向量库存储
 */
import React, { useState, useEffect } from 'react';
import {
  Row, Col, Card, Table, Button, Modal, Upload, message,
  Input, Space, Tag, Popconfirm, Empty, Spin, Divider, Alert, Statistic
} from 'antd';
import {
  BookOutlined, PlusOutlined, DeleteOutlined, UploadOutlined,
  FolderOutlined, FileOutlined, ReloadOutlined, FileTextOutlined,
  FilePdfOutlined, FileExcelOutlined, CodeOutlined, SettingOutlined,
  DatabaseOutlined, CheckCircleOutlined, ClockCircleOutlined, SyncOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Search } = Input;
const { Dragger } = Upload;

// 北京时间格式化函数
const formatBeijingTime = (date) => {
  if (!date) return '-';
  try {
    let d;
    // 处理时间戳（秒或毫秒）
    if (typeof date === 'number') {
      // 如果是秒级时间戳（小于 1e12），转换为毫秒
      d = new Date(date < 1e12 ? date * 1000 : date);
    } else if (typeof date === 'string') {
      // 处理 ISO 格式或其他字符串格式
      d = new Date(date);
    } else {
      d = new Date(date);
    }
    
    // 检查日期是否有效
    if (isNaN(d.getTime())) {
      return String(date);
    }
    
    // 使用北京时间显示
    const options = {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    };
    return d.toLocaleString('zh-CN', options).replace(/\//g, '-');
  } catch {
    return String(date);
  }
};

const formatBeijingDate = (date) => {
  if (!date) return '-';
  try {
    const d = new Date(date);
    const options = {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    };
    return d.toLocaleDateString('zh-CN', options).replace(/\//g, '-');
  } catch {
    return String(date);
  }
};

// 支持的文件类型配置 - 与后端 LOADER_DICT 保持一致
const FILE_TYPE_CONFIG = {
  knowledge: {
    name: '知识类',
    icon: <BookOutlined />,
    color: '#1890ff',
    extensions: ['.jsonl', '.json', '.pdf', '.docx', '.doc', '.md', '.markdown', '.txt', '.text', '.html', '.htm'],
    description: '排查手册、技术文档'
  },
  data: {
    name: '数据类',
    icon: <FileExcelOutlined />,
    color: '#52c41a',
    extensions: ['.csv', '.xlsx', '.xls', '.tsv'],
    description: '历史监控指标、慢查询统计'
  },
  log: {
    name: '日志类',
    icon: <FileTextOutlined />,
    color: '#faad14',
    extensions: ['.log', '.out'],
    description: '数据库运行日志、错误堆栈'
  },
  config: {
    name: '配置类',
    icon: <SettingOutlined />,
    color: '#722ed1',
    extensions: ['.yaml', '.yml', '.conf', '.cfg', '.ini', '.env', '.properties', '.toml', '.xml'],
    description: '数据库参数配置'
  },
  code: {
    name: '代码类',
    icon: <CodeOutlined />,
    color: '#eb2f96',
    extensions: ['.sql', '.py', '.sh', '.bash', '.bat', '.ps1', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.go', '.rs', '.rb', '.php'],
    description: 'SQL脚本、存储过程'
  },
  other: {
    name: '其他',
    icon: <FileOutlined />,
    color: '#8c8c8c',
    extensions: ['.ppt', '.pptx', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.eml', '.msg', '.epub', '.ipynb', '.odt', '.rst', '.rtf', '.srt'],
    description: '演示文稿、图片等'
  }
};

// 所有支持的文件扩展名
const ALL_SUPPORTED_EXTENSIONS = Object.values(FILE_TYPE_CONFIG)
  .flatMap(config => config.extensions);

const Knowledge = () => {
  const [loading, setLoading] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [uploadModalVisible, setUploadModalVisible] = useState(false);
  const [newKbName, setNewKbName] = useState('');
  const [newKbInfo, setNewKbInfo] = useState('');
  const [selectedKb, setSelectedKb] = useState(null);
  const [fileList, setFileList] = useState([]);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [detailFiles, setDetailFiles] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    fetchKnowledgeBases();
  }, []);

  const fetchKnowledgeBases = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/knowledge_base/list_knowledge_bases').catch(() => null);
      console.log('Knowledge bases API response:', res?.data);
      
      // 获取实际数据数组
      let rawData = [];
      if (res?.data?.data && Array.isArray(res.data.data)) {
        rawData = res.data.data;
      } else if (res?.data && Array.isArray(res.data)) {
        rawData = res.data;
      }
      
      // 转换后端数据格式
      if (rawData.length > 0) {
        const formattedData = rawData.map((kb, index) => {
          const fileCount = kb.file_count ?? kb.doc_count ?? 0;
          const updateTime = kb.update_time || kb.create_time;
          const displayTime = updateTime ? formatBeijingTime(updateTime) : formatBeijingTime(new Date());
          return {
            id: index + 1,
            name: kb.kb_name || kb.name || '未命名知识库',
            doc_count: fileCount,
            created_at: displayTime,
            status: fileCount > 0 ? 'ready' : 'empty',
            kb_info: kb.kb_info || kb.info || '',
            vs_type: kb.vs_type || 'faiss',
            embed_model: kb.embed_model || 'text2vec-base-chinese',
            is_empty: fileCount === 0
          };
        });
        setKnowledgeBases(formattedData);
      } else {
        setKnowledgeBases([]);
      }
    } catch (error) {
      console.error('获取知识库列表失败:', error);
      setKnowledgeBases([]);
    } finally {
      setLoading(false);
    }
  };

  const [nameRuleModalVisible, setNameRuleModalVisible] = useState(false);

  const showNameRuleModal = (reason) => {
    Modal.warning({
      title: '知识库名称规则',
      content: (
        <div style={{ color: '#333' }}>
          <p style={{ marginBottom: 12 }}>{reason}</p>
          <div style={{ 
            background: '#f5f5f5', 
            padding: 12, 
            borderRadius: 6,
            fontSize: 13
          }}>
            <p style={{ fontWeight: 600, marginBottom: 8 }}>命名规则：</p>
            <ul style={{ marginBottom: 12, paddingLeft: 20 }}>
              <li>长度：3-63 个字符</li>
              <li>必须以字母或数字开头</li>
              <li>必须以字母或数字结尾</li>
              <li>只能包含：字母、数字、下划线(_)、连字符(-)</li>
            </ul>
            <p style={{ fontWeight: 600, marginBottom: 8 }}>正确示例：</p>
            <ul style={{ marginBottom: 0, paddingLeft: 20, color: '#52c41a' }}>
              <li><code>my_knowledge_base</code></li>
              <li><code>test-kb-2024</code></li>
              <li><code>PostgreSQLDocs</code></li>
              <li><code>db_diagnosis_v1</code></li>
            </ul>
            <p style={{ fontWeight: 600, marginTop: 12, marginBottom: 8, color: '#ff4d4f' }}>错误示例：</p>
            <ul style={{ marginBottom: 0, paddingLeft: 20, color: '#ff4d4f' }}>
              <li><code>测试库</code> - 不支持中文</li>
              <li><code>ab</code> - 少于3个字符</li>
              <li><code>-test</code> - 不能以连字符开头</li>
              <li><code>test_</code> - 不能以下划线结尾</li>
            </ul>
          </div>
        </div>
      ),
      width: 500,
    });
  };

  const createKnowledgeBase = async () => {
    if (!newKbName.trim()) {
      message.warning('请输入知识库名称');
      return;
    }
    
    const name = newKbName.trim();
    
    if (name.length < 3 || name.length > 63) {
      showNameRuleModal(`您输入的名称 "${name}" 长度不符合要求（${name.length}个字符）`);
      return;
    }
    if (!/^[a-zA-Z0-9]/.test(name)) {
      showNameRuleModal(`您输入的名称 "${name}" 必须以字母或数字开头`);
      return;
    }
    if (!/[a-zA-Z0-9]$/.test(name)) {
      showNameRuleModal(`您输入的名称 "${name}" 必须以字母或数字结尾`);
      return;
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
      showNameRuleModal(`您输入的名称 "${name}" 包含了不允许的字符`);
      return;
    }
    
    const existingKb = knowledgeBases.find(kb => kb.name.toLowerCase() === name.toLowerCase());
    if (existingKb) {
      message.error(`知识库 "${name}" 已存在，请使用其他名称`);
      return;
    }
    
    const hideLoading = message.loading({ content: '正在创建知识库...', key: 'create_kb', duration: 0 });
    
    try {
      const response = await axios.post('/knowledge_base/create_knowledge_base', { 
        knowledge_base_name: newKbName,
        info: newKbInfo || ''
      });
      
      hideLoading();
      
      if (response.data?.msg?.includes('已存在')) {
        message.warning(response.data.msg);
      } else {
        message.success({ content: '知识库创建成功！', key: 'create_kb' });
        setModalVisible(false);
        setNewKbName('');
        setNewKbInfo('');
        await fetchKnowledgeBases();
      }
    } catch (error) {
      hideLoading();
      const errorMsg = error.response?.data?.msg || error.message;
      if (errorMsg.includes('已存在') || errorMsg.includes('already exists')) {
        message.warning('知识库已存在，请使用其他名称');
      } else {
        message.error({ content: '知识库创建失败: ' + errorMsg, key: 'create_kb' });
      }
    }
  };

  const deleteKnowledgeBase = async (record) => {
    const hideLoading = message.loading({ content: `正在删除知识库 "${record.name}"...`, key: 'delete_kb', duration: 0 });
    try {
      await axios.post('/knowledge_base/delete_knowledge_base', { 
        knowledge_base_name: record.name 
      }, { timeout: 120000 });
      hideLoading();
      message.success({ content: '知识库删除成功！', key: 'delete_kb' });
      await fetchKnowledgeBases();
    } catch (error) {
      hideLoading();
      message.error({ content: '知识库删除失败: ' + (error.response?.data?.msg || error.message), key: 'delete_kb' });
    }
  };

  const handleUpload = async () => {
    if (fileList.length === 0) {
      message.warning('请选择要上传的文件');
      return;
    }

    const formData = new FormData();
    fileList.forEach(file => {
      formData.append('files', file);
    });
    formData.append('knowledge_base_name', selectedKb?.name || 'default');
    formData.append('override', 'true');  // 覆盖已存在的文件
    formData.append('to_vector_store', 'true');  // 添加到向量库

    try {
      message.loading({ content: `正在上传 ${fileList.length} 个文件并建立索引...`, key: 'upload', duration: 0 });
      const res = await axios.post('/knowledge_base/upload_docs', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 300000  // 5分钟超时
      });
      message.destroy('upload');
      
      // 检查是否有失败的文件
      const failedFiles = res.data?.data?.failed_files || {};
      const failedCount = Object.keys(failedFiles).length;
      const successCount = fileList.length - failedCount;
      
      if (failedCount > 0) {
        message.warning(`成功上传 ${successCount} 个文件，${failedCount} 个失败`);
        console.log('失败的文件:', failedFiles);
      } else {
        message.success(`成功上传 ${fileList.length} 个文件`);
      }
      
      setUploadModalVisible(false);
      setFileList([]);
      // 延迟刷新，等待后端处理完成
      setTimeout(() => {
        fetchKnowledgeBases();
      }, 1000);
    } catch (error) {
      message.destroy('upload');
      message.error('上传失败: ' + (error.response?.data?.msg || error.message));
    }
  };

  const openDetailModal = async (record) => {
    setSelectedKb(record);
    setDetailLoading(true);
    setDetailModalVisible(true);
    
    try {
      const res = await axios.get(`/knowledge_base/kb_file_details?knowledge_base_name=${record.name}`);
      const files = res.data?.data || [];
      setDetailFiles(Array.isArray(files) ? files : []);
    } catch (error) {
      console.error('获取文件列表失败:', error);
      setDetailFiles([]);
    } finally {
      setDetailLoading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes || bytes === '-') return '-';
    const size = parseInt(bytes);
    if (isNaN(size) || size === 0) return '-';
    if (size < 1024) return size + ' B';
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
    if (size < 1024 * 1024 * 1024) return (size / (1024 * 1024)).toFixed(1) + ' MB';
    return (size / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  };

  const getFileStatusTag = (file) => {
    const inDb = file.in_db === true;
    const inFolder = file.in_folder === true;
    
    if (inDb && inFolder) {
      return (
        <Tag style={{ 
          background: 'rgba(82, 196, 26, 0.15)', 
          border: '1px solid rgba(82, 196, 26, 0.4)',
          color: '#52c41a'
        }}>
          <CheckCircleOutlined style={{ marginRight: 4 }} />
          已入库
        </Tag>
      );
    } else if (inFolder && !inDb) {
      return (
        <Tag style={{ 
          background: 'rgba(250, 173, 20, 0.15)', 
          border: '1px solid rgba(250, 173, 20, 0.4)',
          color: '#faad14'
        }}>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          待入库
        </Tag>
      );
    } else if (!inFolder && inDb) {
      return (
        <Tag style={{ 
          background: 'rgba(255, 77, 79, 0.15)', 
          border: '1px solid rgba(255, 77, 79, 0.4)',
          color: '#ff4d4f'
        }}>
          文件丢失
        </Tag>
      );
    }
    return null;
  };

  const handleDownloadFile = (fileName) => {
    if (!selectedKb?.name || !fileName) return;
    // 提取纯文件名（去掉路径）
    const pureFileName = fileName.split(/[/\\]/).pop();
    // 使用后端的下载接口
    const downloadUrl = `/knowledge_base/download_doc?knowledge_base_name=${encodeURIComponent(selectedKb.name)}&file_name=${encodeURIComponent(pureFileName)}`;
    window.open(downloadUrl, '_blank');
  };

  const handleDeleteFile = async (fileName) => {
    if (!selectedKb?.name || !fileName) return;
    // 提取纯文件名（去掉路径）
    const pureFileName = fileName.split(/[/\\]/).pop();
    
    try {
      const res = await axios.post('/knowledge_base/delete_docs', {
        knowledge_base_name: selectedKb.name,
        file_names: [pureFileName],
        delete_content: true
      });
      
      if (res.data?.code === 200) {
        message.success('文件删除成功');
        // 刷新文件列表
        const detailRes = await axios.get(`/knowledge_base/kb_file_details?knowledge_base_name=${selectedKb.name}`);
        setDetailFiles(detailRes.data?.data || []);
        // 刷新知识库列表
        fetchKnowledgeBases();
      } else {
        message.error('删除失败: ' + (res.data?.msg || '未知错误'));
      }
    } catch (error) {
      message.error('删除失败: ' + (error.response?.data?.msg || error.message));
    }
  };

  const [indexingFiles, setIndexingFiles] = useState({});

  const handleIndexFile = async (fileName, isReindex = false) => {
    if (!selectedKb?.name || !fileName) return;
    const pureFileName = fileName.split(/[/\\]/).pop();
    
    setIndexingFiles(prev => ({ ...prev, [pureFileName]: true }));
    
    const actionText = isReindex ? '重新入库' : '入库';
    message.loading({ content: `正在${actionText}文件: ${pureFileName}...`, key: 'indexFile', duration: 0 });
    
    try {
      const res = await axios.post('/knowledge_base/update_docs', {
        knowledge_base_name: selectedKb.name,
        file_names: [pureFileName],
        chunk_size: 500,
        chunk_overlap: 50,
        zh_title_enhance: false,
        override_custom_docs: false,
        docs: {},
        not_refresh_vs_cache: false
      });
      
      if (res.data?.code === 200) {
        const failedFiles = res.data?.data?.failed_files || {};
        if (failedFiles[pureFileName]) {
          message.error({ content: `${actionText}失败: ${failedFiles[pureFileName]}`, key: 'indexFile' });
        } else {
          message.success({ content: `文件${actionText}成功: ${pureFileName}`, key: 'indexFile' });
          const detailRes = await axios.get(`/knowledge_base/kb_file_details?knowledge_base_name=${selectedKb.name}`);
          setDetailFiles(detailRes.data?.data || []);
          fetchKnowledgeBases();
        }
      } else {
        message.error({ content: `${actionText}失败: ${res.data?.msg || '未知错误'}`, key: 'indexFile' });
      }
    } catch (error) {
      message.error({ content: `${actionText}失败: ${error.response?.data?.msg || error.message}`, key: 'indexFile' });
    } finally {
      setIndexingFiles(prev => {
        const newState = { ...prev };
        delete newState[pureFileName];
        return newState;
      });
    }
  };

  const openUploadModal = (record) => {
    if (!record || !record.name || record.name === 'default') {
      if (knowledgeBases.length === 0) {
        message.warning('请先创建知识库再上传文件');
        return;
      }
      record = knowledgeBases[0];
    }
    setSelectedKb(record);
    setFileList([]);
    setUploadModalVisible(true);
  };

  const uploadProps = {
    multiple: true,
    fileList,
    beforeUpload: (file) => {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (!ALL_SUPPORTED_EXTENSIONS.includes(ext)) {
        message.error(`不支持的文件类型: ${ext}`);
        return Upload.LIST_IGNORE;
      }
      setFileList([...fileList, file]);
      return false;
    },
    onRemove: (file) => {
      setFileList(fileList.filter(f => f.uid !== file.uid));
    }
  };

  // 统计信息 - 使用转换后的 doc_count 字段
  const totalDocs = knowledgeBases.reduce((sum, kb) => sum + (kb.doc_count ?? 0), 0);
  const readyCount = knowledgeBases.filter(kb => kb.status === 'ready').length;

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
      render: (id) => <span style={{ color: '#00d4ff', fontWeight: 'bold' }}>{id}</span>
    },
    {
      title: '知识库名称',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (name, record) => (
        <span>
          <FolderOutlined style={{ marginRight: '8px', color: '#faad14' }} />
          <span style={{ fontWeight: 600 }}>{name}</span>
          {record.kb_info && (
            <span style={{ marginLeft: '8px', color: '#8c8c8c', fontSize: '12px' }}>
              ({record.kb_info})
            </span>
          )}
        </span>
      )
    },
    {
      title: '是否为空',
      dataIndex: 'is_empty',
      key: 'is_empty',
      width: 100,
      render: (isEmpty) => (
        <Tag 
          style={{ 
            background: isEmpty ? 'rgba(250, 173, 20, 0.2)' : 'rgba(82, 196, 26, 0.2)',
            border: `1px solid ${isEmpty ? '#faad14' : '#52c41a'}`,
            color: isEmpty ? '#faad14' : '#52c41a'
          }} 
          icon={isEmpty ? null : <CheckCircleOutlined />}
        >
          {isEmpty ? '空' : '有数据'}
        </Tag>
      )
    },
    {
      title: '文档数量',
      dataIndex: 'doc_count',
      key: 'doc_count',
      width: 110,
      render: (count) => (
        <span style={{ fontWeight: 'bold', color: count > 0 ? '#52c41a' : '#faad14' }}>
          <FileOutlined style={{ marginRight: 4 }} />
          {count} 个
        </span>
      )
    },
    {
      title: '向量类型',
      dataIndex: 'vs_type',
      key: 'vs_type',
      width: 100,
      render: (type) => (
        <Tag 
          style={{ 
            background: 'rgba(114, 46, 209, 0.2)',
            border: '1px solid #722ed1',
            color: '#722ed1'
          }}
        >
          <DatabaseOutlined style={{ marginRight: 4 }} />
          {type || 'faiss'}
        </Tag>
      )
    },
    {
      title: '嵌入模型',
      dataIndex: 'embed_model',
      key: 'embed_model',
      width: 160,
      render: (model) => (
        <span style={{ color: '#8c8c8c', fontSize: '12px' }}>{model}</span>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status) => {
        const statusMap = {
          ready: { bg: 'rgba(82, 196, 26, 0.2)', border: '#52c41a', color: '#52c41a', text: '就绪', icon: <CheckCircleOutlined /> },
          empty: { bg: 'rgba(250, 173, 20, 0.2)', border: '#faad14', color: '#faad14', text: '空', icon: <ClockCircleOutlined /> },
          indexing: { bg: 'rgba(24, 144, 255, 0.2)', border: '#1890ff', color: '#1890ff', text: '索引中' },
          error: { bg: 'rgba(255, 77, 79, 0.2)', border: '#ff4d4f', color: '#ff4d4f', text: '错误' }
        };
        const config = statusMap[status] || { bg: 'rgba(140, 140, 140, 0.2)', border: '#8c8c8c', color: '#8c8c8c', text: status };
        return (
          <Tag 
            style={{ 
              background: config.bg,
              border: `1px solid ${config.border}`,
              color: config.color
            }} 
            icon={config.icon}
          >
            {config.text}
          </Tag>
        );
      }
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
      render: (time) => (
        <span style={{ color: '#8c8c8c' }}>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          {time}
        </span>
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button 
            type="link" 
            style={{ color: '#00d4ff' }}
            onClick={() => openDetailModal(record)}
          >
            查看
          </Button>
          <Button 
            type="link" 
            icon={<UploadOutlined />} 
            style={{ color: '#52c41a' }} 
            onClick={() => openUploadModal(record)}
          >
            上传
          </Button>
          <Popconfirm 
            title="确定删除此知识库？" 
            okText="确定" 
            cancelText="取消"
            onConfirm={() => deleteKnowledgeBase(record)}
          >
            <Button type="link" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <div className="knowledge-page" style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', marginBottom: '8px' }}>
          <BookOutlined /> 知识库管理
        </h1>
        <p style={{ color: '#8c8c8c' }}>
          更新时间：{knowledgeBases.length > 0 ? knowledgeBases.reduce((latest, kb) => {
            const kbTime = new Date(kb.created_at.replace(/-/g, '/'));
            return kbTime > latest ? kbTime : latest;
          }, new Date(0)).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).replace(/\//g, '-') : formatBeijingTime(new Date())}
        </p>
      </div>

      {/* 知识文件位置说明 */}
      <Alert
        message="知识文件位置"
        description={
          <div>
            <p><strong>项目中的知识文件目录：</strong></p>
            <ul style={{ marginBottom: 0 }}>
              <li><code>doc2knowledge/</code> - 知识文档根目录</li>
              <li><code>doc2knowledge/docs/db_expert_kb/raw/</code> - 数据库专家手册（19个原始文档）</li>
              <li><code>doc2knowledge/root_causes_dbmind.jsonl</code> - 根因诊断知识库</li>
              <li><code>doc2knowledge/Final_Master_Knowledge_Base.md</code> - 综合专家知识库</li>
              <li><code>doc2knowledge/ALL_KNOWLEDGE_COMBINED.md</code> - 汇总知识文件</li>
              <li><code>knowledge_base/{'{知识库名称}'}/content/</code> - 上传文件存储目录</li>
            </ul>
          </div>
        }
        type="info"
        showIcon
        style={{ marginBottom: '16px' }}
      />

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: '24px' }}>
        <Col span={6}>
          <Card bordered={false} style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
            <Statistic 
              title={<span style={{ color: 'rgba(255,255,255,0.8)' }}>知识库总数</span>} 
              value={knowledgeBases.length} 
              prefix={<DatabaseOutlined />}
              valueStyle={{ color: '#fff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false} style={{ background: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)' }}>
            <Statistic 
              title={<span style={{ color: 'rgba(255,255,255,0.8)' }}>文档总数</span>} 
              value={totalDocs} 
              prefix={<FileOutlined />}
              valueStyle={{ color: '#fff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false} style={{ background: 'linear-gradient(135deg, #ee0979 0%, #ff6a00 100%)' }}>
            <Statistic 
              title={<span style={{ color: 'rgba(255,255,255,0.8)' }}>就绪知识库</span>} 
              value={readyCount} 
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#fff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false} style={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)' }}>
            <Statistic 
              title={<span style={{ color: 'rgba(255,255,255,0.8)' }}>向量类型</span>} 
              value={'FAISS/Chroma'} 
              prefix={<DatabaseOutlined />}
              valueStyle={{ color: '#fff', fontSize: '18px' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 支持的文件类型说明 */}
      <Alert
        message="支持的文件类型"
        description={
          <Row gutter={[16, 8]}>
            {Object.entries(FILE_TYPE_CONFIG).map(([key, config]) => (
              <Col span={8} key={key}>
                <Space>
                  <span style={{ color: config.color, fontSize: '16px' }}>{config.icon}</span>
                  <span style={{ fontWeight: 600 }}>{config.name}:</span>
                  <span style={{ color: '#8c8c8c' }}>
                    {config.extensions.join(', ')} - {config.description}
                  </span>
                </Space>
              </Col>
            ))}
          </Row>
        }
        type="info"
        showIcon
        style={{ marginBottom: '16px' }}
      />

      <Card bordered={false}>
        <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
          <Space>
            <Search placeholder="搜索知识库" style={{ width: 250 }} />
            <Button icon={<ReloadOutlined />} onClick={fetchKnowledgeBases}>刷新</Button>
          </Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setModalVisible(true)}
          >
            新建知识库
          </Button>
        </div>

        <Spin spinning={loading}>
          {knowledgeBases.length > 0 ? (
            <Table
              dataSource={knowledgeBases}
              columns={columns}
              rowKey="id"
              pagination={{ pageSize: 10 }}
              scroll={{ x: 1300 }}
            />
          ) : (
            <Empty description="暂无知识库，请点击【新建知识库】创建或上传文档" />
          )}
        </Spin>
      </Card>

      {/* 新建知识库弹窗 */}
      <Modal
        title="新建知识库"
        open={modalVisible}
        onOk={createKnowledgeBase}
        onCancel={() => setModalVisible(false)}
        okText="创建"
        cancelText="取消"
      >
        <div style={{ marginBottom: '16px' }}>
          <Input
            placeholder="请输入知识库名称（3-63字符，字母数字开头结尾）"
            value={newKbName}
            onChange={(e) => setNewKbName(e.target.value)}
            prefix={<FolderOutlined />}
          />
          <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>
            只能包含字母、数字、下划线(_)和连字符(-)
          </div>
        </div>
        <div>
          <Input.TextArea
            placeholder="请输入知识库描述（可选）"
            value={newKbInfo}
            onChange={(e) => setNewKbInfo(e.target.value)}
            rows={3}
          />
        </div>
      </Modal>

      {/* 查看知识库详情弹窗 */}
      <Modal
        title={
          <span>
            <FolderOutlined style={{ marginRight: 8, color: '#faad14' }} />
            知识库详情: {selectedKb?.name}
          </span>
        }
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={700}
      >
        <Spin spinning={detailLoading}>
          {detailFiles.length > 0 ? (
            <div>
              <div style={{ marginBottom: 16 }}>
                <Tag style={{ 
                  background: 'rgba(24, 144, 255, 0.15)', 
                  border: '1px solid rgba(24, 144, 255, 0.4)',
                  color: '#69c0ff'
                }}>共 {detailFiles.length} 个文件</Tag>
              </div>
              <Table
                dataSource={detailFiles.map((file, index) => {
                  const rawName = file.file_name || file.name || '未知';
                  const pureName = rawName.split(/[/\\]/).pop();
                  return {
                    key: index,
                    name: pureName,
                    rawName: rawName,
                    size: file.file_size || '-',
                    time: file.create_time || file.file_mtime || '-',
                    ext: file.file_ext || '',
                    in_db: file.in_db,
                    in_folder: file.in_folder,
                    file: file
                  };
                })}
                columns={[
                  { 
                    title: '文件名', 
                    dataIndex: 'name', 
                    key: 'name',
                    render: (name, record) => (
                      <a 
                        onClick={() => handleDownloadFile(record.rawName)}
                        style={{ color: '#69c0ff', cursor: 'pointer' }}
                        title="点击下载文件"
                      >
                        <FileOutlined style={{ marginRight: 8, color: '#1890ff' }} />
                        {name}
                      </a>
                    )
                  },
                  { 
                    title: '大小', 
                    dataIndex: 'size', 
                    key: 'size', 
                    width: 100,
                    render: (size) => formatFileSize(size)
                  },
                  { 
                    title: '状态', 
                    key: 'status', 
                    width: 100,
                    render: (_, record) => getFileStatusTag(record.file)
                  },
                  { 
                    title: '上传时间', 
                    dataIndex: 'time', 
                    key: 'time', 
                    width: 160,
                    render: (time) => formatBeijingTime(time)
                  },
                  {
                    title: '操作',
                    key: 'action',
                    width: 160,
                    render: (_, record) => {
                      const inDb = record.in_db === true;
                      const inFolder = record.in_folder === true;
                      const isIndexing = indexingFiles[record.name];
                      
                      return (
                        <Space size="small">
                          {(inFolder && !inDb) && (
                            <Button 
                              type="link" 
                              size="small" 
                              icon={<SyncOutlined spin={isIndexing} />}
                              disabled={isIndexing}
                              onClick={() => handleIndexFile(record.rawName, false)}
                              style={{ color: '#52c41a' }}
                            >
                              {isIndexing ? '入库中...' : '入库'}
                            </Button>
                          )}
                          {(inFolder && inDb) && (
                            <Button 
                              type="link" 
                              size="small" 
                              icon={<SyncOutlined spin={isIndexing} />}
                              disabled={isIndexing}
                              onClick={() => handleIndexFile(record.rawName, true)}
                              style={{ color: '#1890ff' }}
                            >
                              {isIndexing ? '入库中...' : '重新入库'}
                            </Button>
                          )}
                          <Popconfirm 
                            title="确定删除此文件？" 
                            okText="确定" 
                            cancelText="取消"
                            onConfirm={() => handleDeleteFile(record.rawName)}
                          >
                            <Button type="link" danger size="small" icon={<DeleteOutlined />}>
                              删除
                            </Button>
                          </Popconfirm>
                        </Space>
                      );
                    }
                  }
                ]}
                pagination={{ pageSize: 10 }}
                size="small"
              />
            </div>
          ) : (
            <Empty description="该知识库暂无文件" />
          )}
        </Spin>
      </Modal>

      {/* 上传文件弹窗 */}
      <Modal
        title={`上传文件到: ${selectedKb?.name || '默认知识库'}`}
        open={uploadModalVisible}
        onOk={handleUpload}
        onCancel={() => setUploadModalVisible(false)}
        okText="上传"
        cancelText="取消"
        width={700}
      >
        <div style={{ marginBottom: '16px' }}>
          <Divider orientation="left">支持的文件类型</Divider>
          <Row gutter={[8, 8]}>
            {Object.entries(FILE_TYPE_CONFIG).map(([key, config]) => (
              <Col span={12} key={key}>
                <Tag color={config.color} style={{ margin: '4px' }}>
                  {config.icon} {config.name}
                </Tag>
                <span style={{ fontSize: '12px', color: '#8c8c8c' }}>
                  {config.extensions.join(', ')}
                </span>
              </Col>
            ))}
          </Row>
        </div>

        <Divider orientation="left">上传区域</Divider>
        <Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <UploadOutlined style={{ color: '#1890ff', fontSize: '48px' }} />
          </p>
          <p className="ant-upload-text" style={{ fontSize: '16px' }}>点击或拖拽文件到此区域上传</p>
          <p className="ant-upload-hint" style={{ color: '#8c8c8c' }}>
            支持知识类(.jsonl, .pdf, .docx)、数据类(.csv, .xlsx)、日志类(.log, .txt)、
            配置类(.yaml, .conf)、代码类(.sql) 等多种格式
          </p>
        </Dragger>

        {fileList.length > 0 && (
          <div style={{ marginTop: '16px' }}>
            <strong>已选择 {fileList.length} 个文件:</strong>
            <ul style={{ marginTop: '8px', maxHeight: '150px', overflow: 'auto', paddingLeft: '20px' }}>
              {fileList.map((file, index) => (
                <li key={index}>
                  <FileOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
                  {file.name}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Knowledge;