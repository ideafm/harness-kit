'use client'
import React from 'react'
import type { Session, Task, Transport } from '@/lib/contracts'
import { loopbackUrl } from '@/lib/controller-links'
import { useProjectView } from '@/hooks/use-project-view'
import { Button } from './ui/button'
import { AppIcon } from './app-icon'

interface ProjectPreviewBarProps {
  transport: Transport
  session?: Session
  enabled?: boolean
  tasks?: Task[]
  className?: string
}

export function ProjectPreviewBar({
  transport,
  session,
  enabled = true,
  tasks = [],
  className = ''
}: ProjectPreviewBarProps) {
  const state = useProjectView(transport, undefined, enabled, session?.csrf_token)
  const v = state.data?.view

  const activeId = v?.active_task ?? v?.requested?.task
  const activeMode = v?.mode ?? v?.requested?.mode
  const activeTask = activeId
    ? tasks.find(t => t.id === activeId)
    : tasks.length === 1
    ? tasks[0]
    : undefined

  const preview = activeTask?.preview
  const url = loopbackUrl(preview?.url)
  const modern = preview && ['persistent', 'current', 'mode', 'version'].some(key => key in preview)
  const validPreview = url && (!modern || (preview?.persistent === true && preview.current === true && preview.read_only === true && state.ready && preview.mode === v?.mode && typeof preview.version === 'string' && preview.version === v?.source_digest))
  const address = loopbackUrl(v?.url)

  const fallback = !preview && state.ready && address && activeId && v?.source_digest ? new URL(address.href) : undefined
  if (fallback) {
    fallback.searchParams.set('__tw_task', String(activeId))
    fallback.searchParams.set('__tw_version', v!.source_digest!)
  }
  const openUrl = validPreview ? url : fallback

  const writable = enabled && Boolean(session?.csrf_token?.trim())
  const stopping = state.pending?.body.action === 'stop'
  const running = Boolean(v?.running)
  const preparing = !stopping && (state.busy || Boolean(v?.building) || Boolean(state.waiting && !state.ready))

  const error = state.error || (v?.error ? (typeof v.error === 'string' ? v.error : v.error.message) : '')
  const hasSelection = Boolean(activeId && (state.data?.available || running))

  const statusLabel = error
    ? 'Ошибка'
    : stopping
    ? 'Останавливаем…'
    : preparing
    ? 'Запускается'
    : running
    ? 'Запущен'
    : 'Остановлен'

  const indicator = error
    ? 'bg-rose-500'
    : stopping || preparing || state.stale
    ? 'bg-amber-400 animate-pulse'
    : running
    ? 'bg-emerald-500'
    : 'bg-zinc-400 dark:bg-zinc-500'

  const resultLabel = activeId
    ? `TASK-${String(activeId).padStart(3, '0')} · ${activeMode === 'working' ? 'рабочая версия' : 'проверенная версия'}`
    : 'Версия не выбрана'

  const canStart = writable && !running && !preparing && state.canSend && hasSelection
  const canStop = writable && running && !stopping && state.canSend && Boolean(state.data?.actions?.includes('stop'))

  return (
    <div
      className={`preview-control-bar flex flex-wrap sm:flex-nowrap items-center justify-between sm:justify-start gap-2.5 sm:gap-3 px-3 py-1.5 rounded-xl border border-zinc-200/90 dark:border-zinc-800 bg-white/90 dark:bg-zinc-900/90 text-xs shadow-2xs ${className}`}
      aria-label="Управление приложением проекта"
    >
      {/* Status & Active Result Subtitle */}
      <div className="flex flex-col min-w-0 justify-center">
        <div className="flex items-center gap-1.5 font-medium leading-tight">
          <span className={`size-1.5 rounded-full shrink-0 ${indicator}`} />
          <span className="text-zinc-900 dark:text-zinc-100 font-semibold whitespace-nowrap" role="status">
            {statusLabel}
          </span>
          {running && address && (
            <span className="font-mono text-[11px] text-zinc-500 dark:text-zinc-400 hidden sm:inline truncate">
              {address.host}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 leading-tight mt-0.5 min-w-0">
          <span
            className="text-[10px] sm:text-[11px] text-zinc-500 dark:text-zinc-400 truncate max-w-[180px] sm:max-w-[260px]"
            title={resultLabel}
          >
            {resultLabel}
          </span>
          {error && (
            <span
              className="text-[10px] text-rose-500 dark:text-rose-400 truncate max-w-[140px]"
              title={error}
            >
              · {error}
            </span>
          )}
        </div>
      </div>

      <div className="hidden sm:block h-6 w-px bg-zinc-200 dark:bg-zinc-800 my-auto shrink-0" />

      {/* Action Buttons: Запустить, Остановить, Открыть */}
      <div className="flex items-center gap-1.5 shrink-0">
        {writable && (
          <>
            <Button
              size="sm"
              variant="outline"
              className="h-7 sm:h-8 px-2 sm:px-2.5 text-xs gap-1 sm:gap-1.5 rounded-md"
              disabled={!canStart}
              title={
                !hasSelection
                  ? 'Сначала выберите результат в карточке задачи'
                  : running
                  ? 'Приложение уже запущено'
                  : preparing
                  ? 'Идёт запуск приложения'
                  : 'Запустить просмотр приложения'
              }
              onClick={() => void state.send('select', activeMode ?? 'checked')}
            >
              <AppIcon name="play" width="13" height="13" />
              <span>{preparing ? 'Запускается…' : 'Запустить'}</span>
            </Button>

            <Button
              size="sm"
              variant="outline"
              className="h-7 sm:h-8 px-2 sm:px-2.5 text-xs gap-1 sm:gap-1.5 rounded-md"
              disabled={!canStop}
              title={
                !running
                  ? 'Приложение не запущено'
                  : stopping
                  ? 'Останавливаем приложение…'
                  : 'Остановить приложение'
              }
              onClick={() => void state.send('stop', activeMode ?? 'checked')}
            >
              <AppIcon name="stop" width="13" height="13" />
              <span>{stopping ? 'Останавливаем…' : 'Остановить'}</span>
            </Button>
          </>
        )}

        {openUrl ? (
          <a
            href={openUrl.href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-7 sm:h-8 items-center justify-center gap-1 sm:gap-1.5 rounded-md bg-blue-600 px-2 sm:px-2.5 text-xs font-medium text-white shadow-2xs transition-colors hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
            style={{ color: 'white' }}
            aria-label="Открыть результат"
            title="Открыть приложение в новой вкладке"
          >
            <span>Открыть</span>
            <AppIcon name="external" width="13" height="13" />
          </a>
        ) : writable ? (
          <Button
            size="sm"
            variant="outline"
            className="h-7 sm:h-8 px-2 sm:px-2.5 text-xs gap-1 sm:gap-1.5 rounded-md"
            disabled
            title="Открытие станет доступно после подтверждения готовности результата"
          >
            <span>Открыть</span>
            <AppIcon name="external" width="13" height="13" />
          </Button>
        ) : null}
      </div>
    </div>
  )
}
