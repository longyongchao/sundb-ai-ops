/**
 * MetricBarChart - 指标柱状图
 * 用于展示数据库指标的柱状对比
 */
import React from 'react';
import ReactECharts from 'echarts-for-react';

const MetricBarChart = ({ 
  data = null, 
  title = '数据库指标对比',
  height = 300 
}) => {
  const defaultData = {
    categories: ['CPU', '内存', '磁盘I/O', '网络', '连接数', '查询数'],
    values: [75, 82, 45, 30, 120, 85]
  };

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
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      top: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: chartData.categories
    },
    yAxis: {
      type: 'value'
    },
    toolbox: {
      feature: {
        saveAsImage: { title: '保存图片' }
      }
    },
    series: [{
      name: '指标值',
      type: 'bar',
      data: chartData.values,
      itemStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: '#1890ff' },
            { offset: 1, color: '#69c0ff' }
          ]
        },
        borderRadius: [4, 4, 0, 0]
      },
      label: {
        show: true,
        position: 'top',
        color: '#666'
      }
    }]
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: `${height}px`, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
};

export default MetricBarChart;
