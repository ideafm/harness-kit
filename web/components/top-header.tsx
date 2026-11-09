'use client'
import React, { useState, useRef, useEffect } from 'react'
import { 
  FolderGit2, 
  ChevronRight, 
  ChevronDown, 
  Search, 
  RefreshCw, 
  Plus, 
  Check,
  GitBranch,
  PanelLeft
} from 'lucide-react'
import type { Task, Projects, Status } from '@/lib/contracts'

interface TopHeaderProps {
  projectName: string
  selectedProjectId?: string
  projects?: Projects
  onSelectProject?: (id: string) => void
  selectedTask?: Task
  status?: Status
  onRefresh: () => void
  isRefreshing: boolean
  onOpenNewTaskModal?: () => void
  onToggleTerminal?: () => void
  isTerminalOpen?: boolean
  onOpenCommandPalette?: () => void
  onToggleSidebar?: () => void
}

export function TopHeader({
  projectName,
  selectedProjectId,
  projects,
  onSelectProject,
  selectedTask,
  status,
  onRefresh,
  isRefreshing,
  onOpenNewTaskModal,
  onToggleTerminal,
  isTerminalOpen = false,
  onOpenCommandPalette,
  onToggleSidebar
}: TopHeaderProps) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const isWorkerRunning = status?.worker.running ?? false

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <header className="topbar h-13 border-b border-zinc-200 dark:border-zinc-800 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md px-4 flex items-center justify-between shrink-0 z-20 flex-nowrap gap-3">
      {/* Left: Project Switcher & Task Breadcrumb */}
      <div className="flex items-center gap-2 min-w-0 shrink-0">
        {onToggleSidebar && (
          <button
            type="button"
            onClick={onToggleSidebar}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer mr-0.5 shrink-0"
            title="Переключить боковое меню"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
        )}

        <nav className="breadcrumb flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400 shrink-0" aria-label="Навигационная цепочка">
          {/* Project Switcher */}
          <div className="relative shrink-0" ref={dropdownRef}>
            <button
              type="button"
              aria-label="Переключить проект"
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="flex items-center gap-1.5 font-semibold text-zinc-900 dark:text-zinc-100 hover:text-blue-600 dark:hover:text-blue-400 bg-zinc-100/80 dark:bg-zinc-800/60 px-2 py-1 rounded-md transition-colors cursor-pointer"
              title="Переключить активный проект"
            >
              <FolderGit2 className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 shrink-0" />
              <strong className="truncate max-w-[130px] font-semibold">{projectName}</strong>
              <span className="font-mono text-[10px] rounded px-1.5 py-0.5 bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700/60 shrink-0 font-medium">
                v0.2.0
              </span>
              <ChevronDown className="w-3 h-3 text-zinc-400 shrink-0" />
            </button>

            {/* Dropdown Menu */}
            {isDropdownOpen && (
              <div 
                aria-label="Проекты"
                className="absolute left-0 top-full mt-1.5 w-64 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-xl py-1.5 z-50 animate-in fade-in-50 zoom-in-95 duration-100"
              >
                <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                  Выбрать проект
                </div>
                <div className="divide-y divide-zinc-100 dark:divide-zinc-800/80 max-h-60 overflow-y-auto">
                  {(projects?.items || []).map(p => {
                    const isSelected = p.id === selectedProjectId || p.id === projectName || p.name === projectName
                    return (
                      <button
                        key={p.id}
                        type="button"
                        aria-current={isSelected ? 'page' : undefined}
                        onClick={() => {
                          onSelectProject?.(p.id)
                          setIsDropdownOpen(false)
                        }}
                        className={`w-full text-left px-3 py-2 flex items-center justify-between text-xs transition-colors cursor-pointer ${
                          isSelected
                            ? 'bg-blue-50 dark:bg-blue-950/40 text-blue-900 dark:text-blue-200 font-semibold'
                            : 'hover:bg-zinc-50 dark:hover:bg-zinc-800/60 text-zinc-700 dark:text-zinc-300'
                        }`}
                      >
                        <span className="truncate">{p.name}</span>
                        {isSelected && <Check className="w-4 h-4 text-blue-600 shrink-0" />}
                      </button>
                    )
                  })}
                </div>

                {/* Connect new project (disabled with opacity-40 and pointer-events-none) */}
                <div className="p-1.5 border-t border-zinc-100 dark:border-zinc-800 mt-1">
                  <button
                    disabled
                    className="w-full text-left px-2.5 py-1.5 text-xs text-zinc-400 opacity-40 pointer-events-none cursor-not-allowed rounded-lg flex items-center gap-1.5 font-medium"
                    title="Подключение проектов выполняется через CLI: tw connect"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Подключить новый проект...</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {selectedTask && (
            <>
              <ChevronRight className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
              <span className="font-mono text-zinc-900 dark:text-zinc-100 font-semibold bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded text-[11px] whitespace-nowrap shrink-0">
                TASK-{selectedTask.id}
              </span>
            </>
          )}
        </nav>

        {/* Project Git Branch Pill matching design */}
        <div className="hidden xl:flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-[11px] font-mono text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700/60 shrink-0" title="Ветка проекта">
          <GitBranch className="w-3 h-3 text-zinc-500" />
          <span>{selectedTask?.integration?.branch || 'main'}</span>
        </div>
      </div>

      {/* Center: Command Palette Search */}
      <button
        type="button"
        onClick={onOpenCommandPalette}
        className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/40 text-xs text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:border-zinc-300 dark:hover:border-zinc-700 transition-colors cursor-pointer max-w-[240px] flex-1 justify-between shadow-2xs shrink min-w-0"
        title="Открыть быстрый поиск (⌘K)"
      >
        <div className="flex items-center gap-1.5 truncate">
          <Search className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
          <span className="truncate">Поиск команд и задач...</span>
        </div>
        <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-zinc-800 text-[10px] font-mono border border-zinc-200 dark:border-zinc-700 text-zinc-500 shadow-2xs shrink-0">
          ⌘K
        </kbd>
      </button>

      {/* Right Action Bar */}
      <div className="top-actions flex items-center gap-2 shrink-0 flex-nowrap">
        {/* Worker Badge */}
        <div 
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
            isWorkerRunning
              ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/80'
              : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border-zinc-200 dark:border-zinc-700'
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${isWorkerRunning ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-400'}`} />
          <span className="text-[11px]">
            {isWorkerRunning ? 'Worker запущен' : 'Worker не запущен'}
          </span>
          <span className="text-[10px] font-mono opacity-75">:47831</span>
        </div>

        {/* Refresh Button */}
        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="px-2.5 py-1 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-zinc-600 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors flex items-center gap-1 text-xs cursor-pointer"
          title="Обновить"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-blue-600' : ''}`} />
          <span>Обновить</span>
        </button>

        {/* New Task Button */}
        {onOpenNewTaskModal && (
          <button
            type="button"
            onClick={onOpenNewTaskModal}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium shadow-xs hover:shadow transition-all cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Новая задача</span>
          </button>
        )}
      </div>
    </header>
  )
}
