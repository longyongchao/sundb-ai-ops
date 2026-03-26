/**
 * MetricLineChart - 资源波动折线图
 * Reference: D-Bot Paper Section 2.1 - Database Performance Anomalies
 * 用于展示 CPU、内存等资源指标的时间序列波动
 */
import React from 'react';
import ReactECharts from 'echarts-for-react';

const MetricLineChart = ({ 
  data = null, 
  title = '资源指标监控',
  height = 300 
}) => {
  // Mock 数据 - 当后端未就绪时使用
  const defaultData = {
    timestamps: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'],
    cpu: [45, 52, 78, 95, 88, 65, 42],
    memory: [60, 62, 75, 82, 78, 70, 65],
    disk_io: [20, 25, 45, 85, 72, 35, 22],
    network: [10, 15, 30, 55, 48, 25, 18]
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
        type: 'cross'
      },
      backgroundColor: 'rgba(20, 25, 38, 0.9)',
      borderColor: '#333',
      borderWidth: 1,
      textStyle: {
        color: '#ffffff',
        fontSize: 12
      },
      formatter: function (params) {
        if (!params || params.length === 0) return '';
        let result = `<div style="font-weight: bold; margin-bottom: 4px;">${params[0].axisValue}</div>`;
        params.forEach(item => {
          const color = item.color || '#fff';
          const value = item.value !== undefined ? item.value : '-';
          const unit = item.seriesName.includes('使用率') ? '%' : '';
          result += `<div style="display: flex; justify-content: space-between; gap: 20px;">
            <span style="color: ${color};">● ${item.seriesName}</span>
            <span style="color: #fff; font-weight: bold;">${value}${unit}</span>
          </div>`;
        });
        return result;
      }
    },
    legend: {
      data: ['CPU使用率', '内存使用率', '磁盘I/O', '网络流量'],
      bottom: 0,
      textStyle: {
        color: '#ffffff',
        fontSize: 12
      },
      itemWidth: 12,
      itemHeight: 12
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '15%',
      containLabel: true
    },
    toolbox: {
      feature: {
        saveAsImage: { title: '保存图片' },
        dataZoom: { title: { zoom: '区域缩放', back: '区域还原' } }
      }
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: chartData.timestamps
    },
    yAxis: {
      type: 'value',
      name: '使用率 (%)',
      max: 100,
      axisLabel: {
        formatter: '{value}%'
      }
    },
    series: [
      {
        name: 'CPU使用率',
        type: 'line',
        smooth: true,
        data: chartData.cpu,
        itemStyle: { color: '#ff4d4f' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(255,77,79,0.3)' },
              { offset: 1, color: 'rgba(255,77,79,0.05)' }
            ]
          }
        },
        markLine: {
          data: [{ type: 'average', name: '平均值' }],
          lineStyle: { color: '#ff4d4f' }
        },
        markPoint: {
          data: [
            { type: 'max', name: '最大值' },
            { type: 'min', name: '最小值' }
          ]
        }
      },
      {
        name: '内存使用率',
        type: 'line',
        smooth: true,
        data: chartData.memory,
        itemStyle: { color: '#52c41a' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(82,196,26,0.3)' },
              { offset: 1, color: 'rgba(82,196,26,0.05)' }
            ]
          }
        }
      },
      {
        name: '磁盘I/O',
        type: 'line',
        smooth: true,
        data: chartData.disk_io,
        itemStyle: { color: '#faad14' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(250, 173, 20, 0.3)' },
              { offset: 1, color: 'rgba(250, 173, 20, 0.05)' }
            ]
          }
        },
        markLine: {
          data: [{ type: 'average', name: '平均值' }],
          lineStyle: { color: '#faad14' }
        },
        markPoint: {
          data: [
            { type: 'max', name: '最大值' },
            { type: 'min', name: '最小值' }
          ]
        }
      },
      {
        name: '网络流量',
        type: 'line',
        smooth: true,
        data: chartData.network,
        itemStyle: { color: '#1890ff' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(24, 144, 255, 0.3)' },
              { offset: 1, color: 'rgba(24, 144, 255, 0.05)' }
            ]
          }
        },
        markLine: {
          data: [{ type: 'average', name: '平均值' }],
          lineStyle: { color: '#1890ff' }
        },
        markPoint: {
          data: [
            { type: 'max', name: '最大值' },
            { type: 'min', name: '最小值' }
          ]
        }
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

export default MetricLineChart;