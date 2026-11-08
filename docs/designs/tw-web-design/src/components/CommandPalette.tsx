import React, { useState, useEffect } from 'react';
import { 
  Search, 
  Plus, 
  RefreshCw, 
  FolderGit2, 
  Play, 
  Trash2, 
  Moon, 
  Sun, 
  Terminal, 
  CheckSquare, 
  X,
  Zap,
  ArrowRight
} from 'lucide-react';
import { Project, Task } from '../types';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  tasks: Task[];
  projects: Project[];
  currentProject: Project;
  onSelectProject: (p: Project) => void;
  onSelectTask: (t: Task) => void;
  onOpenNewTaskModal: () => void;
  onOpenConnectModal: () => void;
  onOpenWorkerModal: () => void;
  onToggleTerminal?: () => void;
  onToggleTheme: () => void;
  isDarkMode: boolean;
}

export function CommandPalette({
  isOpen,
  onClose,
  tasks,
  projects,
  currentProject,
  onSelectProject,
  onSelectTask,
  onOpenNewTaskModal,
  onOpenConnectModal,
  onOpenWorkerModal,
  onToggleTerminal,
  onToggleTheme,
  isDarkMode
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Close on Escape or open on Cmd+K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
      } else if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Filter tasks and actions
  const matchingTasks = tasks.filter(t => 
    t.title.toLowerCase().includes(query.toLowerCase()) || 
    t.key.toLowerCase().includes(query.toLowerCase())
  );

  const matchingProjects = projects.filter(p =>
    p.name.toLowerCase().includes(query.toLowerCase())
  );

  const actions = [
    {
      id: 'new-task',
      title: 'Создать новую задачу...',
      category: 'Действия',
      icon: Plus,
      run: () => { onClose(); onOpenNewTaskModal(); }
    },
    {
      id: 'connect-proj',
      title: 'Подключить локальный репозиторий...',
      category: 'Действия',
      icon: FolderGit2,
      run: () => { onClose(); onOpenConnectModal(); }
    },
    {
      id: 'toggle-theme',
      title: isDarkMode ? 'Переключить на светлую тему' : 'Переключить на тёмную тему',
      category: 'Настройки',
      icon: isDarkMode ? Sun : Moon,
      run: () => { onToggleTheme(); onClose(); }
    },
    {
      id: 'worker-terminal',
      title: 'Интерактивный терминал воркера (tw-worker CLI)',
      category: 'Инструменты',
      icon: Terminal,
      run: () => { onClose(); onToggleTerminal?.(); }
    },
    {
      id: 'worker-settings',
      title: 'Открыть диагностику и логи воркера harness',
      category: 'Система',
      icon: Terminal,
      run: () => { onClose(); onOpenWorkerModal(); }
    }
  ].filter(a => a.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/60 backdrop-blur-xs p-4 animate-in fade-in-50">
      <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl max-w-xl w-full shadow-2xl overflow-hidden animate-in zoom-in-95">
        {/* Search Input Bar */}
        <div className="p-3.5 border-b border-zinc-200 dark:border-zinc-800 flex items-center gap-3">
          <Search className="w-4 h-4 text-zinc-400 shrink-0" />
          <input
            type="text"
            autoFocus
            placeholder="Поиск задач, проектов или команд... (↑↓ навигация, Esc выход)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full text-xs bg-transparent border-none outline-none text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400"
          />
          <button
            onClick={onClose}
            className="p-1 rounded text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 text-[10px] font-mono border border-zinc-200 dark:border-zinc-800"
          >
            ESC
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto p-2 space-y-3 divide-y divide-zinc-100 dark:divide-zinc-800/80">
          {/* Quick Actions */}
          {actions.length > 0 && (
            <div className="space-y-1">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                Команды
              </div>
              {actions.map((act) => {
                const Icon = act.icon;
                return (
                  <button
                    key={act.id}
                    onClick={act.run}
                    className="w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center justify-between text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors group cursor-pointer"
                  >
                    <div className="flex items-center gap-2.5">
                      <Icon className="w-4 h-4 text-zinc-400 group-hover:text-blue-600 dark:group-hover:text-blue-400" />
                      <span>{act.title}</span>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-zinc-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </button>
                );
              })}
            </div>
          )}

          {/* Matching Tasks */}
          {matchingTasks.length > 0 && (
            <div className="space-y-1 pt-2">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                Задачи ({matchingTasks.length})
              </div>
              {matchingTasks.map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    onSelectTask(t);
                    onClose();
                  }}
                  className="w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center justify-between text-zinc-800 dark:text-zinc-200 hover:bg-blue-50 dark:hover:bg-blue-950/40 transition-colors group cursor-pointer"
                >
                  <div className="flex items-center gap-2 truncate mr-2">
                    <span className="font-mono text-[11px] font-bold text-blue-600 dark:text-blue-400 shrink-0">
                      {t.key}
                    </span>
                    <span className="truncate">{t.title}</span>
                  </div>
                  <span className="text-[10px] text-zinc-400 shrink-0 font-medium">
                    {t.currentStageLabel}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Matching Projects */}
          {matchingProjects.length > 0 && (
            <div className="space-y-1 pt-2">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                Проекты
              </div>
              {matchingProjects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    onSelectProject(p);
                    onClose();
                  }}
                  className="w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center justify-between text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors group cursor-pointer"
                >
                  <div className="flex items-center gap-2 truncate">
                    <FolderGit2 className="w-3.5 h-3.5 text-zinc-400" />
                    <span className="truncate">{p.name}</span>
                    {p.id === currentProject.id && (
                      <span className="text-[10px] text-blue-600 font-semibold">(текущий)</span>
                    )}
                  </div>
                  <span className="text-[10px] text-zinc-400 font-mono">
                    {p.totalTasks} задач
                  </span>
                </button>
              ))}
            </div>
          )}

          {actions.length === 0 && matchingTasks.length === 0 && matchingProjects.length === 0 && (
            <div className="p-6 text-center text-xs text-zinc-400">
              Ничего не найдено по запросу &quot;{query}&quot;
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
