import { useState } from 'react'
import type { FormEvent } from 'react'
import { API_BASE_URL, getDemoAccessCode, setDemoAccessCode } from '../../lib/api'

export function HostedDemoAccess() {
  const [unlocked] = useState(() => Boolean(getDemoAccessCode()))
  const [code, setCode] = useState('')
  const [message, setMessage] = useState('')
  const [checking, setChecking] = useState(false)

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const accessCode = code.trim()
    setChecking(true)
    setMessage('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/demo/access`, {
        headers: { Authorization: `Bearer ${accessCode}` },
      })
      if (!response.ok) throw new Error('访问码无效或服务暂不可用。')
      setDemoAccessCode(accessCode)
      window.location.reload()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '无法验证访问码。')
    } finally {
      setChecking(false)
    }
  }

  return (
    <section className="mb-5 rounded-xl border border-primary/25 bg-primary/[.06] p-4 text-xs text-ink" aria-label="在线演示访问">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p>{unlocked ? '实时演示已解锁。只使用公开论文和模拟数据。' : '公开演示 · 可浏览预置案例和报告。上传、执行和实时模型调用需输入演示访问码。'}</p>
        {unlocked && <button className="text-primary" onClick={() => { setDemoAccessCode(''); window.location.reload() }}>返回公开演示</button>}
      </div>
      {!unlocked && (
        <details className="mt-2">
          <summary className="cursor-pointer text-primary">解锁实时演示</summary>
          <form className="mt-3 flex flex-wrap items-center gap-2" onSubmit={(event) => void unlock(event)}>
            <input aria-label="演示访问码" type="password" autoComplete="off" value={code} onChange={(event) => setCode(event.target.value)} className="rounded-md border border-white/15 bg-canvas px-3 py-2" placeholder="演示访问码" required />
            <button disabled={checking} className="rounded-md bg-primary/20 px-3 py-2 text-primary" type="submit">{checking ? '正在验证…' : '解锁'}</button>
            {message && <span role="alert" className="text-warning">{message}</span>}
          </form>
        </details>
      )}
    </section>
  )
}
