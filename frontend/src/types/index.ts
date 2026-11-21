export type ProjectStatus = '复现中' | '实验中' | '待验证' | '已归档'
export type RiskLevel = 'high' | 'medium' | 'low'

export interface Project {
  id: string
  code: string
  name: string
  description: string
  status: ProjectStatus
  progress: number
  paperCount: number
  experimentCount: number
  updated: string
  nextTask: string
  tags: string[]
  accent: 'violet' | 'cyan' | 'amber' | 'blue'
}

export interface NewProjectInput {
  name: string
  description: string
  researchField: string
}

export interface Paper {
  id: string
  title: string
  authors: string
  venue: string
  year: number
  status: '已解析' | '解析中' | '待复核'
  confidence: number
  readTime: string
  tags: string[]
  summary: string
  contribution: string
}

export interface ProtocolStep {
  id: string
  title: string
  detail: string
  duration: string
  completed: boolean
}

export interface Protocol {
  id: string
  name: string
  project: string
  version: string
  updated: string
  readiness: number
  steps: ProtocolStep[]
}

export interface RiskItem {
  id: string
  level: RiskLevel
  title: string
  source: string
  detail: string
  status: '待处理' | '已忽略' | '已修复'
}

export interface Experiment {
  id: string
  name: string
  model: string
  dataset: string
  status: '运行中' | '已完成' | '已暂停'
  epochs: number[]
  trainLoss: number[]
  validationLoss: number[]
  baseline: number[]
  reproduced: number[]
  metric: string
  metricValue: string
  delta: string
}

export interface ResearchReport {
  id: string
  title: string
  type: '复现报告' | '实验简报' | '文献综述'
  updated: string
  status: '草稿' | '待审阅' | '已完成'
  abstract: string
  content: string
}
