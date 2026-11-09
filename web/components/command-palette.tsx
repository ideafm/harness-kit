'use client'
import React, { useState, useEffect, useMemo, useRef } from 'react'
import { 
  Search, 
  Plus, 
  RefreshCw, 
  FolderGit2, 
  Terminal, 
  X
} from 'lucide-react'
import type { Task, Projects } from '@/lib/contracts'
import { taskStateLabel } from '@/lib/task-presentation'

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
  tasks: Task[]
  projects?: Projects
  currentProjectId?: string
  currentProjectName: string
  onSelectProject?: (id: string) => void
  onSelectTask: (id: number) => void
  onOpenNewTaskModal?: () => void
  onToggleTerminal?: () => void
  onRefresh?: () => void
}

interface ActionCommand {
  id: string
  title: string
  description?: string
  shortcut?: string
  keywords: string[]
  icon: React.ReactNode
  perform: () => void
}

export function CommandPalette({
  isOpen,
  onClose,
  tasks,
  projects,
  currentProjectId,
  currentProjectName,
  onSelectProject,
  onSelectTask,
  onOpenNewTaskModal,
  onToggleTerminal,
  onRefresh
}: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  const commands: ActionCommand[] = useMemo(() => [
    {
      id: 'terminal',
      title: 'Консоль воркера',
      description: 'Открыть интерактивную консоль, статус демона и логи воркера',
      shortcut: 'Ctrl+`',
      keywords: ['консоль', 'терминал', 'воркер', 'console', 'terminal', 'worker', 'cli', 'лог', 'логи', 'открыть', 'запустить'],
      icon: <Terminal className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />,
      perform: () => {
        onToggleTerminal?.()
        onClose()
      }
    },
    {
      id: 'new-task',
      title: 'Создать новую задачу',
      description: 'Поставить новую задачу для активного проекта',
      shortcut: 'Enter',
      keywords: ['создать', 'новая', 'задача', 'new', 'task', 'create', 'добавить', 'плюс'],
      icon: <Plus className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />,
      perform: () => {
        onOpenNewTaskModal?.()
        onClose()
      }
    },
    {
      id: 'refresh',
      title: 'Обновить задачи и статус',
      description: 'Синхронизировать состояние проектов и задач',
      shortcut: 'R',
      keywords: ['обновить', 'refresh', 'перезагрузить', 'статус'],
      icon: <RefreshCw className="w-3.5 h-3.5 text-zinc-500" />,
      perform: () => {
        onRefresh?.()
        onClose()
      }
    }
  ], [onToggleTerminal, onOpenNewTaskModal, onRefresh, onClose])

  const q = query.toLowerCase().trim()

  const matchingCommands = useMemo(() => {
    if (!q) return commands
    return commands.filter(c => 
      c.title.toLowerCase().includes(q) ||
      (c.description && c.description.toLowerCase().includes(q)) ||
      c.keywords.some(k => k.toLowerCase().includes(q))
    )
  }, [commands, q])

  const matchingProjects = useMemo(() => {
    const items = projects?.items || []
    if (!q) return items
    return items.filter(p => p.name.toLowerCase().includes(q) || p.id.toLowerCase().includes(q))
  }, [projects, q])

  const matchingTasks = useMemo(() => {
    if (!q) return tasks
    return tasks.filter(t => 
      `#${t.id} ${t.request}`.toLowerCase().includes(q) ||
      `task-${t.id}`.toLowerCase().includes(q) ||
      taskStateLabel(t).toLowerCase().includes(q)
    )
  }, [tasks, q])

  const flatItems = useMemo(() => {
    const list: { key: string; perform: () => void }[] = []
    matchingCommands.forEach(c => list.push({ key: `cmd-${c.id}`, perform: c.perform }))
    matchingProjects.forEach(p => list.push({
      key: `project-${p.id}`,
      perform: () => { onSelectProject?.(p.id); onClose() }
    }))
    matchingTasks.forEach(t => list.push({
      key: `task-${t.id}`,
      perform: () => { onSelectTask(t.id); onClose() }
    }))
    return list
  }, [matchingCommands, matchingProjects, matchingTasks, onSelectProject, onSelectTask, onClose])

  useEffect(() => {
    setSelectedIndex(0)
  }, [q])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        if (isOpen) onClose()
      } else if (e.key === 'Escape' && isOpen) {
        onClose()
      } else if (isOpen && flatItems.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setSelectedIndex(prev => (prev + 1) % flatItems.length)
        } else if (e.key === 'ArrowUp') {
          e.preventDefault()
          setSelectedIndex(prev => (prev - 1 + flatItems.length) % flatItems.length)
        } else if (e.key === 'Enter') {
          e.preventDefault()
          flatItems[selectedIndex]?.perform()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, flatItems, selectedIndex])

  if (!isOpen) return null

  let runningIndex = 0

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-zinc-950/50 backdrop-blur-xs animate-in fade-in-0 duration-150">
      <div 
        className="w-full max-w-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150 flex flex-col max-h-[75vh]"
        onClick={e => e.stopPropagation()}
      >
        <div className="relative border-b border-zinc-200 dark:border-zinc-800 px-4 py-3 flex items-center gap-3 bg-zinc-50/50 dark:bg-zinc-900/50">
          <Search className="w-4 h-4 text-zinc-400 shrink-0" />
          <input
            autoFocus
            type="text"
            placeholder="Поиск задач, проектов или команд... (Esc для выхода)"
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="w-full bg-transparent text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none"
            style={{ border: 'none', padding: 0 }}
          />
          <button 
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div ref={listRef} className="overflow-y-auto p-2 space-y-3 divide-y divide-zinc-100 dark:divide-zinc-800/80">
          {matchingCommands.length > 0 && (
            <div>
              <div className="px-3 py-1 text-[11px] font-semibold text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">
                Команды и действия ({matchingCommands.length})
              </div>
              <div className="space-y-0.5 mt-1">
                {matchingCommands.map(c => {
                  const idx = runningIndex++
                  const isSelected = idx === selectedIndex
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={c.perform}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors text-left cursor-pointer ${
                        isSelected 
                          ? 'bg-blue-50 dark:bg-blue-950/60 text-blue-900 dark:text-blue-100 font-medium ring-1 ring-blue-500/20' 
                          : 'hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200'
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="p-1 rounded bg-zinc-100 dark:bg-zinc-800 shrink-0">
                          {c.icon}
                        </div>
                        <div>
                          <div className="font-medium leading-tight">{c.title}</div>
                          {c.description && (
                            <div className="text-[11px] text-zinc-400 dark:text-zinc-500">{c.description}</div>
                          )}
                        </div>
                      </div>
                      {c.shortcut && (
                        <span className="text-[10px] text-zinc-400 font-mono px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 shrink-0">
                          {c.shortcut}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {matchingProjects.length > 0 && (
            <div className="pt-2">
              <div className="px-3 py-1 text-[11px] font-semibold text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">
                Проекты ({matchingProjects.length})
              </div>
              <div className="space-y-0.5 mt-1">
                {matchingProjects.map(p => {
                  const idx = runningIndex++
                  const isSelected = idx === selectedIndex
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => { onSelectProject?.(p.id); onClose() }}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors text-left cursor-pointer ${
                        isSelected 
                          ? 'bg-blue-50 dark:bg-blue-950/60 text-blue-900 dark:text-blue-100 font-medium ring-1 ring-blue-500/20' 
                          : p.id === currentProjectId 
                            ? 'bg-zinc-50 dark:bg-zinc-800/50 text-blue-700 dark:text-blue-300 font-semibold' 
                            : 'hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 truncate">
                        <FolderGit2 className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
                        <span className="truncate">{p.name}</span>
                      </div>
                      {p.id === currentProjectId && (
                        <span className="text-[10px] font-mono text-blue-600 dark:text-blue-400">активен</span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {matchingTasks.length > 0 && (
            <div className="pt-2">
              <div className="px-3 py-1 text-[11px] font-semibold text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">
                Задачи ({matchingTasks.length})
              </div>
              <div className="space-y-0.5 mt-1 max-h-48 overflow-y-auto">
                {matchingTasks.map(t => {
                  const idx = runningIndex++
                  const isSelected = idx === selectedIndex
                  const isPaused = t.state === 'paused'
                  const isActionRequired = isPaused || Boolean(t.question) || ['needs_permission', 'needs_input', 'awaiting_approval'].includes(t.state) || (t.state === 'review' && t.stage === 'done')
                  const isAccepted = t.state === 'accepted'

                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => { onSelectTask(t.id); onClose() }}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors text-left cursor-pointer ${
                        isSelected 
                          ? 'bg-blue-50 dark:bg-blue-950/60 text-blue-900 dark:text-blue-100 font-medium ring-1 ring-blue-500/20' 
                          : isActionRequired
                          ? 'hover:bg-amber-50/50 dark:hover:bg-amber-950/30 text-zinc-800 dark:text-zinc-200'
                          : 'hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200'
                      }`}
                    >
                      <div className="flex items-center gap-2 truncate mr-2">
                        {isActionRequired && (
                          <span className="relative flex h-1.5 w-1.5 shrink-0">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-amber-500" />
                          </span>
                        )}
                        <span className="font-mono text-[11px] font-bold text-zinc-500 shrink-0">#{t.id}</span>
                        <span className="truncate">{t.request.split('\n')[0].replace(/^\s*#{1,6}\s+/, '')}</span>
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 font-medium ${
                        isPaused
                          ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-200 border-amber-300 dark:border-amber-700/80'
                          : isActionRequired
                          ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200/60 dark:border-amber-900/40'
                          : isAccepted
                          ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200/60 dark:border-emerald-900/40'
                          : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 border-transparent'
                      }`}>
                        {taskStateLabel(t)}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {flatItems.length === 0 && (
            <div className="p-6 text-center text-xs text-zinc-400">
              По запросу &quot;{query}&quot; ничего не найдено.
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/60 text-[11px] text-zinc-400 flex items-center justify-between">
          <span>Навигация: ↑↓ для выбора, Enter для запуска</span>
          <span className="font-mono">tw-web harness</span>
        </div>
      </div>
    </div>
  )
}
