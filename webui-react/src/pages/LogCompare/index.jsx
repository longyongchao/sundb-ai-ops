import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import {
  Card, Button, Upload, Table, Tag, Tooltip, Row, Col,
  Statistic, Alert, Space, Typography, Divider, Empty,
  Progress, Segmented, message as antMessage,
} from 'antd'
import {
  InboxOutlined, FileTextOutlined,
  CheckCircleOutlined, WarningOutlined, CloseCircleOutlined,
  ClockCircleOutlined, ThunderboltOutlined, DatabaseOutlined,
  ReloadOutlined, TableOutlined, BarChartOutlined,
  CheckOutlined, CloseOutlined, PlayCircleOutlined, CodeOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import { lilacAPI } from '@/utils/api'
import './index.scss'

const { Dragger } = Upload
const { Text, Title } = Typography

// ── 内置示例数据 ──────────────────────────────────────────────────────
const DEMO_CSV_ROWS = [
  { gmt_create: '2024/11/15 16:57', predict_type: 'TXT_2_IMG', predict_status: 'SUCCEED', exec_time_seconds: '32',  groupId: 'G0000', prompt_length: '63',  negative_prompt_length: '26', num_images_per_prompt: '1', num_inference_steps: '30', checkpoint_model_version_id: 'M0000', num_lora: '0' },
  { gmt_create: '2024/11/15 18:16', predict_type: 'TXT_2_IMG', predict_status: 'SUCCEED', exec_time_seconds: '43',  groupId: 'G0001', prompt_length: '93',  negative_prompt_length: '',   num_images_per_prompt: '1', num_inference_steps: '40', checkpoint_model_version_id: 'M0001', num_lora: '0' },
  { gmt_create: '2024/11/17 4:44',  predict_type: 'TXT_2_IMG', predict_status: 'FAILED',  exec_time_seconds: '0',   groupId: 'G0001', prompt_length: '93',  negative_prompt_length: '',   num_images_per_prompt: '1', num_inference_steps: '40', checkpoint_model_version_id: 'M0001', num_lora: '0' },
  { gmt_create: '2024/11/18 9:05',  predict_type: 'IMG_2_IMG', predict_status: 'SUCCEED', exec_time_seconds: '18',  groupId: 'G0002', prompt_length: '45',  negative_prompt_length: '12', num_images_per_prompt: '2', num_inference_steps: '20', checkpoint_model_version_id: 'M0002', num_lora: '1' },
  { gmt_create: '2024/11/18 11:30', predict_type: 'TXT_2_IMG', predict_status: 'SUCCEED', exec_time_seconds: '55',  groupId: 'G0003', prompt_length: '120', negative_prompt_length: '30', num_images_per_prompt: '1', num_inference_steps: '50', checkpoint_model_version_id: 'M0000', num_lora: '2' },
  { gmt_create: '2024/11/19 2:15',  predict_type: 'IMG_2_IMG', predict_status: 'FAILED',  exec_time_seconds: '0',   groupId: 'G0002', prompt_length: '45',  negative_prompt_length: '12', num_images_per_prompt: '1', num_inference_steps: '20', checkpoint_model_version_id: 'M0003', num_lora: '0' },
  { gmt_create: '2024/11/19 14:22', predict_type: 'TXT_2_IMG', predict_status: 'SUCCEED', exec_time_seconds: '38',  groupId: 'G0004', prompt_length: '77',  negative_prompt_length: '18', num_images_per_prompt: '1', num_inference_steps: '30', checkpoint_model_version_id: 'M0001', num_lora: '1' },
  { gmt_create: '2024/11/20 8:00',  predict_type: 'TXT_2_IMG', predict_status: 'SUCCEED', exec_time_seconds: '29',  groupId: 'G0000', prompt_length: '50',  negative_prompt_length: '0',  num_images_per_prompt: '4', num_inference_steps: '25', checkpoint_model_version_id: 'M0000', num_lora: '0' },
]
const DEMO_SCHEMA = {
  timestamp_col: 'gmt_create', level_col: 'predict_status', message_col: 'predict_type',
  extra_cols: ['exec_time_seconds','groupId','prompt_length','negative_prompt_length','num_images_per_prompt','num_inference_steps','checkpoint_model_version_id','num_lora'],
}
const _TPL = 'TXT_2_IMG [predict_status=<*> exec_time_seconds=<*> groupId=<*> prompt_length=<*> negative_prompt_length=<*> num_images_per_prompt=<*> num_inference_steps=<*> checkpoint_model_version_id=<*> num_lora=<*>]'
const _ITPL = 'IMG_2_IMG [predict_status=<*> exec_time_seconds=<*> groupId=<*> prompt_length=<*> negative_prompt_length=<*> num_images_per_prompt=<*> num_inference_steps=<*> checkpoint_model_version_id=<*> num_lora=<*>]'
const DEMO_ENTRIES = [
  { timestamp: '2024-11-15 16:57:00', level: 'INFO',  message: 'TXT_2_IMG [predict_status=SUCCEED exec_time_seconds=32 groupId=G0000 prompt_length=63 negative_prompt_length=26 num_images_per_prompt=1 num_inference_steps=30 checkpoint_model_version_id=M0000 num_lora=0]',  template: _TPL,  template_source: 'llm'   },
  { timestamp: '2024-11-15 18:16:00', level: 'INFO',  message: 'TXT_2_IMG [predict_status=SUCCEED exec_time_seconds=43 groupId=G0001 prompt_length=93 num_images_per_prompt=1 num_inference_steps=40 checkpoint_model_version_id=M0001 num_lora=0]',                           template: _TPL,  template_source: 'cache' },
  { timestamp: '2024-11-17 04:44:00', level: 'ERROR', message: 'TXT_2_IMG [predict_status=FAILED exec_time_seconds=0 groupId=G0001 prompt_length=93 num_images_per_prompt=1 num_inference_steps=40 checkpoint_model_version_id=M0001 num_lora=0]',                            template: _TPL,  template_source: 'cache' },
  { timestamp: '2024-11-18 09:05:00', level: 'INFO',  message: 'IMG_2_IMG [predict_status=SUCCEED exec_time_seconds=18 groupId=G0002 prompt_length=45 negative_prompt_length=12 num_images_per_prompt=2 num_inference_steps=20 checkpoint_model_version_id=M0002 num_lora=1]', template: _ITPL, template_source: 'cache' },
  { timestamp: '2024-11-18 11:30:00', level: 'INFO',  message: 'TXT_2_IMG [predict_status=SUCCEED exec_time_seconds=55 groupId=G0003 prompt_length=120 negative_prompt_length=30 num_images_per_prompt=1 num_inference_steps=50 checkpoint_model_version_id=M0000 num_lora=2]',template: _TPL,  template_source: 'cache' },
  { timestamp: '2024-11-19 02:15:00', level: 'ERROR', message: 'IMG_2_IMG [predict_status=FAILED exec_time_seconds=0 groupId=G0002 prompt_length=45 negative_prompt_length=12 num_images_per_prompt=1 num_inference_steps=20 checkpoint_model_version_id=M0003 num_lora=0]',  template: _ITPL, template_source: 'cache' },
  { timestamp: '2024-11-19 14:22:00', level: 'INFO',  message: 'TXT_2_IMG [predict_status=SUCCEED exec_time_seconds=38 groupId=G0004 prompt_length=77 negative_prompt_length=18 num_images_per_prompt=1 num_inference_steps=30 checkpoint_model_version_id=M0001 num_lora=1]', template: _TPL,  template_source: 'cache' },
  { timestamp: '2024-11-20 08:00:00', level: 'INFO',  message: 'TXT_2_IMG [predict_status=SUCCEED exec_time_seconds=29 groupId=G0000 prompt_length=50 negative_prompt_length=0 num_images_per_prompt=4 num_inference_steps=25 checkpoint_model_version_id=M0000 num_lora=0]',   template: _TPL,  template_source: 'cache' },
]
const DEMO_FIELD_CHECKS = DEMO_CSV_ROWS.map((row, idx) => ({
  csv_row_idx: idx, entry_idx: idx, all_match: true,
  checks: [
    { col: 'gmt_create', role: 'timestamp', original: row.gmt_create, expected: DEMO_ENTRIES[idx].timestamp, parsed: DEMO_ENTRIES[idx].timestamp, match: true },
    { col: 'predict_status', role: 'level', original: row.predict_status, expected: DEMO_ENTRIES[idx].level, parsed: DEMO_ENTRIES[idx].level, match: true },
    { col: 'predict_type', role: 'message', original: row.predict_type, expected: row.predict_type, parsed: DEMO_ENTRIES[idx].message.slice(0, 30), match: true },
  ],
}))
const DEMO_ACCURACY = {
  checked_rows: 8, full_row_match: 8, full_pct: 100,
  ts_match: 8, ts_total: 8, ts_pct: 100,
  lv_match: 8, lv_total: 8, lv_pct: 100,
  msg_match: 8, msg_total: 8, msg_pct: 100,
  extra_match: 56, extra_total: 56, extra_pct: 100,
  tpl_placeholder: 8, tpl_pct: 100,
  row_alignment: 'exact', skipped_rows: 0,
}
const DEMO_PARSE_RESULT = {
  filename: 'lora_request_trace.csv（示例）',
  csv_conversion: { total_rows: 8, converted_rows: 8, schema: DEMO_SCHEMA, warnings: [], row_mapping: [0,1,2,3,4,5,6,7] },
  total_entries: 8, cache_hits: 7, llm_calls: 1, drain3_fallbacks: 0, parse_time_ms: 1243,
  entries: DEMO_ENTRIES,
  csv_rows: DEMO_CSV_ROWS,
  field_checks: DEMO_FIELD_CHECKS,
  accuracy: DEMO_ACCURACY,
}

// 支持 LILAC 可解析的日志格式（与后端 /diagnose/lilac/parse 一致）
const ACCEPTED_EXTENSIONS = ['.csv', '.log', '.txt', '.trc', '.out', '.trace']
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',')
const PARSE_MODE_LABELS = { llm: 'LLM', drain3: 'DRAIN3' }
const PARSE_MODE_OPTIONS = [
  {
    label: <span className="parse-mode-option"><ThunderboltOutlined />LLM</span>,
    value: 'llm',
  },
  {
    label: <span className="parse-mode-option"><DatabaseOutlined />DRAIN3</span>,
    value: 'drain3',
  },
]

function isCsvFile(name) {
  return /\.csv$/i.test(name || '')
}

function isAcceptedLogFile(name) {
  const lower = (name || '').toLowerCase()
  if (!lower.includes('.')) return true
  return ACCEPTED_EXTENSIONS.some(ext => lower.endsWith(ext))
}

function computeTemplateStats(entries) {
  const sources = {}
  let withPlaceholder = 0
  for (const e of entries) {
    const src = e.template_source || 'unknown'
    sources[src] = (sources[src] || 0) + 1
    if (e.template?.includes('<*>')) withPlaceholder++
  }
  return { sources, withPlaceholder, total: entries.length }
}

// ── CSV 解析 ──────────────────────────────────────────────────────────
function parseCSVLine(line) {
  const result = []; let cur = ''; let inQ = false
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (c === '"') { if (inQ && line[i+1] === '"') { cur += '"'; i++ } else inQ = !inQ }
    else if (c === ',' && !inQ) { result.push(cur); cur = '' }
    else cur += c
  }
  result.push(cur); return result
}
function parseCSV(text) {
  const lines = text.split(/\r?\n/)
  if (!lines.length) return { headers: [], rows: [] }
  const headers = parseCSVLine(lines[0]); const rows = []
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue
    const vals = parseCSVLine(lines[i]); const row = {}
    headers.forEach((h, idx) => { row[h] = vals[idx] ?? '' })
    rows.push(row)
  }
  return { headers, rows }
}

// ── 后端 field_checks 适配（服务端统一计算准确率，前端仅展示） ──────────
function adaptBackendChecks(backendChecks) {
  if (!backendChecks) return []
  return backendChecks.map(c => ({
    col: c.col,
    role: c.role,
    originalVal: c.original || '',
    expectedVal: c.expected || '',
    parsedVal: c.parsed || '',
    match: c.match,
    na: c.match === null,
    hint: c.match === null ? '原始值为空，跳过'
      : c.match ? '匹配成功'
      : `期望: ${c.expected}，实际: ${c.parsed}`,
  }))
}

// ── 非 CSV 日志行质量判断 ─────────────────────────────────────────────
function getLogEntryQuality(entry) {
  if (!entry) return 'bad'
  const hasMsg = !!(entry.message)
  const hasTs  = !!(entry.timestamp)
  const hasLv  = !!(entry.level)
  if (hasMsg && hasTs && hasLv) return 'good'
  if (hasMsg) return 'warn'
  return 'bad'
}

// ── UI 工具 ───────────────────────────────────────────────────────────
function getTemplateSourceTag(src) {
  const map = { llm:{color:'#1677ff',label:'LLM'}, cache:{color:'#52c41a',label:'缓存'},
    drain3:{color:'#fa8c16',label:'Drain3'}, static:{color:'#8c8c8c',label:'静态'} }
  const cfg = map[src] || { color:'#595959', label: src||'-' }
  return <Tag style={{ fontSize:11, padding:'0 5px', marginRight:0 }} color={cfg.color}>{cfg.label}</Tag>
}
function getLevelColor(level) {
  const map = { ERROR:'red',FATAL:'volcano',WARNING:'orange',INFO:'cyan',DEBUG:'geekblue',TRACE:'purple' }
  return map[(level||'').toUpperCase()] || 'default'
}
const ROLE_CFG = { timestamp:{color:'#13c2c2',label:'时间戳'}, level:{color:'#722ed1',label:'级别'},
  message:{color:'#1677ff',label:'消息'}, extra:{color:'#595959',label:'附加'} }
function RoleBadge({ role }) {
  const cfg = ROLE_CFG[role]; if (!cfg) return null
  return <span style={{ fontSize:10, padding:'1px 5px', borderRadius:3,
    background:cfg.color+'33', color:cfg.color, border:`1px solid ${cfg.color}66`, marginLeft:4 }}>{cfg.label}</span>
}

// ── 完整模板展示（展开详情用，避免 ellipsis 截断） ───────────────────
function FullTemplateBlock({ template, templateSource }) {
  if (!template) return null
  const hasVar = template.includes('<*>')
  return (
    <div style={{ marginTop: 10 }}>
      <Space size={8} style={{ marginBottom: 6 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>完整模板</Text>
        {getTemplateSourceTag(templateSource)}
        <Tag style={{ fontSize: 11 }} color={hasVar ? 'green' : 'default'}>
          {hasVar ? '含变量 <*>' : '纯静态模板'}
        </Tag>
        <Text type="secondary" style={{ fontSize: 11 }}>{template.length} 字符</Text>
      </Space>
      <pre className={`field-val entry-detail-pre entry-detail-pre--template ${hasVar ? 'template-dynamic' : 'template-static'}`}>
        {template}
      </pre>
    </div>
  )
}

// ── 行展开：字段详情表（CSV 模式） ────────────────────────────────────
function FieldDetailTable({ checks }) {
  const cols = [
    { title: '列名', dataIndex: 'col', key: 'col', width: 200,
      render: (v, r) => <span><code style={{color:'#e2b96c'}}>{v}</code><RoleBadge role={r.role} /></span> },
    { title: '原始值', dataIndex: 'originalVal', key: 'orig', width: 160,
      render: v => <code className="field-val">{v || <span className="empty-cell">（空）</span>}</code> },
    { title: '期望（解析后）', dataIndex: 'expectedVal', key: 'exp', width: 220,
      render: v => <code className="field-val expected-val">{v}</code> },
    { title: '实际解析值', dataIndex: 'parsedVal', key: 'parsed', ellipsis: true,
      render: v => <code className="field-val">{v || <span className="empty-cell">—</span>}</code> },
    { title: '匹配', key: 'match', width: 80, align: 'center',
      render: (_, r) => {
        if (r.na) return <Tag style={{fontSize:11}}>跳过</Tag>
        return r.match
          ? <CheckCircleOutlined style={{color:'#52c41a', fontSize:16}} />
          : <CloseCircleOutlined style={{color:'#ff4d4f', fontSize:16}} />
      }},
  ]
  return (
    <Table
      className="field-detail-table"
      dataSource={checks.map((c,i) => ({...c, key:i}))}
      columns={cols} pagination={false} size="small" bordered={false}
    />
  )
}

// ── 行展开：日志条目字段详情表（非 CSV 模式） ─────────────────────────
function LogEntryFieldTable({ entry }) {
  if (!entry) return null

  const EXTRACT_CFG = [
    { field: 'timestamp', label: '时间戳', color: '#13c2c2', role: 'timestamp' },
    { field: 'level',     label: '日志级别', color: '#722ed1', role: 'level' },
    { field: 'message',   label: '消息体', color: '#1677ff', role: 'message' },
  ]

  const rows = EXTRACT_CFG.map(cfg => {
    const val = entry[cfg.field]
    const extracted = !!(val)
    return {
      key: cfg.field,
      field: cfg.field,
      label: cfg.label,
      color: cfg.color,
      role: cfg.role,
      value: val || '',
      extracted,
      match: extracted ? true : null,
    }
  })

  const cols = [
    { title: '字段', dataIndex: 'label', key: 'label', width: 110,
      render: (v, r) => (
        <span>
          <code style={{ color: r.color }}>{v}</code>
          <RoleBadge role={r.role} />
        </span>
      ) },
    { title: '提取值', dataIndex: 'value', key: 'value',
      render: (v, r) => {
        if (!v) return <span className="empty-cell">（未提取）</span>
        // 长文本（如 JSON message）用 pre 完整展示，避免表格 ellipsis 截断
        if (v.length > 80 || r.field === 'message') {
          return <pre className="field-val entry-detail-pre entry-detail-pre--inline">{v}</pre>
        }
        return <code className={`field-val ${r.field === 'timestamp' ? 'expected-val' : ''}`}>{v}</code>
      } },
    { title: '状态', key: 'status', width: 130, align: 'center',
      render: (_, r) => {
        if (r.match === null)
          return <Tag style={{ fontSize: 11 }} color="default">未提取</Tag>
        return <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
      } },
  ]

  const hasParams = entry.parameters?.length > 0
  const hasMeta   = entry.metadata && Object.keys(entry.metadata).length > 0

  return (
    <div className="entry-detail">
      <Table
        className="field-detail-table"
        dataSource={rows}
        columns={cols}
        pagination={false}
        size="small"
        bordered={false}
      />
      <FullTemplateBlock template={entry.template} templateSource={entry.template_source} />
      {hasParams && (
        <div style={{ marginTop: 10 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>提取参数</Text>
          <pre className="field-val entry-detail-pre">{JSON.stringify(entry.parameters, null, 2)}</pre>
        </div>
      )}
      {hasMeta && (
        <div style={{ marginTop: 10 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>元数据</Text>
          <pre className="field-val entry-detail-pre">{JSON.stringify(entry.metadata, null, 2)}</pre>
        </div>
      )}
      <div style={{ marginTop: 10 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>原始文本</Text>
        <pre className="field-val entry-detail-pre">{entry.raw_text || '—'}</pre>
      </div>
    </div>
  )
}

// ── 转换保真度面板（CSV 模式，使用后端统一计算的 accuracy） ─────────────
function AccuracyPanel({ accuracy, schema }) {
  if (!accuracy) return null
  const getStatus = p => p === null ? null : p >= 95 ? 'good' : p >= 80 ? 'warn' : 'bad'
  const statusStyle = { good:{color:'#52c41a',label:'优秀'}, warn:{color:'#faad14',label:'良好'}, bad:{color:'#ff4d4f',label:'需关注'} }
  const items = [
    { label:'全字段保真率', pct:accuracy.full_pct, desc:`${accuracy.full_row_match}/${accuracy.checked_rows} 行全部字段一致`,
      stroke:'#00d4ff', tip:'所有列（时间戳+级别+消息+附加）全部正确对应的行占比，综合指标' },
    { label:'时间戳还原', pct:accuracy.ts_pct, desc:`${accuracy.ts_match}/${accuracy.ts_total} 行匹配`,
      stroke:'#13c2c2', tip:`${schema?.timestamp_col} 列经服务端规范化后与 LILAC 提取值逐字符比对` },
    { label:'级别映射', pct:accuracy.lv_pct, desc:`${accuracy.lv_match}/${accuracy.lv_total} 行正确`,
      stroke:'#722ed1', tip:`${schema?.level_col} 列映射为标准级别后与解析结果比对` },
    { label:'消息列还原', pct:accuracy.msg_pct, desc:`${accuracy.msg_match}/${accuracy.msg_total} 行对应`,
      stroke:'#1677ff', tip:`${schema?.message_col} 列原始值应出现在解析后消息体开头` },
    { label:'附加列保真', pct:accuracy.extra_pct, desc:`${accuracy.extra_match}/${accuracy.extra_total} 个字段值匹配`,
      stroke:'#fa8c16', tip:'每个附加列的 key=原始值 应出现在解析后的消息体中' },
    { label:'变量模板覆盖率', pct:accuracy.tpl_pct, desc:`${accuracy.tpl_placeholder}/${accuracy.checked_rows} 行含 <*>`,
      stroke:'#eb2f96', tip:'模板含 <*> 占位符表示成功提取了变量部分（非固定文本）' },
  ]
  return (
    <Card className="accuracy-card" title={<Space><BarChartOutlined />转换保真度验证（服务端统一计算）</Space>}>
      {accuracy.row_alignment !== 'exact' && (
        <Alert type="warning" style={{marginBottom:12}} showIcon
          message={`行对齐模式：${accuracy.row_alignment}（${accuracy.skipped_rows} 行被跳过转换），验证基于已成功转换的 ${accuracy.checked_rows} 行`} />
      )}
      <Row gutter={[20, 16]}>
        {items.map(item => {
          const st = getStatus(item.pct)
          const sc = st ? statusStyle[st] : null
          return (
            <Col span={4} key={item.label}>
              <Tooltip title={item.tip} placement="top">
                <div className="accuracy-item">
                  <Text style={{ fontSize:12, color:'rgba(255,255,255,0.65)', cursor:'help' }}>{item.label}</Text>
                  {item.pct !== null ? (
                    <>
                      <div style={{ display:'flex', alignItems:'baseline', gap:6, margin:'6px 0 3px' }}>
                        <span style={{ fontSize:26, fontWeight:700, color: sc?.color || '#888' }}>{item.pct}%</span>
                        {sc && <Tag color={sc.color} style={{fontSize:11}}>{sc.label}</Tag>}
                      </div>
                      <Progress percent={item.pct} showInfo={false} strokeColor={item.stroke}
                        trailColor="rgba(255,255,255,0.08)" size="small" />
                      <Text type="secondary" style={{fontSize:11}}>{item.desc}</Text>
                    </>
                  ) : (
                    <div style={{ color:'rgba(255,255,255,0.25)', fontSize:12, marginTop:8 }}>未检测到对应列</div>
                  )}
                </div>
              </Tooltip>
            </Col>
          )
        })}
      </Row>
    </Card>
  )
}

// ── 提取完整度面板（非 CSV 模式，展示各字段提取率） ───────────────────
function LogCompletenessPanel({ entries }) {
  if (!entries?.length) return null
  const n = entries.length
  const pct = (a, b) => b > 0 ? Math.round(a / b * 100) : null

  const withTs     = entries.filter(e => e.timestamp).length
  const withLv     = entries.filter(e => e.level).length
  const withMsg    = entries.filter(e => e.message).length
  const withTpl    = entries.filter(e => e.template?.includes('<*>')).length
  const withParams = entries.filter(e => e.parameters?.length > 0).length
  const withMeta   = entries.filter(e => e.metadata && Object.keys(e.metadata).length > 0).length

  const getStatus = p => p === null ? null : p >= 95 ? 'good' : p >= 80 ? 'warn' : 'bad'
  const statusStyle = { good:{color:'#52c41a',label:'优秀'}, warn:{color:'#faad14',label:'良好'}, bad:{color:'#ff4d4f',label:'需关注'} }

  const items = [
    { label: '时间戳提取率',  pct: pct(withTs, n),     desc: `${withTs}/${n} 行提取到时间戳`,     stroke: '#13c2c2',
      tip: '成功从原始日志行解析出时间戳字段的比例' },
    { label: '级别识别率',    pct: pct(withLv, n),     desc: `${withLv}/${n} 行识别到日志级别`,   stroke: '#722ed1',
      tip: '成功识别 INFO/WARNING/ERROR 等日志级别的行占比' },
    { label: '消息体提取率',  pct: pct(withMsg, n),    desc: `${withMsg}/${n} 行提取到消息体`,    stroke: '#1677ff',
      tip: '成功提取到日志主体消息内容的行占比' },
    { label: '变量模板覆盖率',pct: pct(withTpl, n),    desc: `${withTpl}/${n} 行含 <*>`,          stroke: '#eb2f96',
      tip: '模板含 <*> 占位符，表示成功归纳出含变量的通用模板' },
    { label: '参数提取率',    pct: pct(withParams, n), desc: `${withParams}/${n} 行有结构化参数`, stroke: '#fa8c16',
      tip: '从消息体中解析出结构化 key=value 参数的行占比' },
    { label: '元数据提取率',  pct: pct(withMeta, n),   desc: `${withMeta}/${n} 行有附加元数据`,  stroke: '#52c41a',
      tip: '从日志行中额外识别出结构化元数据（如模块、文件名等）的行占比' },
  ]

  return (
    <Card className="accuracy-card" title={<Space><BarChartOutlined />提取完整度（结构化字段覆盖率）</Space>}>
      <Row gutter={[20, 16]}>
        {items.map(item => {
          const st = getStatus(item.pct)
          const sc = st ? statusStyle[st] : null
          return (
            <Col span={4} key={item.label}>
              <Tooltip title={item.tip} placement="top">
                <div className="accuracy-item">
                  <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', cursor: 'help' }}>{item.label}</Text>
                  {item.pct !== null ? (
                    <>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, margin: '6px 0 3px' }}>
                        <span style={{ fontSize: 26, fontWeight: 700, color: sc?.color || '#888' }}>{item.pct}%</span>
                        {sc && <Tag color={sc.color} style={{ fontSize: 11 }}>{sc.label}</Tag>}
                      </div>
                      <Progress percent={item.pct} showInfo={false} strokeColor={item.stroke}
                        trailColor="rgba(255,255,255,0.08)" size="small" />
                      <Text type="secondary" style={{ fontSize: 11 }}>{item.desc}</Text>
                    </>
                  ) : (
                    <div style={{ color: 'rgba(255,255,255,0.25)', fontSize: 12, marginTop: 8 }}>无数据</div>
                  )}
                </div>
              </Tooltip>
            </Col>
          )
        })}
      </Row>
    </Card>
  )
}

// ── 模板来源统计（两种模式均用） ──────────────────────────────────────
function TemplateStatsPanel({ entries }) {
  const stats = useMemo(() => computeTemplateStats(entries), [entries])
  if (!stats.total) return null
  const sourceLabels = { llm: 'LLM', cache: '缓存', drain3: 'Drain3', static: '静态', seed: '种子' }
  return (
    <Card className="schema-card" title="模板提取统计">
      <Space wrap size={[8, 8]}>
        <Text type="secondary">共 {stats.total} 条</Text>
        <Divider type="vertical" />
        {Object.entries(stats.sources).map(([src, cnt]) => (
          <span key={src}>{getTemplateSourceTag(src)} <Text>{sourceLabels[src] || src} × {cnt}</Text></span>
        ))}
        <Divider type="vertical" />
        <Text type="secondary">含变量模板：</Text>
        <Tag color={stats.withPlaceholder > 0 ? 'green' : 'default'}>
          {stats.withPlaceholder}/{stats.total}
        </Tag>
      </Space>
    </Card>
  )
}

// ── 主组件 ────────────────────────────────────────────────────────────
const LogCompare = () => {
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileMode, setFileMode] = useState(null) // 'csv' | 'log'
  const [csvData, setCsvData] = useState(null)
  const [rawPreview, setRawPreview] = useState(null) // { lineCount, sampleLines }
  const [parseResult, setParseResult] = useState(null)
  const [parseMode, setParseMode] = useState('llm')
  const [loading, setLoading] = useState(false)
  const [cacheClearing, setCacheClearing] = useState(false)
  const [cacheClearConfirming, setCacheClearConfirming] = useState(false)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const cacheClearTimerRef = useRef(null)
  const PAGE_SIZE = 20

  useEffect(() => () => {
    if (cacheClearTimerRef.current) {
      clearTimeout(cacheClearTimerRef.current)
    }
  }, [])

  const handleFileSelect = useCallback((file) => {
    if (!isAcceptedLogFile(file.name)) {
      antMessage.warning(`不支持的文件类型，请上传 ${ACCEPTED_EXTENSIONS.join(' / ')} 等日志文件`)
      return false
    }
    const mode = isCsvFile(file.name) ? 'csv' : 'log'
    setSelectedFile(file)
    setFileMode(mode)
    setParseResult(null)
    setError(null)
    setPage(1)
    setCsvData(null)
    setRawPreview(null)

    const reader = new FileReader()
    reader.onload = e => {
      const text = e.target.result
      if (mode === 'csv') {
        const parsed = parseCSV(text)
        setCsvData(parsed)
        antMessage.success(`已读取 ${parsed.rows.length} 行，${parsed.headers.length} 列`)
      } else {
        const lines = text.split(/\r?\n/).filter(l => l.trim())
        setRawPreview({ lineCount: lines.length, sampleLines: lines.slice(0, 8) })
        antMessage.success(`已读取 ${lines.length} 行日志`)
      }
    }
    reader.onerror = () => antMessage.error('文件读取失败')
    reader.readAsText(file, 'utf-8')
    return false
  }, [])

  const handleParse = async () => {
    if (!selectedFile) { antMessage.warning('请先选择日志文件'); return }
    setLoading(true); setError(null)
    try {
      const data = fileMode === 'csv'
        ? await lilacAPI.parseCsv(selectedFile, { parseMode })
        : await lilacAPI.parseFile(selectedFile, { parseMode })
      setParseResult(data); setPage(1)
      antMessage.success(`${PARSE_MODE_LABELS[parseMode]} 解析完成，共 ${data.total_entries} 条`)
    } catch (err) { setError(err?.message || '解析失败') }
    finally { setLoading(false) }
  }

  const handleClearCache = async () => {
    setCacheClearing(true)
    try {
      await lilacAPI.clearCache()
      antMessage.success('日志解析缓存已清空')
    } catch (err) {
      antMessage.error(err?.message || '清空缓存失败')
    } finally {
      setCacheClearing(false)
    }
  }

  const handleCacheClearClick = async () => {
    if (!cacheClearConfirming) {
      setCacheClearConfirming(true)
      if (cacheClearTimerRef.current) {
        clearTimeout(cacheClearTimerRef.current)
      }
      cacheClearTimerRef.current = setTimeout(() => {
        setCacheClearConfirming(false)
        cacheClearTimerRef.current = null
      }, 3000)
      return
    }

    if (cacheClearTimerRef.current) {
      clearTimeout(cacheClearTimerRef.current)
      cacheClearTimerRef.current = null
    }
    setCacheClearConfirming(false)
    await handleClearCache()
  }

  const handleReset = () => {
    setSelectedFile(null); setFileMode(null); setCsvData(null); setRawPreview(null)
    setParseResult(null); setError(null); setPage(1)
  }

  const handleLoadDemo = () => {
    setFileMode('csv')
    setCsvData({ headers: Object.keys(DEMO_CSV_ROWS[0]), rows: DEMO_CSV_ROWS })
    setRawPreview(null)
    setParseResult(DEMO_PARSE_RESULT)
    setSelectedFile({ name: 'lora_request_trace.csv（示例）', size: 0 })
    setParseMode('llm')
    setError(null); setPage(1)
    antMessage.success('示例数据已加载，共 8 行')
  }

  const schema  = parseResult?.csv_conversion?.schema
  const entries = parseResult?.entries || []

  // 准确率（CSV 模式，直接使用后端统一计算的结果）
  const accuracy = parseResult?.accuracy || null
  const backendFieldChecks = parseResult?.field_checks || []
  const backendCsvRows = parseResult?.csv_rows || null

  // ── CSV 对比数据 ────────────────────────────────────────────────────
  const mergedData = useMemo(() => {
    const rows = backendCsvRows || (csvData ? csvData.rows : null)
    if (!rows) return []
    return rows.map((csvRow, idx) => {
      const fc = backendFieldChecks.find(f => f.csv_row_idx === idx)
      const entry = fc ? entries[fc.entry_idx] : null
      const fieldChecks = fc ? adaptBackendChecks(fc.checks) : []
      const failedChecks = fieldChecks.filter(c => c.match === false)
      const naChecks = fieldChecks.filter(c => c.na)
      const quality = !fc ? 'skipped'
        : !entry ? 'bad'
        : failedChecks.length > 0 ? 'warn'
        : 'good'
      return { key: idx, rowIndex: idx + 1, csvRow, entry, fieldChecks, failedChecks, naChecks, quality }
    })
  }, [backendCsvRows, csvData, backendFieldChecks, entries])

  const pagedData = mergedData.slice((page-1)*PAGE_SIZE, page*PAGE_SIZE)

  // ── CSV 表格列 ──────────────────────────────────────────────────────
  const columns = useMemo(() => {
    if (!csvData) return []
    const roleOf = col => {
      if (!schema) return null
      if (col === schema.timestamp_col) return 'timestamp'
      if (col === schema.level_col) return 'level'
      if (col === schema.message_col) return 'message'
      return 'extra'
    }
    const csvCols = csvData.headers.map(col => ({
      title: <span>{col}{schema && <RoleBadge role={roleOf(col)} />}</span>,
      dataIndex: ['csvRow', col], key: `csv_${col}`, ellipsis: true, width: 130,
      render: val => (
        <Tooltip title={val} placement="topLeft">
          <span className="cell-text">{val || <span className="empty-cell">—</span>}</span>
        </Tooltip>
      ),
    }))
    const parsedCols = parseResult ? [
      { title:'时间戳', key:'p_ts', width:165,
        render: (_,rec) => {
          const c = rec.fieldChecks.find(f => f.role==='timestamp')
          const val = rec.entry?.timestamp
          if (!val) return <span className="empty-cell">—</span>
          return <span style={{display:'flex',alignItems:'center',gap:4}}>
            {c && c.match !== null && (c.match ? <CheckOutlined style={{color:'#52c41a',fontSize:11}}/> : <CloseOutlined style={{color:'#ff4d4f',fontSize:11}}/>)}
            <span className="parsed-ts">{val}</span>
          </span>
        }},
      { title:'级别', key:'p_lv', width:90,
        render: (_,rec) => {
          const c = rec.fieldChecks.find(f => f.role==='level')
          const val = rec.entry?.level
          if (!val) return <span className="empty-cell">—</span>
          return <span style={{display:'flex',alignItems:'center',gap:4}}>
            {c && c.match !== null && (c.match ? <CheckOutlined style={{color:'#52c41a',fontSize:11}}/> : <CloseOutlined style={{color:'#ff4d4f',fontSize:11}}/>)}
            <Tag color={getLevelColor(val)} style={{margin:0}}>{val}</Tag>
          </span>
        }},
      { title:'消息体', dataIndex:['entry','message'], key:'p_msg', ellipsis:true, width:240,
        render: val => <Tooltip title={val} placement="topLeft" overlayStyle={{maxWidth:500}}>
          <span className="cell-text">{val||<span className="empty-cell">—</span>}</span>
        </Tooltip>},
      { title:'模板', key:'p_tpl', ellipsis:true, width:220,
        render: (_,rec) => {
          const val = rec.entry?.template; const src = rec.entry?.template_source
          const hasPlaceholder = val?.includes('<*>')
          return <Space size={4}>
            {getTemplateSourceTag(src)}
            {hasPlaceholder ? <CheckOutlined style={{color:'#52c41a',fontSize:11}}/> : <CloseOutlined style={{color:'#8c8c8c',fontSize:11}}/>}
            <Tooltip title={val} placement="topLeft" overlayStyle={{maxWidth:500}}>
              <span className={`cell-text ${hasPlaceholder ? 'template-dynamic' : 'template-static'}`}>
                {val||<span className="empty-cell">—</span>}
              </span>
            </Tooltip>
          </Space>
        }},
    ] : []

    const QCFG = { good:{icon:<CheckCircleOutlined/>,color:'#52c41a'}, warn:{icon:<WarningOutlined/>,color:'#faad14'}, bad:{icon:<CloseCircleOutlined/>,color:'#ff4d4f'}, skipped:{icon:<CloseOutlined/>,color:'#8c8c8c'} }
    return [
      { title:'#', dataIndex:'rowIndex', key:'idx', width:70, fixed:'left',
        render:(val,rec) => {
          const q = QCFG[rec.quality] || QCFG.bad
          const failCnt = rec.failedChecks?.length || 0
          return <span style={{color:q.color,display:'flex',alignItems:'center',gap:4}}>
            {q.icon}
            <span>{val}</span>
            {rec.quality === 'skipped' && <Tag style={{fontSize:10,padding:'0 4px',marginLeft:2}}>跳过</Tag>}
            {failCnt > 0 && <Tag color="red" style={{fontSize:10,padding:'0 4px',marginLeft:2}}>{failCnt}项不符</Tag>}
          </span>
        }},
      { title:'原始 CSV 数据', children: csvCols },
      ...(parseResult ? [{ title:'LILAC 解析结果', children: parsedCols }] : []),
    ]
  }, [csvData, parseResult, schema])

  // ── 非 CSV 对比数据 ─────────────────────────────────────────────────
  const logMergedData = useMemo(() => {
    if (fileMode !== 'log') return []
    return entries.map((entry, idx) => {
      const quality = getLogEntryQuality(entry)
      const missingFields = []
      if (!entry.timestamp) missingFields.push('时间戳')
      if (!entry.level)     missingFields.push('级别')
      if (!entry.message)   missingFields.push('消息体')
      return { key: idx, rowIndex: idx + 1, entry, quality, missingFields }
    })
  }, [fileMode, entries])

  const pagedLogData = logMergedData.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  // ── 非 CSV 表格列（与 CSV 同结构：原始行 | LILAC 解析结果） ──────────
  const logCompareColumns = useMemo(() => {
    const QCFG = {
      good:    { icon: <CheckCircleOutlined />, color: '#52c41a' },
      warn:    { icon: <WarningOutlined />,    color: '#faad14' },
      bad:     { icon: <CloseCircleOutlined />, color: '#ff4d4f' },
    }
    const rawCols = [
      { title: '原始文本', key: 'raw', width: 380, ellipsis: true,
        render: (_, rec) => {
          const val = rec.entry?.raw_text
          return <Tooltip title={val} placement="topLeft" overlayStyle={{ maxWidth: 600 }}>
            <span className="cell-text raw-text">{val || <span className="empty-cell">—</span>}</span>
          </Tooltip>
        }},
    ]
    const parsedCols = [
      { title: '时间戳', key: 'p_ts', width: 170,
        render: (_, rec) => {
          const val = rec.entry?.timestamp
          return val
            ? <span className="parsed-ts">{val}</span>
            : <span className="empty-cell">—</span>
        }},
      { title: '级别', key: 'p_lv', width: 95,
        render: (_, rec) => {
          const val = rec.entry?.level
          return val
            ? <Tag color={getLevelColor(val)} style={{ margin: 0 }}>{val}</Tag>
            : <span className="empty-cell">—</span>
        }},
      { title: '消息体', key: 'p_msg', ellipsis: true, width: 260,
        render: (_, rec) => {
          const val = rec.entry?.message
          return <Tooltip title={val} placement="topLeft" overlayStyle={{ maxWidth: 500 }}>
            <span className="cell-text">{val || <span className="empty-cell">—</span>}</span>
          </Tooltip>
        }},
      { title: '来源', key: 'p_src', width: 72,
        render: (_, rec) => getTemplateSourceTag(rec.entry?.template_source) },
      { title: '模板', key: 'p_tpl', ellipsis: true, width: 220,
        render: (_, rec) => {
          const val = rec.entry?.template
          const hasPlaceholder = val?.includes('<*>')
          return <Space size={4}>
            {hasPlaceholder
              ? <CheckOutlined style={{ color: '#52c41a', fontSize: 11 }} />
              : <CloseOutlined style={{ color: '#8c8c8c', fontSize: 11 }} />}
            <Tooltip title={val} placement="topLeft" overlayStyle={{ maxWidth: 500 }}>
              <span className={`cell-text ${hasPlaceholder ? 'template-dynamic' : 'template-static'}`}>
                {val || <span className="empty-cell">—</span>}
              </span>
            </Tooltip>
          </Space>
        }},
    ]
    return [
      { title: '#', dataIndex: 'rowIndex', key: 'idx', width: 80, fixed: 'left',
        render: (val, rec) => {
          const q = QCFG[rec.quality] || QCFG.bad
          return (
            <span style={{ color: q.color, display: 'flex', alignItems: 'center', gap: 4 }}>
              {q.icon}
              <span>{val}</span>
              {rec.missingFields?.length > 0 && (
                <Tooltip title={`缺失：${rec.missingFields.join('、')}`}>
                  <Tag color="orange" style={{ fontSize: 10, padding: '0 4px', marginLeft: 2, cursor: 'help' }}>
                    缺{rec.missingFields.length}项
                  </Tag>
                </Tooltip>
              )}
            </span>
          )
        }},
      { title: '原始日志行', children: rawCols },
      { title: 'LILAC 解析结果', children: parsedCols },
    ]
  }, [])

  const qualityStats = mergedData.reduce((acc, r) => { acc[r.quality] = (acc[r.quality] || 0) + 1; return acc }, {})
  const logQualityStats = logMergedData.reduce((acc, r) => { acc[r.quality] = (acc[r.quality] || 0) + 1; return acc }, {})

  const stats = parseResult ? {
    totalEntries: parseResult.total_entries,
    totalRows: parseResult.csv_conversion?.total_rows ?? parseResult.total_entries,
    converted: parseResult.csv_conversion?.converted_rows ?? parseResult.total_entries,
    cacheHits: parseResult.cache_hits, llmCalls: parseResult.llm_calls,
    drain3: parseResult.drain3_fallbacks, parseMs: parseResult.parse_time_ms,
    mode: parseResult.parse_mode || parseMode,
  } : null

  const statsItems = useMemo(() => {
    if (!stats) return []
    const common = [
      { title: '解析耗时', value: `${stats.parseMs?.toFixed(0) ?? '—'} ms`, icon: <ClockCircleOutlined /> },
      { title: 'LLM 调用', value: stats.llmCalls, icon: <ThunderboltOutlined style={{ color: '#1677ff' }} /> },
      { title: '缓存命中', value: stats.cacheHits, icon: <DatabaseOutlined style={{ color: '#52c41a' }} /> },
      {
        title: stats.mode === 'drain3' ? 'Drain3 解析' : 'Drain3 兜底',
        value: stats.drain3,
        icon: <WarningOutlined style={{ color: '#fa8c16' }} />,
      },
    ]
    if (fileMode === 'csv') {
      return [
        { title: '原始行数', value: stats.totalRows, icon: <DatabaseOutlined /> },
        { title: '成功转换', value: stats.converted, icon: <CheckCircleOutlined style={{ color: '#52c41a' }} /> },
        ...common,
      ]
    }
    return [
      { title: '解析条目', value: stats.totalEntries, icon: <DatabaseOutlined /> },
      { title: '全字段完整', value: logQualityStats.good || 0, icon: <CheckCircleOutlined style={{ color: '#52c41a' }} /> },
      ...common,
    ]
  }, [stats, fileMode, logQualityStats])

  const fileInfoExtra = fileMode === 'csv' && csvData
    ? ` · ${csvData.rows.length} 行 · ${csvData.headers.length} 列`
    : rawPreview
      ? ` · ${rawPreview.lineCount} 行`
      : ''

  return (
    <div className="log-compare-page">
      {/* 页头 */}
      <div className="page-header">
        <div className="header-left">
          <Title level={4} style={{margin:0}}>
            <TableOutlined style={{marginRight:8,color:'#00d4ff'}} />日志解析
          </Title>
          <Text type="secondary" style={{fontSize:13,marginTop:4}}>
            支持 CSV / LOG / TXT / TRC 等格式；均可逐行对比原始内容与 LILAC 结构化解析结果
          </Text>
        </div>
        <div className="header-actions">
          <div className="cache-tool">
            <DatabaseOutlined className="cache-tool-icon" />
            <span className="cache-tool-label">
              {cacheClearConfirming ? '再次点击确认' : '解析缓存'}
            </span>
            <Button
              aria-label={cacheClearConfirming ? '确认清空日志解析缓存' : '清空日志解析缓存'}
              className={`cache-clear-btn ${cacheClearConfirming ? 'is-confirming' : ''}`}
              icon={cacheClearConfirming ? <CheckOutlined /> : <DeleteOutlined />}
              loading={cacheClearing}
              onClick={handleCacheClearClick}
              size="small"
              title={cacheClearConfirming ? '确认清空日志解析缓存' : '清空日志解析缓存'}
              type="text"
            >
              {cacheClearConfirming ? '清空' : null}
            </Button>
          </div>
          {(selectedFile||parseResult) && <Button icon={<ReloadOutlined/>} onClick={handleReset}>重新上传</Button>}
        </div>
      </div>

      {/* 上传区 */}
      {!selectedFile && (
        <Card className="upload-card">
          <Dragger accept={ACCEPT_ATTR} multiple={false} beforeUpload={handleFileSelect} showUploadList={false} className="upload-dragger">
            <p className="ant-upload-drag-icon"><InboxOutlined style={{color:'#00d4ff',fontSize:48}}/></p>
            <p className="ant-upload-text">拖入日志文件，或点击选择</p>
            <p className="ant-upload-hint">
              支持 {ACCEPTED_EXTENSIONS.join('、')}；所有格式均支持原始行与解析结果的逐行对比
            </p>
          </Dragger>
          <div style={{textAlign:'center',marginTop:16}}>
            <Divider plain style={{color:'rgba(255,255,255,0.25)',borderColor:'rgba(255,255,255,0.1)'}}>或者</Divider>
            <Button icon={<PlayCircleOutlined/>} onClick={handleLoadDemo} className="demo-btn" size="large">
              查看内置示例（lora_request_trace.csv 节选）
            </Button>
            <div style={{marginTop:8,color:'rgba(255,255,255,0.35)',fontSize:12}}>无需上传，直接展示 8 行真实解析与全字段验证结果</div>
          </div>
        </Card>
      )}

      {/* 文件信息 */}
      {selectedFile && !parseResult && (
        <Card className="file-info-card">
          <Row align="middle" gutter={16}>
            <Col><FileTextOutlined style={{fontSize:32,color:'#00d4ff'}}/></Col>
            <Col flex={1}>
              <div style={{fontWeight:600}}>{selectedFile.name}</div>
              <Text type="secondary" style={{fontSize:12}}>
                {selectedFile.size > 0 ? `${(selectedFile.size/1024).toFixed(1)} KB` : '示例文件'}
                {fileInfoExtra}
                {fileMode === 'log' && <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>日志文件</Tag>}
                {fileMode === 'csv' && <Tag color="cyan" style={{ marginLeft: 8, fontSize: 11 }}>CSV</Tag>}
                <Tag color={parseMode === 'llm' ? 'geekblue' : 'orange'} style={{ marginLeft: 8, fontSize: 11 }}>
                  {PARSE_MODE_LABELS[parseMode]} 模式
                </Tag>
              </Text>
            </Col>
            <Col>
              <div className="parse-mode-control">
                <Text type="secondary" className="parse-mode-label">解析模式</Text>
                <Segmented
                  className="parse-mode-segmented"
                  options={PARSE_MODE_OPTIONS}
                  value={parseMode}
                  onChange={setParseMode}
                  disabled={loading}
                />
              </div>
            </Col>
            <Col>
              <Button type="primary" icon={<ThunderboltOutlined/>} size="large" loading={loading} onClick={handleParse} className="parse-btn">
                开始 {PARSE_MODE_LABELS[parseMode]} 解析
              </Button>
            </Col>
          </Row>
        </Card>
      )}

      {loading && (
        <Card className="loading-card">
          <Space direction="vertical" style={{width:'100%'}} align="center">
            <Text>正在解析，请稍候……</Text>
            <Progress percent={100} status="active" showInfo={false} style={{width:360}}/>
          </Space>
        </Card>
      )}
      {error && <Alert type="error" message="解析失败" description={error} showIcon closable style={{marginBottom:16}}/>}

      {/* 统计行 */}
      {parseResult && stats && (
        <Row gutter={12} className="stats-row">
          {statsItems.map(s => (
            <Col span={fileMode === 'csv' ? 4 : 4} key={s.title}>
              <Card className="stat-card"><Statistic title={s.title} value={s.value} prefix={s.icon}/></Card>
            </Col>
          ))}
        </Row>
      )}

      {/* 列角色识别（仅 CSV） */}
      {parseResult && fileMode === 'csv' && schema && (
        <Card className="schema-card" title="列角色识别结果">
          <Row gutter={16} align="middle" wrap>
            <Col><Text type="secondary">时间戳：</Text><Tag color="cyan">{schema.timestamp_col||'未识别'}</Tag></Col>
            <Col><Text type="secondary">级别：</Text><Tag color="purple">{schema.level_col||'未识别'}</Tag></Col>
            <Col><Text type="secondary">消息：</Text><Tag color="blue">{schema.message_col||'未识别'}</Tag></Col>
            <Col flex={1}><Text type="secondary">附加：</Text>{(schema.extra_cols||[]).map(c=><Tag key={c}>{c}</Tag>)}</Col>
            <Col>
              <Divider type="vertical"/>
              <Text type="secondary">质量：</Text>
              {Object.entries(qualityStats).map(([q,cnt]) => {
                const cfg={good:{color:'#52c41a',label:'全字段匹配'},warn:{color:'#faad14',label:'部分字段不符'},bad:{color:'#ff4d4f',label:'解析失败'},skipped:{color:'#8c8c8c',label:'跳过转换'}}[q]
                return cfg ? <span key={q} style={{color:cfg.color,marginLeft:8,fontSize:13}}>{cnt} {cfg.label}</span> : null
              })}
            </Col>
          </Row>
          {parseResult.csv_conversion?.warnings?.length > 0 && (
            <Alert type="warning" style={{marginTop:12}} message={parseResult.csv_conversion.warnings.join('；')} showIcon/>
          )}
        </Card>
      )}

      {/* 解析质量汇总（非 CSV 模式，解析后） */}
      {parseResult && fileMode === 'log' && (
        <Card className="schema-card" title={<Space><CodeOutlined />解析质量汇总</Space>}>
          <Row gutter={16} align="middle" wrap>
            <Col><Text type="secondary">文件格式：</Text><Tag color="blue">{(selectedFile?.name || '').split('.').pop()?.toUpperCase() || 'LOG'}</Tag></Col>
            <Col><Text type="secondary">解析条目：</Text><Tag color="cyan">{entries.length}</Tag></Col>
            <Divider type="vertical" />
            {Object.entries(logQualityStats).map(([q, cnt]) => {
              const cfg = {
                good: { color: '#52c41a', label: '全字段完整' },
                warn: { color: '#faad14', label: '字段部分缺失' },
                bad:  { color: '#ff4d4f', label: '消息体缺失' },
              }[q]
              return cfg
                ? <Col key={q}><span style={{ color: cfg.color, fontSize: 13 }}>{cnt} 条{cfg.label}</span></Col>
                : null
            })}
          </Row>
        </Card>
      )}

      {/* 准确率面板（仅 CSV） */}
      {fileMode === 'csv' && accuracy && <AccuracyPanel accuracy={accuracy} schema={schema}/>}

      {/* 提取完整度面板（非 CSV，解析后） */}
      {fileMode === 'log' && parseResult && entries.length > 0 && (
        <LogCompletenessPanel entries={entries} />
      )}

      {/* 模板统计（两种模式均展示） */}
      {parseResult && entries.length > 0 && (
        <TemplateStatsPanel entries={entries} />
      )}

      {/* 日志预览（非 CSV，解析前） */}
      {fileMode === 'log' && rawPreview && !parseResult && (
        <Card className="compare-card" title={
          <Space>
            <FileTextOutlined />原始日志预览
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              前 {rawPreview.sampleLines.length} 行 · 共 {rawPreview.lineCount} 行
            </Text>
          </Space>
        }>
          <pre className="log-preview-pre">
            {rawPreview.sampleLines.join('\n')}
            {rawPreview.lineCount > rawPreview.sampleLines.length && '\n…'}
          </pre>
        </Card>
      )}

      {/* CSV 对比表格 */}
      {fileMode === 'csv' && csvData && (
        <Card className="compare-card" title={
          <Space>
            <TableOutlined/>对比详情
            <Text type="secondary" style={{fontSize:12,fontWeight:400}}>
              {mergedData.length} 行 · 点击行左侧 ▶ 展开字段级对比详情
              {!parseResult && ' · 点击"开始 LILAC 解析"查看结果'}
            </Text>
          </Space>
        }>
          {mergedData.length === 0 ? <Empty description="暂无数据"/> : (
            <Table
              columns={columns}
              dataSource={pagedData}
              expandable={parseResult ? {
                expandedRowRender: rec => (
                  <div className="entry-detail">
                    <FieldDetailTable checks={rec.fieldChecks} />
                    {rec.entry && (
                      <FullTemplateBlock
                        template={rec.entry.template}
                        templateSource={rec.entry.template_source}
                      />
                    )}
                  </div>
                ),
                rowExpandable: rec => rec.fieldChecks?.length > 0 || !!rec.entry?.template,
              } : undefined}
              pagination={{
                current:page, pageSize:PAGE_SIZE, total:mergedData.length,
                onChange:setPage, showTotal:(t,r)=>`${r[0]}-${r[1]} / ${t} 行`, showSizeChanger:false,
              }}
              scroll={{ x:'max-content', y:440 }}
              size="small" className="compare-table" bordered
            />
          )}
        </Card>
      )}

      {/* 非 CSV 对比表格（解析后） */}
      {fileMode === 'log' && parseResult && (
        <Card className="compare-card" title={
          <Space>
            <TableOutlined />对比详情
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              {logMergedData.length} 条 · 点击行左侧 ▶ 展开字段级提取详情
            </Text>
          </Space>
        }>
          {logMergedData.length === 0 ? <Empty description="暂无解析结果"/> : (
            <Table
              columns={logCompareColumns}
              dataSource={pagedLogData}
              expandable={{
                expandedRowRender: rec => <LogEntryFieldTable entry={rec.entry} />,
                rowExpandable: rec => !!rec.entry,
              }}
              pagination={{
                current: page, pageSize: PAGE_SIZE, total: logMergedData.length,
                onChange: setPage, showTotal: (t, r) => `${r[0]}-${r[1]} / ${t} 条`, showSizeChanger: false,
              }}
              scroll={{ x: 'max-content', y: 440 }}
              size="small" className="compare-table" bordered
            />
          )}
        </Card>
      )}
    </div>
  )
}

export default LogCompare
