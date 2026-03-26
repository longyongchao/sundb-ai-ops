/**
 * DiagnosisHeatMap - 指标相关性热力图（毕设亮点）
 * Reference: D-Bot Paper Section 5.1 - Knowledge Retrieval
 * 用于展示数据库指标之间的相关性矩阵，辅助根因分析
 */
import React from 'react';
import ReactECharts from 'echarts-for-react';

const DiagnosisHeatMap = ({ 
  data = null, 
  title = '指标相关性热力图',
  height = 400 
}) => {
  // Mock 数据 - 当后端未就绪时使用
  // Reference: D-Bot Paper - 指标相关性分析用于根因定位
  const defaultMetrics = [
    'CPU使用率', '内存使用率', '磁盘I/O', '网络流量', 
    '查询响应时间', '连接数', '锁等待', '事务数'
  ];

  // 相关性矩阵 (模拟数据，值范围 -1 到 1)
  const defaultCorrelationMatrix = [
    [1.0, 0.85, 0.72, 0.45, 0.92, 0.68, 0.55, 0.78],   // CPU
    [0.85, 1.0, 0.65, 0.38, 0.75, 0.72, 0.48, 0.65],   // 内存
    [0.72, 0.65, 1.0, 0.52, 0.82, 0.55, 0.68, 0.58],   // 磁盘I/O
    [0.45, 0.38, 0.52, 1.0, 0.42, 0.35, 0.28, 0.45],   // 网络
    [0.92, 0.75, 0.82, 0.42, 1.0, 0.72, 0.85, 0.88],   // 查询响应
    [0.68, 0.72, 0.55, 0.35, 0.72, 1.0, 0.62, 0.75],   // 连接数
    [0.55, 0.48, 0.68, 0.28, 0.85, 0.62, 1.0, 0.58],   // 锁等待
    [0.78, 0.65, 0.58, 0.45, 0.88, 0.75, 0.58, 1.0]    // 事务数
  ];

  const metrics = data?.metrics || defaultMetrics;
  const correlationMatrix = data?.correlation_matrix || defaultCorrelationMatrix;

  // 将矩阵转换为 ECharts 需要的格式 [x, y, value]
  const heatmapData = [];
  correlationMatrix.forEach((row, y) => {
    row.forEach((value, x) => {
      heatmapData.push([x, y, value]);
    });
  });

  const option = {
    title: {
      text: title,
      left: 'center',
      textStyle: {
        color: '#1890ff',
        fontSize: 16
      }
    },
    tooltip: {
      position: 'top',
      backgroundColor: 'rgba(20, 25, 38, 0.9)',
      borderColor: '#333',
      borderWidth: 1,
      textStyle: {
        color: '#ffffff',
        fontSize: 12
      },
      formatter: function (params) {
        if (!params || !params.data) return '';
        const xMetric = metrics[params.data[0]];
        const yMetric = metrics[params.data[1]];
        const value = params.data[2];
        const correlationType = value > 0.5 ? '强正相关' : value > 0 ? '弱正相关' : value < -0.5 ? '强负相关' : '弱负相关';
        const color = value > 0.5 ? '#ff4d4f' : value > 0 ? '#faad14' : value < -0.5 ? '#1890ff' : '#52c41a';
        return `<div style="padding: 4px;">
          <div style="font-weight: bold; margin-bottom: 6px;">${xMetric} ↔ ${yMetric}</div>
          <div style="display: flex; justify-content: space-between; gap: 20px;">
            <span>相关性系数:</span>
            <span style="color: ${color}; font-weight: bold;">${value.toFixed(2)}</span>
          </div>
          <div style="display: flex; justify-content: space-between; gap: 20px;">
            <span>相关类型:</span>
            <span style="color: ${color};">${correlationType}</span>
          </div>
        </div>`;
      }
    },
    grid: {
      left: '15%',
      right: '10%',
      bottom: '20%',
      top: '15%'
    },
    xAxis: {
      type: 'category',
      data: metrics,
      splitArea: { show: true },
      axisLabel: {
        rotate: 45,
        fontSize: 10
      }
    },
    yAxis: {
      type: 'category',
      data: metrics,
      splitArea: { show: true }
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '0',
      inRange: {
        color: ['#1890ff', '#f0f4f8', '#ff4d4f']
      },
      text: ['强正相关', '强负相关'],
      textStyle: {
        color: '#ffffff'
      }
    },
    toolbox: {
      feature: {
        saveAsImage: { title: '保存图片' },
        dataView: { title: '数据视图', readOnly: true }
      }
    },
    series: [{
      name: '相关性',
      type: 'heatmap',
      data: heatmapData,
      label: {
        show: true,
        formatter: function (params) {
          return params.data[2].toFixed(2);
        },
        fontSize: 9
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      }
    }]
  };

  return (
    <div>
      <ReactECharts
        option={option}
        style={{ height: `${height}px`, width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
      <div style={{ 
        textAlign: 'center', 
        color: '#8c8c8c', 
        fontSize: '12px',
        marginTop: '8px' 
      }}>
        * 颜色越深表示相关性越强，红色为正相关，蓝色为负相关
      </div>
    </div>
  );
};

export default DiagnosisHeatMap;