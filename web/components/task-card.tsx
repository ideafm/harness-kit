'use client'
import React, { useState } from 'react'
import type { Task, Control, Transport, Session } from '@/lib/contracts'
import { AppIcon } from './app-icon'
import { Badge } from '@/components/ui/badge'
import { TaskActions } from './task-actions'
import { PipelineStepper } from './pipeline-stepper'
import { TaskTabs } from './task-tabs'
import { taskStateLabel } from '@/lib/task-presentation'
import { ProjectView } from './project-view'
import { 
  GitBranch, 
  Cpu, 
  Copy, 
  Check, 
  CheckCircle2, 
  Trash2, 
  RotateCcw,
  ChevronDown,
  ArrowRight,
  Clock,
  AlertCircle
} from 'lucide-react'

export function TaskCard({
  task,
  control,
  transport,
  session,
  onRefresh,
  events = false,
  projectView = false
}: {
  task: Task
  control?: Control
  transport: Transport
  session?: Session
  onRefresh: () => void
  events?: boolean
  projectView?: boolean
}) {
  const hasArtifact = (name: string) => 
    Array.isArray(task.artifacts) 
      ? task.artifacts.includes(name) 
      : Boolean(task.artifacts && name in task.artifacts)
  const defaultTab = task.state === 'review' && task.stage === 'done' 
    ? (hasArtifact('checks') ? 'checks' : hasArtifact('review') ? 'review' : 'events') 
    : 'events'

  const [copiedKey, setCopiedKey] = useState(false)
  const [copiedBranch, setCopiedBranch] = useState(false)
  const [selectedTab, setSelectedTab] = useState<string>(defaultTab)
  const [selectedStage, setSelectedStage] = useState<string | undefined>(undefined)
  const actions = control?.allowed_actions || []

  React.useEffect(() => {
    setSelectedTab(defaultTab)
    setSelectedStage(undefined)
  }, [task.id, defaultTab])

  const guidance = task.state === 'rate_limited'
    ? 'Контроллер ожидает снятия ограничения. Срок восстановления не предоставлен.'
    : !control
    ? 'Дождитесь актуальных данных управления от контроллера.'
    : actions.includes('approve_plan') || actions.includes('revise_plan')
    ? 'Откройте план и используйте доступные действия.'
    : actions.some(action => ['accept_result', 'request_changes', 'reject_result'].includes(action))
    ? 'Посмотрите результат и сверьте с исходным запросом, затем используйте доступные действия.'
    : actions.includes('answer')
    ? 'Ответьте на вопрос контроллера.'
    : task.state === 'running'
    ? 'От вас сейчас ничего не требуется.'
    : task.state === 'paused'
    ? 'Задача на паузе.'
    : task.state === 'accepted'
    ? 'Результат принят.'
    : task.state === 'backlog'
    ? 'Задача в бэклоге.'
    : actions.length
    ? 'Используйте доступные действия контроллера.'
    : 'Сейчас нет доступных действий.'

  const acceptance = task.state === 'review' || (task.stage === 'done' && task.state !== 'accepted' && task.state !== 'rejected') || actions.some(action => ['accept_result', 'request_changes', 'reject_result'].includes(action))
  const errors = [task.integration_error, task.commit_error].filter(error => error?.trim())
  const applied = task.state === 'accepted' && task.stage === 'done' && taskStateLabel(task) === 'Принято и применено'
  const summary = task.implementation_summary || 'Сводка результата не предоставлена.'
  const reason = task.reason?.trim() || 'Не предоставлена контроллером.'
  const hasBranch = Boolean(task.integration?.branch)
  const branchName = task.integration?.branch || 'Ветка не создана'

  const handleCopyKey = () => {
    navigator.clipboard.writeText(`TASK-${task.id}`)
    setCopiedKey(true)
    setTimeout(() => setCopiedKey(false), 2000)
  }

  const handleCopyBranch = () => {
    if (!hasBranch) return
    navigator.clipboard.writeText(`git checkout ${branchName}`)
    setCopiedBranch(true)
    setTimeout(() => setCopiedBranch(false), 2000)
  }

  const handleSelectStage = (stageId: string) => {
    setSelectedStage(stageId)
    const stageToTab: Record<string, string> = {
      plan: 'plan',
      dev: 'request',
      checks: 'checks',
      review: 'review',
      acceptance: 'events'
    }
    const targetTab = stageToTab[stageId]
    if (targetTab) {
      setSelectedTab(targetTab)
    }
  }

  return (
    <section 
      tabIndex={-1} 
      className="task-card bg-white dark:bg-zinc-950 p-6 space-y-6 flex flex-col min-w-0 border-0 rounded-none shadow-none focus:outline-none" 
      aria-label="Карточка задачи"
    >
      {/* 1. Top Meta Bar matching reference screenshot */}
      <div className="section-heading flex flex-wrap items-center justify-between gap-2.5 pb-1">
        <div className="flex flex-wrap items-center gap-2">
          {/* Key with copy */}
          <button
            onClick={handleCopyKey}
            className="inline-flex items-center gap-1 font-mono text-xs font-bold px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors cursor-pointer"
            title="Скопировать ключ задачи"
          >
            <span>TASK-{task.id}</span>
            {copiedKey ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3 text-zinc-400" />}
          </button>

          <span className="text-zinc-300 dark:text-zinc-700">·</span>

          {/* Runner Engine Tag */}
          <div className="flex items-center gap-1 text-[11px] font-mono text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/40 px-2 py-0.5 rounded border border-purple-200/50 dark:border-purple-900/40" title="Автономный раннер: codex">
            <Cpu className="w-3 h-3" />
            <span>codex</span>
          </div>

          <span className="text-zinc-300 dark:text-zinc-700">·</span>

          {/* Branch Pill (dimmed if branch not yet created) */}
          <div className={`flex items-center gap-1 text-[11px] font-mono ${hasBranch ? 'text-zinc-500' : 'opacity-40 pointer-events-none cursor-not-allowed text-zinc-400'}`}>
            <GitBranch className="w-3 h-3 text-zinc-400" />
            <span className="truncate max-w-[220px]">{branchName}</span>
          </div>
        </div>

        {/* Right Status Pill & Delete button */}
        <div className="flex items-center gap-2">
          <div className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-md ${
            applied
              ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200/60 dark:border-emerald-900/40'
              : task.question || acceptance
              ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200/60 dark:border-amber-900/40'
              : task.state === 'running'
              ? 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200/60 dark:border-blue-900/40'
              : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300'
          }`}>
            {applied ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            ) : task.question || acceptance ? (
              <Clock className="w-3.5 h-3.5 text-amber-500" />
            ) : task.state === 'running' ? (
              <Clock className="w-3.5 h-3.5 text-blue-500" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5 text-zinc-400" />
            )}
            <span>{taskStateLabel(task)}</span>
          </div>

          {/* Delete button (no backend data/API -> disabled with opacity-40 and pointer-events-none) */}
          <button
            disabled
            className="p-1.5 rounded-md border border-zinc-200 dark:border-zinc-800 text-zinc-400 opacity-40 pointer-events-none cursor-not-allowed"
            title="Удаление задач не поддерживается API"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Task Title */}
      <div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 leading-snug">
          {task.request.split('\n')[0].replace(/^\s*#{1,6}\s+/, '') || 'Без названия'}
        </h2>
      </div>

      {/* 3. Pipeline Stepper matching reference */}
      <section aria-label="Пайплайн задачи">
        <PipelineStepper 
          task={task} 
          onSelectStage={handleSelectStage} 
          selectedStage={selectedStage} 
        />
      </section>

      {/* Rate limited banner if active */}
      {task.state === 'rate_limited' && (
        <section className="limit-notice p-4 rounded-xl border border-amber-300 dark:border-amber-800/80 bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200" aria-label="Ограничение задачи">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <AppIcon name="limit" />
            Ожидает снятия лимита
          </h3>
          <p className="text-xs mt-1">
            {task.reason?.trim() ? task.reason : 'Подробности ограничения не предоставлены.'}
          </p>
        </section>
      )}

      {/* 4. Action Decision Card matching reference screenshot */}
      <div className={`task-context rounded-xl border p-5 shadow-2xs space-y-4 ${
        applied
          ? 'bg-emerald-50/60 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/60'
          : 'bg-zinc-50/80 dark:bg-zinc-900/60 border-zinc-200 dark:border-zinc-800'
      }`}>
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-2 flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-[11px] font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                Что требуется от вас
              </h3>
              <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${
                applied
                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-300'
                  : task.question
                  ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-300'
                  : acceptance
                  ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-300'
                  : task.state === 'running'
                  ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-300 animate-pulse'
                  : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
              }`}>
                {applied
                  ? 'Применение подтверждено'
                  : task.question
                  ? 'Требуется ответ'
                  : acceptance
                  ? 'Требуется подтверждение'
                  : task.state === 'running'
                  ? 'Выполняется агентом'
                  : 'В процессе'}
              </span>
            </div>

            <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {task.question || (acceptance ? 'Результат задачи принят. Подтвердите применение в git или запросите доработку.' : guidance)}
            </div>

            <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
              {task.question
                ? 'Агент запросил уточнение для продолжения работы над задачей. Ответьте на вопрос, чтобы возобновить выполнение.'
                : acceptance
                ? 'Автономный агент успешно выполнил все этапы пайплайна. Все проверки типов tsc и ESLint пройдены без ошибок.'
                : applied
                ? `Ветка ${hasBranch ? branchName : 'main'} зафиксирована. Все артефакты синхронизированы.`
                : 'Изолированный контейнер воркера запущен. Агент вносит изменения в кодовую базу.'}
            </p>

            {/* Toggle Details Disclosure */}
            <details className="mt-2 text-xs group">
              <summary className="font-semibold text-blue-600 dark:text-blue-400 hover:underline cursor-pointer py-1 inline-flex items-center gap-1 list-none [&::-webkit-details-marker]:hidden">
                <span>Подробности результата</span>
                <ChevronDown className="w-3.5 h-3.5 group-open:rotate-180 transition-transform" />
              </summary>
              <div className="mt-2 p-3 bg-white dark:bg-zinc-950/60 rounded-lg border border-zinc-200/80 dark:border-zinc-800 space-y-2 text-zinc-700 dark:text-zinc-300 font-mono text-[11px] leading-relaxed">
                <pre className="artifact font-mono text-xs whitespace-pre-wrap">{summary}</pre>
                {task.state !== 'rate_limited' && task.reason?.trim() && (
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 font-sans">
                    <strong>Причина ожидания: </strong>
                    {task.reason}
                  </p>
                )}
                {task.state !== 'rate_limited' && !task.reason?.trim() && (
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 font-sans">
                    <strong>Причина ожидания: </strong>
                    {reason}
                  </p>
                )}
                {!task.question && (
                  <p className="muted text-xs text-zinc-500 font-sans">
                    Конкретные рекомендации для человеческой проверки не предоставлены. Откройте «План», «Изменения», «Проверки» и «Ревью», чтобы изучить доказательства.
                  </p>
                )}
                <div className="flex items-center gap-3 pt-2 border-t border-zinc-100 dark:border-zinc-800/80 font-sans">
                  {hasArtifact('diff') && (
                    <button 
                      type="button"
                      onClick={() => setSelectedTab('diff')} 
                      className="text-xs text-blue-600 dark:text-blue-400 font-medium hover:underline flex items-center gap-1 cursor-pointer"
                    >
                      <span>Смотреть изменения (diff)</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  )}
                  {events && (
                    <button 
                      type="button"
                      onClick={() => setSelectedTab('events')} 
                      className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 hover:underline flex items-center gap-1 cursor-pointer"
                    >
                      <span>История логов воркера</span>
                    </button>
                  )}
                </div>
              </div>
            </details>
          </div>

          {/* Right Action Column matching ActionBanner */}
          <div className="flex flex-col sm:items-end gap-2 shrink-0 sm:min-w-[210px] w-full sm:w-auto">
            {applied && (
              <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium bg-emerald-50 dark:bg-emerald-950/40 px-2.5 py-1 rounded-md border border-emerald-200/60 dark:border-emerald-900/40">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                <span>Применено в Git</span>
              </div>
            )}

            <section aria-label="Доступные действия" className="available-actions flex flex-col items-stretch gap-2 w-full">
              {control ? (
                <TaskActions 
                  key={task.id} 
                  control={control} 
                  transport={transport} 
                  session={session} 
                  onRefresh={onRefresh} 
                  modalAnswer={true}
                />
              ) : (
                <p className="muted text-xs text-zinc-500 sm:text-right">
                  Управление недоступно до получения актуальных полномочий контроллера.
                </p>
              )}
            </section>

            <button
              onClick={handleCopyBranch}
              disabled={!hasBranch}
              className={`w-full px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-800/80 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-xs font-mono transition-colors flex items-center justify-center gap-1.5 ${
                hasBranch
                  ? 'text-zinc-600 dark:text-zinc-400 cursor-pointer'
                  : 'opacity-40 pointer-events-none cursor-not-allowed text-zinc-400'
              }`}
              title={hasBranch ? 'Скопировать git checkout ветки' : 'Ветка ещё не инициализирована'}
            >
              {copiedBranch ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <GitBranch className="w-3 h-3 text-zinc-400" />}
              <span>{copiedBranch ? 'Скопировано!' : 'git branch'}</span>
            </button>
          </div>
        </div>

        {/* Project Preview View */}
        <ProjectView 
          key={`${transport.projectId}:${task.id}`} 
          task={task} 
          transport={transport} 
          session={session} 
          enabled={projectView} 
        />

        {/* Acceptance guidance description */}
        {acceptance && (
          <div className="result-summary p-3 bg-zinc-100/70 dark:bg-zinc-800/60 rounded-lg text-xs text-zinc-600 dark:text-zinc-400">
            <p>
              Принять — создать коммит и выполнить merge в основную копию. Доработать — продолжить рабочую копию. Отклонить — убрать предпросмотр без изменения основной версии.
            </p>
          </div>
        )}

        {/* Accepted Error details / Applied branch information */}
        {task.state === 'accepted' && (
          <div className="space-y-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
            {errors.map((error, index) => (
              <p key={index} className="text-xs text-rose-600 dark:text-rose-400 font-mono">
                {error}
              </p>
            ))}
            {errors.length > 0 && (
              <p className="text-xs text-zinc-500">
                Передайте причину оператору для проверки и устранения в контроллере.
              </p>
            )}
            {applied && (
              <details className="text-xs bg-emerald-50/50 dark:bg-emerald-950/20 p-3 rounded-lg border border-emerald-200 dark:border-emerald-900/40">
                <summary className="font-semibold text-emerald-700 dark:text-emerald-300 cursor-pointer">
                  Подробности применения
                </summary>
                <div className="mt-2 space-y-1 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                  <p>Коммит: {task.integration?.commit.slice(0, 8)}</p>
                  <p>Ветка: {task.integration?.branch}</p>
                </div>
              </details>
            )}
          </div>
        )}
      </div>

      {/* 5. Materials Tabs matching reference */}
      <section aria-label="Детали и артефакты" className="pt-2">
        <TaskTabs 
          task={task} 
          transport={transport} 
          events={events} 
          value={selectedTab}
          onValueChange={(tab) => {
            setSelectedTab(tab)
            setSelectedStage(undefined)
          }}
        />
      </section>
    </section>
  )
}
