'use client'
import { useEffect, useRef, useState } from 'react'
import type { Session } from '@/lib/contracts'
import { ShieldCheck } from 'lucide-react'

export interface AutoApplySettingProps {
  policy?: { enabled: boolean; confirmation_url: string }
  project?: string
  session?: Session
  disabled: boolean
  onRefresh: () => void
  showTitle?: boolean
}

export function AutoApplySetting({
  policy,
  project,
  session,
  disabled,
  onRefresh,
  showTitle = true,
}: AutoApplySettingProps) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [frameHeight, setFrameHeight] = useState(130)
  let url: URL | undefined
  try {
    const candidate = new URL(policy?.confirmation_url || '')
    if (
      candidate.origin === 'http://127.0.0.1:47832' &&
      candidate.pathname === '/policy/embed' &&
      !candidate.username &&
      !candidate.password &&
      !candidate.hash &&
      candidate.searchParams.get('project') === project
    ) {
      url = candidate
    }
  } catch {}

  const source = session?.csrf_token ? url?.href : undefined

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (
        event.origin !== session?.confirmation_origin ||
        event.source !== frame.current?.contentWindow
      ) {
        return
      }
      if (event.data?.type === 'tw:policy' && event.data.project === project) {
        onRefresh()
      }
      if (event.data?.type === 'tw:widget-size' && typeof event.data.height === 'number') {
        setFrameHeight(Math.max(90, Math.ceil(event.data.height) + 4))
      }
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [project, session?.confirmation_origin, onRefresh])

  if (!policy || !source) return null

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/40 p-4 space-y-3">
      {showTitle && (
        <div className="flex items-center justify-between gap-3 pb-2.5 border-b border-zinc-200/70 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
            <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
              Автоматическое применение результатов
            </span>
          </div>
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full font-medium shrink-0 ${
              policy.enabled
                ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                : 'bg-zinc-200/80 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400'
            }`}
          >
            {policy.enabled ? 'Включено' : 'Выключено'}
          </span>
        </div>
      )}

      <div
        inert={disabled}
        aria-disabled={disabled}
        className="w-full"
      >
        <iframe
          ref={frame}
          key={project}
          src={source}
          title="Настройка автоматического применения"
          sandbox="allow-forms allow-scripts allow-same-origin"
          className="w-full border-0 block"
          style={{ height: frameHeight }}
        />
      </div>
    </div>
  )
}
