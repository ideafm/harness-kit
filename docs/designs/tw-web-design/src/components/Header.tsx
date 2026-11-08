import React, { useState, useRef, useEffect } from 'react';
import { 
  GitBranch, 
  RefreshCw, 
  Play, 
  Square, 
  HelpCircle, 
  Plus, 
  Search, 
  ChevronRight, 
  ChevronDown,
  Check, 
  Terminal, 
  Sun, 
  Moon,
  FolderGit2,
  ExternalLink
} from 'lucide-react';
import { Project, Task } from '../types';

interface HeaderProps {
  currentProject: Project;
  projects: Project[];
  onSelectProject: (project: Project) => void;
  onOpenConnectModal: () => void;
  selectedTask?: Task;
  onRefresh: () => void;
  isRefreshing: boolean;
  onOpenNewTaskModal: () => void;
  onOpenWorkerModal: () => void;
  onOpenCommandPalette: () => void;
  onToggleWorker: () => void;
  onToggleTerminal?: () => void;
  isTerminalOpen?: boolean;
  isDarkMode: boolean;
  onToggleTheme: () => void;
}

export function Header({
  currentProject,
  projects,
  onSelectProject,
  onOpenConnectModal,
  selectedTask,
  onRefresh,
  isRefreshing,
  onOpenNewTaskModal,
  onOpenWorkerModal,
  onOpenCommandPalette,
  onToggleWorker,
  onToggleTerminal,
  isTerminalOpen = false,
  isDarkMode,
  onToggleTheme
}: HeaderProps) {
  const [isProjectDropdownOpen, setIsProjectDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsProjectDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="h-14 border-b border-zinc-200 dark:border-zinc-800 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md px-4 flex items-center justify-between shrink-0 z-20">
      {/* Left: Breadcrumbs & Interactive Project Switcher */}
      <div className="flex items-center gap-3 min-w-0">
        <nav className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
          <span className="hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors">
            Проекты
          </span>
          <ChevronRight className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
          
          {/* Interactive Project Switcher Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setIsProjectDropdownOpen(!isProjectDropdownOpen)}
              className="flex items-center gap-1 font-semibold text-zinc-900 dark:text-zinc-100 hover:text-blue-600 dark:hover:text-blue-400 bg-zinc-100/70 dark:bg-zinc-800/60 px-2 py-1 rounded-md transition-colors cursor-pointer"
              title="Переключить активный проект"
            >
              <FolderGit2 className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
              <span className="truncate max-w-[140px]">{currentProject.name}</span>
              <ChevronDown className="w-3 h-3 text-zinc-400" />
            </button>

            {/* Dropdown Menu */}
            {isProjectDropdownOpen && (
              <div className="absolute left-0 top-full mt-1.5 w-64 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-xl py-1.5 z-50 animate-in fade-in-50 zoom-in-95">
                <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                  Выбрать проект
                </div>
                <div className="divide-y divide-zinc-100 dark:divide-zinc-800/80 max-h-60 overflow-y-auto">
                  {projects.map((p) => {
                    const isSelected = p.id === currentProject.id;
                    return (
                      <button
                        key={p.id}
                        onClick={() => {
                          onSelectProject(p);
                          setIsProjectDropdownOpen(false);
                        }}
                        className={`w-full text-left px-3 py-2 flex items-center justify-between text-xs transition-colors ${
                          isSelected
                            ? 'bg-blue-50 dark:bg-blue-950/40 text-blue-900 dark:text-blue-200 font-semibold'
                            : 'hover:bg-zinc-50 dark:hover:bg-zinc-800/60 text-zinc-700 dark:text-zinc-300'
                        }`}
                      >
                        <div className="truncate mr-2">
                          <div className="flex items-center gap-1.5 truncate">
                            <span className="truncate">{p.name}</span>
                            {p.workerRunning && (
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                            )}
                          </div>
                          <div className="text-[10px] text-zinc-400 font-mono truncate font-normal">
                            {p.totalTasks} задач · {p.activeBranch}
                          </div>
                        </div>
                        {isSelected && <Check className="w-4 h-4 text-blue-600 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
                <div className="p-1.5 border-t border-zinc-100 dark:border-zinc-800 mt-1">
                  <button
                    onClick={() => {
                      setIsProjectDropdownOpen(false);
                      onOpenConnectModal();
                    }}
                    className="w-full text-left px-2.5 py-1.5 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/40 rounded-lg flex items-center gap-1.5 font-medium transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Подключить новый проект...</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          <ChevronRight className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
          <span className="text-zinc-600 dark:text-zinc-300">
            Задачи
          </span>
          {selectedTask && (
            <>
              <ChevronRight className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
              <span className="font-mono text-zinc-900 dark:text-zinc-100 font-semibold bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded text-[11px]">
                {selectedTask.key}
              </span>
            </>
          )}
        </nav>

        {/* Git Branch Pill */}
        <div className="hidden md:flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-[11px] font-mono text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700/60">
          <GitBranch className="w-3 h-3 text-zinc-500" />
          <span>{currentProject.activeBranch}</span>
        </div>
      </div>

      {/* Center: Command Palette Trigger */}
      <button
        onClick={onOpenCommandPalette}
        className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/40 text-xs text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:border-zinc-300 dark:hover:border-zinc-700 transition-colors cursor-pointer"
        title="Открыть командную строку (⌘K)"
      >
        <Search className="w-3.5 h-3.5" />
        <span>Быстрый поиск команд и задач...</span>
        <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-zinc-800 text-[10px] font-mono border border-zinc-200 dark:border-zinc-700 text-zinc-500 shadow-2xs">
          ⌘K
        </kbd>
      </button>

      {/* Right: Worker Control, Quick Actions, New Task */}
      <div className="flex items-center gap-2.5 shrink-0">
        {/* Worker Daemon Status / Trigger */}
        <div className="flex items-center">
          <button
            onClick={onOpenWorkerModal}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer ${
              currentProject.workerRunning
                ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/80 hover:bg-emerald-100'
                : 'bg-zinc-100 dark:bg-zinc-800/60 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:bg-zinc-200'
            }`}
            title="Кликните для открытия настроек воркера"
          >
            <span className={`w-2 h-2 rounded-full ${currentProject.workerRunning ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
            <span className="hidden sm:inline">
              {currentProject.workerRunning ? 'Worker запущен' : 'Worker не запущен'}
            </span>
            <span className="text-[10px] font-mono opacity-80">
              :{currentProject.workerPort}
            </span>
          </button>
        </div>

        {/* Interactive Worker Terminal Toggle Button */}
        {onToggleTerminal && (
          <button
            onClick={onToggleTerminal}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-medium border transition-colors cursor-pointer ${
              isTerminalOpen
                ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 border-zinc-900 dark:border-zinc-100 shadow-sm'
                : 'bg-zinc-100 dark:bg-zinc-800/60 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700 hover:bg-zinc-200 dark:hover:bg-zinc-700'
            }`}
            title="Интерактивный терминал воркера (клик или Ctrl+`)"
          >
            <Terminal className="w-3.5 h-3.5 text-blue-500" />
            <span className="hidden md:inline">Терминал</span>
            <span className="text-[9px] px-1 py-0.2 rounded font-sans bg-blue-500/10 dark:bg-blue-400/20 text-blue-600 dark:text-blue-300">
              CLI
            </span>
          </button>
        )}

        {/* Refresh Button */}
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="p-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors flex items-center gap-1 text-xs px-2.5 cursor-pointer"
          title="Синхронизировать задачи и статус"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-blue-600' : ''}`} />
          <span className="hidden sm:inline">Обновить</span>
        </button>

        {/* Primary CTA: + Новая задача */}
        <button
          onClick={onOpenNewTaskModal}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium shadow-xs hover:shadow transition-all shrink-0 active:scale-98 cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Новая задача</span>
        </button>
      </div>
    </header>
  );
}
