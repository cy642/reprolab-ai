import { BookOpenText, ChartNoAxesCombined, FileText, GitBranch, LayoutDashboard, ListChecks, ShieldCheck, type LucideIcon } from 'lucide-react'

export interface NavigationItem {
  path: string
  label: string
  english: string
  icon: LucideIcon
}

export const navigationItems: NavigationItem[] = [
  { path: '/', label: '科研工作台', english: 'Research Hub', icon: LayoutDashboard },
  { path: '/workflows', label: '工作流编排', english: 'Research Workflow', icon: GitBranch },
  { path: '/papers', label: '论文理解', english: 'Paper Intelligence', icon: BookOpenText },
  { path: '/protocols', label: '实验方案', english: 'Protocol Builder', icon: ListChecks },
  { path: '/guardian', label: '数据审计', english: 'Data Guardian', icon: ShieldCheck },
  { path: '/insights', label: '实验分析', english: 'Experiment Insight', icon: ChartNoAxesCombined },
  { path: '/reports', label: '科研报告', english: 'Research Report', icon: FileText },
]
