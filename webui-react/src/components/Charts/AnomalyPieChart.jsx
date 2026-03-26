/**
 * AnomalyPieChart - 异常分类饼图
 * Reference: D-Bot Paper Section 2.1 - Database Performance Anomalies
 * 用于展示数据库异常类型的分布情况
 */
import React from 'react';
import ReactECharts from 'echarts-for-react';

const AnomalyPieChart = ({ 
  data = null, 
  title = '异常类型分布',
  height = 350 
}) => {
  // Mock 数据 - 当后端未就绪时使用
  // Reference: D-Bot Paper Figure 2 - 四种典型数据库性能异常
  const defaultData = [
    { value: 35, name: '慢查询执行', itemStyle: { color: '#ff4d4f' } },
    { value: 25, name: '资源耗尽', itemStyle: { color: '#faad14' } },
    { value: 20, name: '数据库挂起', itemStyle: { color: '#1890ff' } },
    { value: 15, name: '数据库崩溃', itemStyle: { color: '#722ed1' } },
    { value: 5, name: '其他异常', itemStyle: { color: '#8c8c8c' } }
  ];

  const chartData = data || defaultData;

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
      trigger: 'item',
      backgroundColor: 'rgba(30, 37, 50, 0.9)',
      borderColor: '#1f1f5',
      borderWidth: 0,
      textStyle: {
        color: '#ffffff',
        fontSize: 12
      },
      formatter: '{a} <br/>{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      top: 'middle',
      textStyle: {
        color: '#ffffff',
        fontSize: 12
      },
      itemWidth: 12,
      itemHeight: 12
    },
    toolbox: {
      feature: {
        saveAsImage: { title: '保存图片' }
      }
    },
    series: [
      {
        name: '异常类型',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['60%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: true,
          formatter: '{b}: {d}%'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 16,
            fontWeight: 'bold'
          },
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        },
        labelLine: {
          show: true
        },
        data: chartData
      }
    ]
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: `${height}px`, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
};

export default AnomalyPieChart;