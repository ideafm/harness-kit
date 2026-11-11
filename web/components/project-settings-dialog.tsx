'use client'
import React from 'react'
import { FolderGit2, Shield, AlertTriangle } from 'lucide-react'
import type { Session } from '@/lib/contracts'
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogDescription 
} from '@/components/ui/dialog'
import { AutoApplySetting } from './auto-apply-setting'
import { RemoveProject } from './remove-project'

export interface ProjectSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  project: { id: string; name: string } | null
  policy?: { enabled: boolean; confirmation_url: string }
  session?: Session
  disabled?: boolean
  onRefresh?: () => void
  onRemove?: (id: string) => Promise<void>
  canRemove?: boolean
  tasksCount?: number
}

export function ProjectSettingsDialog({
  open,
  onOpenChange,
  project,
  policy,
  session,
  disabled = false,
  onRefresh,
  onRemove,
  canRemove = false,
  tasksCount,
}: ProjectSettingsDialogProps) {
  if (!project) return null

  const hasPolicy = Boolean(policy?.confirmation_url && session?.csrf_token)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto p-0 gap-0 border-zinc-200 dark:border-zinc-800 shadow-2xl">
        {/* Header */}
        <div className="p-5 border-b border-zinc-200 dark:border-zinc-800 flex items-start gap-3.5 bg-zinc-50/70 dark:bg-zinc-900/50">
          <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-blue-950/60 border border-blue-100 dark:border-blue-900/40 text-blue-600 dark:text-blue-400 shrink-0">
            <FolderGit2 className="w-5 h-5" />
          </div>
          <div className="min-w-0 pr-6">
            <DialogTitle className="text-base font-semibold truncate text-zinc-900 dark:text-zinc-100">
              Настройки: {project.name}
            </DialogTitle>
            <DialogDescription className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
              Управление автоматизацией и подключением проекта
            </DialogDescription>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-6">
          {/* Quick info row */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-lg border border-zinc-200/80 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30">
              <span className="text-[10px] uppercase font-semibold text-zinc-400 tracking-wider">
                ID проекта
              </span>
              <p className="font-mono text-zinc-800 dark:text-zinc-200 truncate mt-0.5">
                {project.id}
              </p>
            </div>
            <div className="p-3 rounded-lg border border-zinc-200/80 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30">
              <span className="text-[10px] uppercase font-semibold text-zinc-400 tracking-wider">
                Задачи
              </span>
              <p className="text-zinc-800 dark:text-zinc-200 font-semibold mt-0.5">
                {tasksCount !== undefined ? `${tasksCount} в очереди` : 'готов к работе'}
              </p>
            </div>
          </div>

          {/* Automation & Auto-apply section */}
          <section aria-label="Автоматическое применение результатов">
            {hasPolicy ? (
              <AutoApplySetting
                policy={policy}
                project={project.id}
                session={session}
                disabled={disabled}
                onRefresh={onRefresh || (() => {})}
                showTitle={true}
              />
            ) : (
              <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/40 text-xs text-zinc-500 space-y-1">
                <p className="font-medium text-zinc-700 dark:text-zinc-300">
                  Политика недоступна для редактирования
                </p>
                <p className="text-[11px] leading-relaxed">
                  Настройка автоматического применения доступна в доверенном локальном сеансе выбранного активного проекта.
                </p>
              </div>
            )}
          </section>

          {/* Danger zone / Removal */}
          {canRemove && onRemove && (
            <section className="pt-2 border-t border-zinc-200 dark:border-zinc-800 space-y-2.5" aria-labelledby="danger-heading">
              <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                <AlertTriangle className="w-4 h-4" />
                <h3 id="danger-heading" className="text-xs font-semibold uppercase tracking-wider">
                  Опасная зона
                </h3>
              </div>

              <RemoveProject
                project={project}
                onRemove={onRemove}
                onRemoved={() => onOpenChange(false)}
              />
            </section>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
