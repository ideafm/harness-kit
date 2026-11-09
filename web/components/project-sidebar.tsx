'use client'
import React, { useState } from 'react'
import { 
  FolderGit2, 
  Plus, 
  Search, 
  ChevronRight, 
  Activity,
  ExternalLink
} from 'lucide-react'
import type { Projects } from '@/lib/contracts'
import { Sidebar, useSidebar } from '@/components/ui/sidebar'

function useOptionalSidebar() {
  try {
    return useSidebar()
  } catch {
    return null
  }
}

export interface ProjectSidebarProps {
  project: string
  count: number
  running: boolean
  projects?: Projects
  selected?: string
  onSelect?: (id: string) => void
  backend?: 'gemini' | 'codex'
  onOpenWorkerModal?: () => void
  collapsed?: boolean
  onToggleCollapse?: () => void
}

export function ProjectSidebar({
  project,
  count,
  running,
  projects,
  selected,
  onSelect,
  onOpenWorkerModal,
  collapsed = false,
  onToggleCollapse
}: ProjectSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [internalCollapsed, setInternalCollapsed] = useState(collapsed)

  const isCollapsed = onToggleCollapse !== undefined ? collapsed : internalCollapsed
  const toggleCollapse = onToggleCollapse || (() => setInternalCollapsed(prev => !prev))

  const items = (projects?.items || []).filter(p => 
    p.name.toLocaleLowerCase('ru').includes(searchQuery.toLocaleLowerCase('ru'))
  )

  const sidebar = useOptionalSidebar()
  if (sidebar?.isMobile) {
    return (
      <Sidebar className="border-r border-zinc-200 dark:border-zinc-800 bg-zinc-50/70 dark:bg-zinc-950/80 select-none">
        <div className="p-4 border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-sm">
              tw
            </div>
            <div>
              <strong className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">tw</strong>
              <p className="text-[11px] text-zinc-500">Рабочее пространство</p>
            </div>
          </div>
        </div>
        <div className="p-3 flex-1 overflow-y-auto space-y-1">
          {items.map(p => (
            <button
              key={p.id}
              type="button"
              aria-label={p.name}
              aria-current={p.id === selected ? 'page' : undefined}
              onClick={() => {
                onSelect?.(p.id)
                sidebar.setOpenMobile(false)
              }}
              className={`w-full text-left p-2 rounded-lg text-xs transition-colors flex items-center gap-2 ${
                p.id === selected 
                  ? 'bg-blue-50 text-blue-700 font-semibold' 
                  : 'hover:bg-zinc-100 text-zinc-700'
              }`}
            >
              <FolderGit2 className="w-4 h-4 text-zinc-400" />
              <span>{p.name}</span>
            </button>
          ))}
          {!projects?.items?.length && <p className="text-xs text-zinc-500 p-2">{project}</p>}
        </div>
      </Sidebar>
    )
  }

  return (
    <aside 
      className={`h-screen flex flex-col shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 transition-all duration-300 z-30 select-none ${
        isCollapsed ? 'w-0 opacity-0 overflow-hidden border-r-0' : 'w-64 md:w-72'
      }`}
    >
      {/* Workspace Title & Brand */}
      <div className="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-sm shadow-xs">
              tw
            </div>
            <div 
              className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-zinc-950 ${
                running ? 'bg-emerald-500' : 'bg-zinc-400'
              }`} 
              title={running ? 'Harness daemon online' : 'Harness daemon offline'} 
            />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 leading-none">
              tw-web
            </h1>
            <p className="text-[11px] text-zinc-500 dark:text-zinc-400">Тест очереди B</p>
            <span className="text-[11px] text-zinc-500 dark:text-zinc-400">
              Агентский harness
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button 
            type="button"
            onClick={toggleCollapse}
            className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 cursor-pointer transition-colors"
            title="Скрыть панель"
          >
            <ChevronRight className="w-4 h-4 rotate-180" />
          </button>
        </div>
      </div>

      {/* Section: Рабочее пространство */}
      <div className="px-4 pt-3.5 pb-1 shrink-0">
        <div className="text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Рабочее пространство
        </div>
        <div className="mt-1.5 flex items-center justify-between p-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-900/80 border border-zinc-200/80 dark:border-zinc-800 text-xs font-medium text-zinc-800 dark:text-zinc-200 shadow-2xs">
          <div className="flex items-center gap-2 truncate">
            <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
            <span className="truncate">Локальное окружение dev</span>
          </div>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-200/60 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 font-mono shrink-0">
            :47831
          </span>
        </div>
      </div>

      {/* Section: Проекты with Search */}
      <div className="px-4 pt-3 flex-1 flex flex-col min-h-0 overflow-y-auto">
        <div className="flex items-center justify-between mb-2 shrink-0">
          <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            Проекты ({projects?.items?.length || 0})
          </span>
          {projects?.connect_url && (
            <a 
              href={projects.connect_url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-0.5 cursor-pointer"
            >
              <Plus className="w-3 h-3" />
              <span>Новый</span>
            </a>
          )}
        </div>

        {/* Search Input with generous padding */}
        <div className="relative mb-2.5 shrink-0">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none" />
          <input
            type="text"
            aria-label="Поиск проектов"
            placeholder="Найти проект…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800 text-xs rounded-lg pl-10 pr-3.5 py-2 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow shadow-2xs search-input"
            style={{ paddingLeft: '2.5rem' }}
          />
        </div>

        {/* Projects List without vertical stretching */}
        <nav aria-label="Проекты" className="project-list flex flex-col gap-1 pr-1">
          {items.map((p) => {
            const isSelected = p.id === selected
            return (
              <button
                key={p.id}
                type="button"
                aria-label={p.name}
                aria-current={isSelected ? 'page' : undefined}
                onClick={() => onSelect?.(p.id)}
                className={`w-full text-left p-2.5 rounded-lg text-xs transition-all flex items-start gap-2.5 group cursor-pointer shrink-0 ${
                  isSelected
                    ? 'bg-blue-50/80 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900/60 text-blue-900 dark:text-blue-100 shadow-2xs font-medium'
                    : 'hover:bg-zinc-100 dark:hover:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border border-transparent'
                }`}
              >
                <FolderGit2 className={`w-4 h-4 mt-0.5 shrink-0 ${isSelected ? 'text-blue-600 dark:text-blue-400' : 'text-zinc-400 group-hover:text-zinc-600 dark:group-hover:text-zinc-300'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium truncate">{p.name}</span>
                    {isSelected && (
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400 shrink-0" />
                    )}
                  </div>
                  <div className="text-[11px] text-zinc-500 dark:text-zinc-400 truncate mt-0.5">
                    {p.id === selected ? `${count} задач` : 'активен'}
                  </div>
                </div>
              </button>
            )
          })}

          {!projects?.items?.length && (
            <p className="muted px-2 py-1 text-xs text-zinc-500">{project}</p>
          )}

          {Boolean(projects?.items?.length && !items.length) && (
            <p className="px-2 py-2 text-xs text-zinc-500">Проекты не найдены.</p>
          )}

          {/* Connect Project Button / Link */}
          {projects?.connect_url && (
            <a
              href={projects.connect_url}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full mt-2 text-left p-2 rounded-lg text-xs border border-dashed border-zinc-300 dark:border-zinc-800 text-zinc-500 dark:text-zinc-400 hover:text-blue-600 dark:hover:text-blue-400 hover:border-blue-300 dark:hover:border-blue-800 flex items-center justify-center gap-1.5 transition-colors shrink-0"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Подключить проект</span>
              <ExternalLink className="w-3 h-3 ml-auto text-blue-500" />
            </a>
          )}
        </nav>
      </div>

      {/* Sidebar Footer Stats & Worker Status */}
      <div className="p-3 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50 space-y-2 shrink-0">
        <div className="flex items-center justify-between text-[11px] text-zinc-500 dark:text-zinc-400">
          <span>Задач в проекте:</span>
          <span className="font-semibold text-zinc-800 dark:text-zinc-200 font-mono">
            {count}
          </span>
        </div>

        <div 
          className="p-2 rounded-lg bg-white dark:bg-zinc-900 border border-zinc-200/80 dark:border-zinc-800 opacity-70 cursor-not-allowed select-none shadow-2xs"
          title="Интерактивное управление воркером в веб-панели отключено"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-800 dark:text-zinc-200">
              <Activity className={`w-3.5 h-3.5 ${running ? 'text-emerald-500 animate-pulse' : 'text-zinc-400'}`} />
              <span>Воркер harness</span>
            </div>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
              running 
                ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300'
                : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-600 dark:text-zinc-300'
            }`}>
              {running ? 'Активен' : 'Остановлен'}
            </span>
          </div>
          <div className="text-[10px] text-zinc-500 dark:text-zinc-400 mt-1 flex items-center justify-between">
            <span>Локальная панель</span>
            <span className="font-mono">порт 47831</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
