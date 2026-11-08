import React, { useState } from 'react';
import { 
  FolderGit2, 
  Plus, 
  Search, 
  Terminal, 
  ChevronRight, 
  Cpu, 
  Layers, 
  Moon, 
  Sun,
  Server,
  Activity,
  CheckCircle2,
  ExternalLink
} from 'lucide-react';
import { Project } from '../types';

interface SidebarProps {
  currentProject: Project;
  projects: Project[];
  onSelectProject: (project: Project) => void;
  onOpenConnectModal: () => void;
  onOpenWorkerModal: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function Sidebar({
  currentProject,
  projects,
  onSelectProject,
  onOpenConnectModal,
  onOpenWorkerModal,
  isDarkMode,
  onToggleTheme,
  collapsed,
  onToggleCollapse
}: SidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredProjects = projects.filter(p => 
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <aside 
      className={`h-screen flex flex-row shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-zinc-50/70 dark:bg-zinc-950/80 backdrop-blur-md transition-all duration-300 z-30 select-none ${
        collapsed ? 'w-16' : 'w-72'
      }`}
    >
      {/* Mini Icon Dock Rail */}
      <div className="w-16 h-full flex flex-col items-center py-3.5 border-r border-zinc-200/80 dark:border-zinc-800/80 bg-zinc-100/50 dark:bg-zinc-900/50 shrink-0 justify-between">
        <div className="flex flex-col items-center gap-3 w-full">
          {/* Logo Mark */}
          <div className="relative group cursor-pointer" onClick={onToggleCollapse} title="Свернуть / Развернуть меню">
            <div className="w-10 h-10 rounded-xl bg-blue-600 dark:bg-blue-600 text-white flex items-center justify-center font-bold text-base shadow-sm hover:scale-105 transition-transform">
              tw
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 rounded-full border-2 border-zinc-100 dark:border-zinc-900" title="Harness daemon online" />
          </div>

          <div className="w-8 h-[1px] bg-zinc-200 dark:border-zinc-800 my-1" />

          {/* Workspace Quick Icon Buttons */}
          <button 
            className="w-10 h-10 rounded-xl bg-zinc-200/80 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 flex items-center justify-center hover:bg-zinc-300 dark:hover:bg-zinc-700 transition-colors shadow-xs"
            title="Рабочее пространство: Core Team"
          >
            <span className="text-xs font-semibold">hh</span>
          </button>

          <button 
            className="w-10 h-10 rounded-xl bg-white dark:bg-zinc-800/70 text-zinc-600 dark:text-zinc-400 flex items-center justify-center hover:text-zinc-900 dark:hover:text-zinc-100 border border-zinc-200 dark:border-zinc-700/60 transition-colors"
            title="Пайплайны разработки"
          >
            <Layers className="w-4 h-4" />
          </button>

          <button 
            onClick={onOpenWorkerModal}
            className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors border ${
              currentProject.workerRunning 
                ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60'
                : 'bg-zinc-100 dark:bg-zinc-800/50 text-zinc-400 border-zinc-200 dark:border-zinc-800'
            }`}
            title={`Воркер: ${currentProject.workerRunning ? 'Активен (порт 47831)' : 'Остановлен'}`}
          >
            <Cpu className="w-4 h-4" />
          </button>
        </div>

        {/* Bottom utility icons */}
        <div className="flex flex-col items-center gap-2.5 w-full">
          <button
            onClick={onToggleTheme}
            className="w-10 h-10 rounded-xl text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100 hover:bg-zinc-200/60 dark:hover:bg-zinc-800 flex items-center justify-center transition-colors"
            title={isDarkMode ? 'Светлая тема' : 'Тёмная тема'}
          >
            {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          <button
            onClick={onOpenConnectModal}
            className="w-10 h-10 rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 text-zinc-500 hover:text-blue-600 hover:border-blue-500 dark:text-zinc-400 dark:hover:text-blue-400 flex items-center justify-center transition-colors"
            title="Подключить новый проект"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Collapsible Project Panel */}
      {!collapsed && (
        <div className="flex-1 flex flex-col h-full overflow-hidden">
          {/* Workspace Title & Brand */}
          <div className="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 flex items-center justify-center font-bold text-xs">
                tw
              </div>
              <div>
                <h1 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 leading-none">
                  tw-web
                </h1>
                <span className="text-[11px] text-zinc-500 dark:text-zinc-400">
                  Агентский harness v0.9.4
                </span>
              </div>
            </div>
            <button 
              onClick={onToggleCollapse}
              className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 p-1 rounded-md"
              title="Скрыть панель"
            >
              <ChevronRight className="w-4 h-4 rotate-180" />
            </button>
          </div>

          {/* Section: Рабочее пространство */}
          <div className="px-4 pt-3 pb-1">
            <div className="text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              Рабочее пространство
            </div>
            <div className="mt-1.5 flex items-center justify-between p-2 rounded-lg bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-xs font-medium text-zinc-800 dark:text-zinc-200 shadow-2xs">
              <div className="flex items-center gap-2 truncate">
                <span className="w-2 h-2 rounded-full bg-blue-500" />
                <span className="truncate">Локальное окружение dev</span>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-500 font-mono">
                :47831
              </span>
            </div>
          </div>

          {/* Section: Проекты with Search */}
          <div className="px-4 pt-3 flex-1 flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                Проекты ({projects.length})
              </span>
              <button 
                onClick={onOpenConnectModal}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-0.5"
              >
                <Plus className="w-3 h-3" />
                <span>Новый</span>
              </button>
            </div>

            {/* Search Input */}
            <div className="relative mb-2.5">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-zinc-400" />
              <input
                type="text"
                placeholder="Найти проект..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-xs rounded-lg pl-8 pr-3 py-1.5 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow"
              />
            </div>

            {/* Projects List */}
            <div className="flex-1 overflow-y-auto space-y-1 pr-1">
              {filteredProjects.map((project) => {
                const isSelected = project.id === currentProject.id;
                return (
                  <button
                    key={project.id}
                    onClick={() => onSelectProject(project)}
                    className={`w-full text-left p-2.5 rounded-lg text-xs transition-all flex items-start gap-2.5 group ${
                      isSelected
                        ? 'bg-blue-50/80 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900/60 text-blue-900 dark:text-blue-100'
                        : 'hover:bg-zinc-100 dark:hover:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border border-transparent'
                    }`}
                  >
                    <FolderGit2 className={`w-4 h-4 mt-0.5 shrink-0 ${isSelected ? 'text-blue-600 dark:text-blue-400' : 'text-zinc-400 group-hover:text-zinc-600 dark:group-hover:text-zinc-300'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="font-medium truncate">{project.name}</span>
                        {isSelected && (
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400 shrink-0" />
                        )}
                      </div>
                      <div className="text-[11px] text-zinc-500 dark:text-zinc-400 truncate mt-0.5">
                        {project.totalTasks} задач · {project.activeBranch}
                      </div>
                    </div>
                  </button>
                );
              })}

              {/* Connect Project Button */}
              <button
                onClick={onOpenConnectModal}
                className="w-full mt-2 text-left p-2 rounded-lg text-xs border border-dashed border-zinc-300 dark:border-zinc-800 text-zinc-500 dark:text-zinc-400 hover:text-blue-600 dark:hover:text-blue-400 hover:border-blue-300 dark:hover:border-blue-800 flex items-center justify-center gap-1.5 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Подключить проект</span>
              </button>
            </div>
          </div>

          {/* Sidebar Footer Stats & Worker Status */}
          <div className="p-3 border-t border-zinc-200 dark:border-zinc-800 bg-white/60 dark:bg-zinc-900/60 space-y-2">
            <div className="flex items-center justify-between text-[11px] text-zinc-500 dark:text-zinc-400">
              <span>Задач в проекте:</span>
              <span className="font-semibold text-zinc-800 dark:text-zinc-200 font-mono">
                {currentProject.totalTasks}
              </span>
            </div>

            <div 
              onClick={onOpenWorkerModal}
              className="p-2 rounded-lg bg-zinc-100/70 dark:bg-zinc-800/60 border border-zinc-200/80 dark:border-zinc-700/60 cursor-pointer hover:border-zinc-300 dark:hover:border-zinc-600 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-800 dark:text-zinc-200">
                  <Activity className={`w-3.5 h-3.5 ${currentProject.workerRunning ? 'text-emerald-500 animate-pulse' : 'text-zinc-400'}`} />
                  <span>Воркер harness</span>
                </div>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  currentProject.workerRunning 
                    ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300'
                    : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-600 dark:text-zinc-300'
                }`}>
                  {currentProject.workerRunning ? 'Активен' : 'Остановлен'}
                </span>
              </div>
              <div className="text-[10px] text-zinc-500 dark:text-zinc-400 mt-1 flex items-center justify-between">
                <span>Локальная панель</span>
                <span className="font-mono">порт {currentProject.workerPort}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
