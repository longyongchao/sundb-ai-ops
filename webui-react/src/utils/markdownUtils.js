export const stripMarkdown = (text) => {
  if (text === null || text === undefined) {
    return '';
  }
  
  if (typeof text !== 'string') {
    return String(text);
  }
  
  let result = text;
  
  result = result.replace(/\\n/g, '\n');
  result = result.replace(/\\r\\n/g, '\n');
  result = result.replace(/\\r/g, '\n');
  result = result.replace(/\r\n/g, '\n');
  result = result.replace(/\r/g, '\n');
  
  result = result.replace(/```[\w]*\n?([\s\S]*?)```/g, '\n$1\n');
  
  result = result.replace(/`([^`]+)`/g, '$1');
  
  result = result.replace(/\*\*([^*]+)\*\*/g, '$1');
  result = result.replace(/\*([^*]+)\*/g, '$1');
  
  result = result.replace(/^#{1,6}\s*/gm, '');
  
  result = result.replace(/^[\s]*[-*+]\s+/gm, '• ');
  result = result.replace(/^\s*\d+\.\s+/gm, '');
  
  result = result.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  
  result = result.replace(/<!--[\s\S]*?-->/g, '');
  
  result = result.replace(/\*\*/g, '');
  result = result.replace(/\*/g, '');
  result = result.replace(/`/g, '');
  result = result.replace(/#{1,6}/g, '');
  
  result = result.replace(/\n{3,}/g, '\n\n');
  result = result.trim();
  
  return result;
};

export const stripMarkdownPreserveCode = (text) => {
  if (text === null || text === undefined) {
    return '';
  }
  
  if (typeof text !== 'string') {
    return String(text);
  }
  
  let result = text;
  
  result = result.replace(/\\n/g, '\n');
  result = result.replace(/\\r\\n/g, '\n');
  result = result.replace(/\\r/g, '\n');
  result = result.replace(/\r\n/g, '\n');
  result = result.replace(/\r/g, '\n');
  
  result = result.replace(/^#{1,6}\s*/gm, '');
  
  result = result.replace(/\*\*([^*]+)\*\*/g, '$1');
  
  result = result.replace(/^\*\s+/gm, '• ');
  
  result = result.replace(/\n{3,}/g, '\n\n');
  result = result.trim();
  
  return result;
};

export const stripMarkdownWithLineBreaks = (text) => {
  if (!text) return '';
  return stripMarkdown(text);
};

export const cleanAndFormatText = (text) => {
  if (!text) return '';
  const cleaned = stripMarkdown(text);
  return cleaned;
};
