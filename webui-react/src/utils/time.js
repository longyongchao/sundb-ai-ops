/**
 * 时间工具函数 - 统一使用北京时间 (Asia/Shanghai, UTC+8)
 * 更新时间：2026年2月
 */

/**
 * 格式化为北京时间（年月日时分秒）
 * @param {Date|string|number} date - 日期对象、字符串或时间戳
 * @returns {string} 格式化后的北京时间，如 "2026-02-11 12:05:30"
 */
export const formatBeijingTime = (date) => {
  if (!date) return '-';
  try {
    const d = new Date(date);
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

/**
 * 格式化为北京时间日期（年月日）
 * @param {Date|string|number} date - 日期对象、字符串或时间戳
 * @returns {string} 格式化后的日期，如 "2026-02-11"
 */
export const formatBeijingDate = (date) => {
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

/**
 * 获取当前北京时间字符串
 * @returns {string} 当前北京时间，如 "2026-02-11 12:05:30"
 */
export const getCurrentBeijingTime = () => {
  return formatBeijingTime(new Date());
};

/**
 * 获取当前北京时间日期字符串
 * @returns {string} 当前日期，如 "2026-02-11"
 */
export const getCurrentBeijingDate = () => {
  return formatBeijingDate(new Date());
};

export default {
  formatBeijingTime,
  formatBeijingDate,
  getCurrentBeijingTime,
  getCurrentBeijingDate
};