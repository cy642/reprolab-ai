import { useMemo, useState } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { BookOpenText, GitBranch, X } from 'lucide-react'
import type { ProtocolStep } from '../../types/protocol'
import { Badge } from '../ui/Badge'
import { INFO_META, STATUS_META } from './meta'

interface ProtocolFlowProps {
  steps: ProtocolStep[]
  onSaveSteps: (steps: ProtocolStep[]) => Promise<void>
  onOpenEvidence: (evidenceId: string) => void
}

export function validateWorkflow(steps: ProtocolStep[]): string | null {
  const ids = new Set(steps.map((step) => step.step_id))
  if (ids.size !== steps.length) return '步骤 step_id 重复。'
  const graph = new Map<string, string[]>()
  for (const step of steps) {
    const dependencies: string[] = []
    for (const dependency of step.dependencies) {
      if (dependency === step.step_id) return `步骤 ${step.step_id} 不能依赖自身。`
      if (!ids.has(dependency)) return `步骤 ${step.step_id} 依赖不存在的 ${dependency}。`
      dependencies.push(dependency)
    }
    graph.set(step.step_id, dependencies)
  }
  const indegree = new Map([...graph].map(([id, dependencies]) => [id, dependencies.length]))
  const dependents = new Map([...graph].map(([id]) => [id, [] as string[]]))
  for (const [id, dependencies] of graph) {
    for (const dependency of dependencies) dependents.get(dependency)?.push(id)
  }
  const queue = [...indegree].filter(([, degree]) => degree === 0).map(([id]) => id)
  let visited = 0
  while (queue.length) {
    const current = queue.shift()!
    visited += 1
    for (const dependent of dependents.get(current) ?? []) {
      const degree = (indegree.get(dependent) ?? 1) - 1
      indegree.set(dependent, degree)
      if (degree === 0) queue.push(dependent)
    }
  }
  return visited === steps.length ? null : '实验步骤存在循环依赖，已阻止保存。'
}

function layoutSteps(steps: ProtocolStep[]): Map<string, { x: number; y: number }> {
  const byId = new Map(steps.map((step) => [step.step_id, step]))
  const levels = new Map<string, number>()
  const remaining = new Set(steps.map((step) => step.step_id))
  while (remaining.size) {
    let progressed = false
    for (const stepId of [...remaining]) {
      const step = byId.get(stepId)!
      if (step.dependencies.every((dependency) => levels.has(dependency) || !remaining.has(dependency))) {
        const level = step.dependencies.length
          ? Math.max(...step.dependencies.map((dependency) => levels.get(dependency) ?? -1)) + 1
          : 0
        levels.set(stepId, level)
        remaining.delete(stepId)
        progressed = true
      }
    }
    if (!progressed) {
      for (const stepId of remaining) levels.set(stepId, 0)
      break
    }
  }
  const positions = new Map<string, { x: number; y: number }>()
  const grouped = new Map<number, ProtocolStep[]>()
  for (const step of steps) {
    const level = levels.get(step.step_id) ?? 0
    const group = grouped.get(level) ?? []
    group.push(step)
    grouped.set(level, group)
  }
  for (const [level, group] of grouped) {
    group.sort((a, b) => a.order_no - b.order_no).forEach((step, index) => {
      positions.set(step.step_id, { x: level * 290, y: index * 150 })
    })
  }
  return positions
}

function StepNodeCard({ data, selected }: NodeProps) {
  const step = data.step as ProtocolStep
  const info = INFO_META[step.information_type]
  const status = STATUS_META[step.status]
  return (
    <div className={`w-[230px] rounded-xl border bg-[#121A2B] p-3 shadow-lg ${selected ? 'border-primary' : 'border-white/15'}`}>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-accent !bg-canvas" />
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/15 font-mono text-[10px] text-primary">{step.order_no}</span>
        <p className="min-w-0 flex-1 truncate text-xs font-medium text-ink">{step.title}</p>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        <Badge tone={status.tone}>{status.label}</Badge>
        <Badge tone={info.tone}>{info.label}</Badge>
      </div>
      <p className="mt-2 font-mono text-[9px] text-muted">{step.step_id} · {step.evidence_refs.length} 条证据</p>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-primary !bg-canvas" />
    </div>
  )
}

const nodeTypes = { protocolStep: StepNodeCard }

export function ProtocolFlow({ steps, onSaveSteps, onOpenEvidence }: ProtocolFlowProps) {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(steps[0]?.step_id ?? null)
  const [selectedEdge, setSelectedEdge] = useState<{ source: string; target: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const graphError = useMemo(() => validateWorkflow(steps), [steps])
  const selectedStep = steps.find((step) => step.step_id === selectedStepId) ?? null

  const nodes = useMemo<Node[]>(() => {
    const positions = layoutSteps(steps)
    return steps.map((step) => ({
      id: step.step_id,
      type: 'protocolStep',
      position: positions.get(step.step_id) ?? { x: 0, y: 0 },
      data: { step },
      selected: step.step_id === selectedStepId,
      draggable: false,
    }))
  }, [steps, selectedStepId])

  const edges = useMemo<Edge[]>(() => steps.flatMap((step) => step.dependencies.map((dependency) => ({
    id: `${dependency}->${step.step_id}`,
    source: dependency,
    target: step.step_id,
    animated: step.status === 'running',
    style: { stroke: selectedEdge?.source === dependency && selectedEdge.target === step.step_id ? '#22D3EE' : '#64748B', strokeWidth: 1.5 },
    markerEnd: { type: MarkerType.ArrowClosed, color: '#8B5CF6' },
  }))), [steps, selectedEdge])

  const saveDependencies = async (nextSteps: ProtocolStep[]) => {
    const validationError = validateWorkflow(nextSteps)
    if (validationError) {
      setError(validationError)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSaveSteps(nextSteps)
      setSelectedEdge(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '依赖保存失败。')
    } finally {
      setSaving(false)
    }
  }

  const connect = (connection: Connection) => {
    if (!connection.source || !connection.target) return
    const next = steps.map((step) => step.step_id === connection.target && !step.dependencies.includes(connection.source!)
      ? { ...step, dependencies: [...step.dependencies, connection.source!] }
      : step)
    void saveDependencies(next)
  }

  const removeDependency = (source: string, target: string) => {
    const next = steps.map((step) => step.step_id === target
      ? { ...step, dependencies: step.dependencies.filter((dependency) => dependency !== source) }
      : step)
    void saveDependencies(next)
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[10px] text-muted">
        <GitBranch size={13} className="text-primary" />
        从右侧节点Handle拖到下游节点可新增依赖；点击边后可删除。
        {saving && <Badge tone="cyan">保存中</Badge>}
        {(error || graphError) && <Badge tone="red">{error || graphError}</Badge>}
      </div>
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_250px]">
        <div className="h-[500px] overflow-hidden rounded-xl border border-white/[.07] bg-canvas/45" data-testid="protocol-dag">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onConnect={connect}
            onNodeClick={(_, node) => setSelectedStepId(node.id)}
            onEdgeClick={(_, edge) => setSelectedEdge({ source: edge.source, target: edge.target })}
            fitView
            minZoom={0.35}
            maxZoom={1.4}
            nodesDraggable={false}
            deleteKeyCode={null}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#273449" />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable className="!bg-[#0B1020]" nodeColor="#8B5CF6" maskColor="rgba(5,9,20,.75)" />
          </ReactFlow>
        </div>
        <aside className="rounded-xl border border-white/[.07] bg-canvas/35 p-4">
          {selectedStep ? (
            <div>
              <p className="font-mono text-[9px] uppercase tracking-[.14em] text-primary">STEP DETAIL</p>
              <h3 className="mt-2 text-sm font-medium text-ink">{selectedStep.title}</h3>
              <p className="mt-2 text-[11px] leading-6 text-muted">{selectedStep.description || '暂无描述'}</p>
              <div className="mt-3 space-y-2 text-[10px]">
                <p className="text-muted">输入：{selectedStep.required_inputs.join('、') || '—'}</p>
                <p className="text-muted">输出：{selectedStep.expected_outputs.join('、') || '—'}</p>
              </div>
              <div className="mt-4">
                <p className="font-mono text-[9px] uppercase tracking-[.12em] text-muted">DEPENDENCIES</p>
                <div className="mt-2 space-y-1.5">
                  {selectedStep.dependencies.length === 0 && <p className="text-[10px] text-muted">无前置依赖</p>}
                  {selectedStep.dependencies.map((dependency) => (
                    <button key={dependency} onClick={() => removeDependency(dependency, selectedStep.step_id)} className="flex w-full items-center justify-between rounded border border-white/[.07] px-2 py-1.5 font-mono text-[9px] text-muted hover:border-danger/30 hover:text-danger">
                      {dependency}<X size={11} />
                    </button>
                  ))}
                </div>
              </div>
              {selectedStep.evidence_refs.length > 0 && (
                <div className="mt-4">
                  <p className="font-mono text-[9px] uppercase tracking-[.12em] text-muted">EVIDENCE</p>
                  <div className="mt-2 space-y-1.5">
                    {selectedStep.evidence_refs.map((reference) => (
                      <button key={reference} onClick={() => onOpenEvidence(reference)} className="flex w-full items-center gap-2 rounded border border-accent/15 bg-accent/[.04] px-2 py-1.5 text-left font-mono text-[9px] text-accent hover:border-accent/35">
                        <BookOpenText size={11} />{reference}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : <p className="text-xs text-muted">点击节点查看步骤详情。</p>}
          {selectedEdge && (
            <button onClick={() => removeDependency(selectedEdge.source, selectedEdge.target)} className="mt-4 w-full rounded-lg border border-danger/20 px-3 py-2 text-[10px] text-danger hover:bg-danger/[.05]">
              删除依赖 {selectedEdge.source} → {selectedEdge.target}
            </button>
          )}
        </aside>
      </div>
    </div>
  )
}
