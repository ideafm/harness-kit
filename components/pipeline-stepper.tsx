'use client'
import React from 'react'
import { 
  FileText, 
  Code2, 
  CheckSquare, 
  Eye, 
  ShieldCheck, 
  Check 
} from 'lucide-react'
import type { Task } from '@/lib/contracts'
import { taskProgress, taskStateLabel } from '@/lib/task-presentation'

export const STAGES_CONFIG = [
  { id: 'plan', label: 'План', defaultDuration: '14c', icon: FileText },
  { id: 'dev', label: 'Разработка', defaultDuration: '2m 41c', icon: Code2 },
  { id: 'checks', label: 'Проверки', defaultDuration: '38c', icon: CheckSquare },
  { id: 'review', label: 'Ревью', defaultDuration: '52c', icon: Eye },
  { id: 'acceptance', label: 'Приёмка', defaultDuration: 'ожидание', icon: ShieldCheck }
]

export function PipelineStepper({ 
  task, 
  onSelectStage,
  selectedStage 
}: { 
  task: Task
  onSelectStage?: (stageId: string) => void
  selectedStage?: string 
}) {
  const progress = taskProgress(task)
  const currentStageIndex = progress.index ?? 0
  const isAccepted = task.state === 'accepted'
  const progressPercent = isAccepted 
    ? 100 
    : Math.round((currentStageIndex / (STAGES_CONFIG.length - 1)) * 100)

  // Current action text
  const currentAction = task.state === 'review' && task.stage === 'done'
    ? 'Ожидается подтверждение оператора для слияния в main'
    : task.state === 'accepted'
    ? 'Изменения подтверждены и применены в ветку'
    : task.state === 'running'
    ? 'Агент выполняет автономную разработку'
    : task.state === 'rate_limited'
    ? 'Ожидание снятия лимита'
    : taskStateLabel(task)

  return (
    <div className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 shadow-2xs space-y-4">
      {/* Top Header: Title, Progress % and Current Stage */}
      <div className="flex items-center justify-between pb-2 border-b border-zinc-100 dark:border-zinc-800 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">
            Пайплайн автономной разработки
          </span>
          <span className="text-[11px] font-mono text-zinc-400">
            (5 фаз)
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-zinc-500 dark:text-zinc-400">
            Готовность: <span className="font-semibold text-blue-600 dark:text-blue-400">{progressPercent}%</span>
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 font-medium text-[11px]">
            <ShieldCheck className="w-3 h-3 text-blue-600 shrink-0" />
            <span className="truncate max-w-[120px]">{taskStateLabel(task)}</span>
          </span>
        </div>
      </div>

      {/* Main Stepper Track */}
      <div className="w-full">
        {/* Row of Circles with Connector Line */}
        <div className="relative flex items-center justify-between w-full h-9">
          <div className="absolute left-[18px] right-[18px] top-1/2 -translate-y-1/2 h-[2px] z-0 pointer-events-none overflow-hidden">
            <div className="w-full h-full bg-zinc-200 dark:bg-zinc-800" />
            <div 
              className="absolute left-0 top-0 h-full bg-blue-600 dark:bg-blue-500 transition-all duration-300"
              style={{
                width: isAccepted ? '100%' : `${(currentStageIndex / (STAGES_CONFIG.length - 1)) * 100}%`
              }}
            />
          </div>

          {/* Stepper Circle Buttons */}
          {STAGES_CONFIG.map((stage, idx) => {
            const isPassed = isAccepted || idx < currentStageIndex
            const isCurrent = !isAccepted && idx === currentStageIndex
            const isSelected = selectedStage === stage.id
            const isPending = !isPassed && !isCurrent
            const Icon = stage.icon

            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => onSelectStage?.(stage.id)}
                className={`relative z-10 w-9 h-9 rounded-full flex items-center justify-center transition-all duration-150 border-2 cursor-pointer focus:outline-none ${
                  isPassed
                    ? 'bg-emerald-500 border-emerald-500 text-white shadow-xs'
                    : isCurrent
                    ? 'bg-blue-600 border-blue-600 text-white shadow-md ring-4 ring-blue-100 dark:ring-blue-950/70 scale-105'
                    : 'bg-white dark:bg-zinc-900 border-zinc-300 dark:border-zinc-700 text-zinc-400 hover:border-zinc-400 opacity-60'
                } ${isSelected ? 'ring-2 ring-zinc-900 dark:ring-zinc-100' : ''}`}
                title={`Этап: ${stage.label} (${isPassed ? 'Завершён' : isCurrent ? 'Текущий' : 'В очереди'})`}
              >
                {isPassed ? (
                  <Check className="w-4 h-4 stroke-[3]" />
                ) : (
                  <Icon className="w-4 h-4" />
                )}
              </button>
            )
          })}
        </div>

        {/* Labels & Timing row underneath */}
        <div className="flex items-start justify-between w-full mt-2.5">
          {STAGES_CONFIG.map((stage, idx) => {
            const isPassed = isAccepted || idx < currentStageIndex
            const isCurrent = !isAccepted && idx === currentStageIndex
            const isPending = !isPassed && !isCurrent
            const alignClass = idx === 0 
              ? 'items-start text-left' 
              : idx === STAGES_CONFIG.length - 1 
              ? 'items-end text-right' 
              : 'items-center text-center'

            return (
              <div 
                key={stage.id} 
                className={`w-20 flex flex-col cursor-pointer ${alignClass}`}
                onClick={() => onSelectStage?.(stage.id)}
              >
                <span className={`text-xs font-semibold leading-tight ${
                  isCurrent 
                    ? 'text-blue-600 dark:text-blue-400' 
                    : isPassed 
                    ? 'text-zinc-800 dark:text-zinc-200' 
                    : 'text-zinc-400 dark:text-zinc-500 opacity-60'
                }`}>
                  {stage.label}
                </span>

                <span className={`text-[10px] font-mono mt-0.5 ${
                  isCurrent 
                    ? 'text-blue-500 font-medium' 
                    : isPassed 
                    ? 'text-zinc-400 dark:text-zinc-500' 
                    : 'text-zinc-400 dark:text-zinc-500 opacity-40 pointer-events-none cursor-not-allowed'
                }`}>
                  {isCurrent && stage.id === 'acceptance' 
                    ? 'ожидание' 
                    : isPassed 
                    ? stage.defaultDuration 
                    : isCurrent 
                    ? 'в процессе...' 
                    : '—'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Stage Sub-description Callout */}
      <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800/80 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-1.5 text-zinc-600 dark:text-zinc-400">
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">Текущее действие:</span>
          <span className="truncate max-w-[340px]">{currentAction}</span>
        </div>

        <span className="text-[11px] text-zinc-400 font-mono hidden sm:inline">
          Кликните на этап для перехода к артефактам
        </span>
      </div>
    </div>
  )
}
