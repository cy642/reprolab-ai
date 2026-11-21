import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, FlaskConical } from 'lucide-react'
import { useWorkspace } from '../../hooks/useWorkspace'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

export function CreateProjectModal({ open, onClose, onCreated }: {
  open: boolean
  onClose: () => void
  onCreated: (name: string) => void
}) {
  const { createProject } = useWorkspace()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [researchField, setResearchField] = useState('图机器学习')

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    const project = createProject({ name, description, researchField })
    setName('')
    setDescription('')
    onClose()
    onCreated(project.name)
    navigate('/')
  }

  return (
    <Modal open={open} onClose={onClose} title="创建科研项目" description="从研究问题开始，逐步构建可验证、可复现的实验链路。">
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="flex items-center gap-3 rounded-xl border border-primary/15 bg-primary/[.055] p-3.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary"><FlaskConical size={18} /></span>
          <p className="text-[11px] leading-5 text-muted">项目将使用演示工作区，本地创建后可立即切换与查看。</p>
        </div>
        <label className="block text-xs font-medium text-ink">项目名称 <span className="text-danger">*</span>
          <input autoFocus value={name} onChange={(event) => setName(event.target.value)} className="field mt-2" placeholder="例如：图神经网络分子性质预测" maxLength={60} required />
        </label>
        <label className="block text-xs font-medium text-ink">研究方向
          <select value={researchField} onChange={(event) => setResearchField(event.target.value)} className="field mt-2">
            <option>图机器学习</option><option>自然语言处理</option><option>计算机视觉</option><option>生物信息学</option><option>其他方向</option>
          </select>
        </label>
        <label className="block text-xs font-medium text-ink">研究目标
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} className="field mt-2 min-h-24 resize-none" placeholder="简述需要复现的论文、核心假设或验证目标…" maxLength={240} />
          <span className="mt-1.5 block text-right font-mono text-[9px] text-muted">{description.length}/240</span>
        </label>
        <div className="flex justify-end gap-2 border-t border-white/[.06] pt-5">
          <Button onClick={onClose}>取消</Button>
          <Button type="submit" variant="primary" disabled={!name.trim()} icon={<ArrowRight size={15} />}>创建并进入项目</Button>
        </div>
      </form>
    </Modal>
  )
}
