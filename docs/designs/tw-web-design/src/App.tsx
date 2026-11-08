/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import { 
  Plus, 
  RefreshCw, 
  Sparkles, 
  SlidersHorizontal,
  ChevronRight,
  GitBranch,
  CheckCircle2,
  Check,
  Zap,
  Trash2
} from 'lucide-react';
import { mockProject, mockProjectsList, mockTasks } from './data/mockData';
import { Project, Task } from './types';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { TaskList } from './components/TaskList';
import { TaskDetailPane } from './components/TaskDetailPane';
import { NewTaskModal } from './components/NewTaskModal';
import { ConnectProjectModal } from './components/ConnectProjectModal';
import { WorkerModal } from './components/WorkerModal';
import { CommandPalette } from './components/CommandPalette';
import { InteractiveWorkerTerminal } from './components/InteractiveWorkerTerminal';

export default function App() {
  const [projects, setProjects] = useState<Project[]>(mockProjectsList);
  const [currentProject, setCurrentProject] = useState<Project>(mockProject);
  const [tasks, setTasks] = useState<Task[]>(mockTasks);
  const [selectedTaskId, setSelectedTaskId] = useState<string>(mockTasks[0]?.id || '');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [collapsedSidebar, setCollapsedSidebar] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Modals state
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [isWorkerModalOpen, setIsWorkerModalOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);

  // Sync theme with <html> element
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  // Global shortcuts: Cmd+K for command palette, Ctrl+` or Cmd+` for terminal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen(prev => !prev);
      } else if ((e.metaKey || e.ctrlKey) && (e.key === '`' || e.key === '~' || e.key === 'ё' || e.key === 'Ё')) {
        e.preventDefault();
        setIsTerminalOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Find currently active task or fallback
  const selectedTask = tasks.find(t => t.id === selectedTaskId) || tasks[0];

  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => {
      setIsRefreshing(false);
      showToast('Список задач синхронизирован с воркером');
    }, 600);
  };

  const handleToggleWorker = () => {
    setCurrentProject(prev => {
      const nextRunning = !prev.workerRunning;
      showToast(nextRunning ? 'Воркер успешно запущен' : 'Воркер остановлен');
      return {
        ...prev,
        workerRunning: nextRunning
      };
    });
  };

  // Project selection handler
  const handleSelectProject = (proj: Project) => {
    setCurrentProject(proj);
    showToast(`Переключено на проект: ${proj.name}`);
  };

  // Create new task
  const handleCreateTask = (newTaskData: Partial<Task>) => {
    const nextNum = tasks.length + 1;
    const newTask: Task = {
      id: String(nextNum),
      num: nextNum,
      key: `TASK-${nextNum}`,
      title: newTaskData.title || 'Новая задача',
      status: 'in_progress',
      statusLabel: 'В процессе разработки',
      currentStage: 'dev',
      currentStageLabel: 'Разработка',
      branch: newTaskData.branch || `feature/task-${nextNum}`,
      model: newTaskData.model || 'claude-3-7-sonnet',
      createdAt: 'Только что',
      updatedAt: 'Только что',
      needsAttention: false,
      stages: {
        plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'completed', duration: '8с' },
        dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'running', duration: 'в процессе...' },
        checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'pending' },
        review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'pending' },
        acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Приёмка', status: 'pending' }
      },
      description: newTaskData.description || '',
      harnessPrompt: newTaskData.harnessPrompt || '',
      resultSummary: 'Агент инициализировал рабочую ветку и приступил к выполнению задания.',
      planItems: [
        { id: 'np1', title: 'Декомпозировать промпт и составить граф изменений', completed: true },
        { id: 'np2', title: 'Написать исходный код в sandbox окружении', completed: false },
        { id: 'np3', title: 'Прогнать тесты и проверить сборку проекта', completed: false }
      ],
      logs: [
        {
          id: `l-new-1`,
          timestamp: new Date().toLocaleTimeString().slice(0, 5),
          type: 'human',
          title: 'Задача принята в работу',
          content: 'Оператор создал задачу через панель управления tw-web.'
        },
        {
          id: `l-new-2`,
          timestamp: new Date().toLocaleTimeString().slice(0, 5),
          type: 'thought',
          title: 'Инициализация окружения',
          content: `Создана ветка ${newTaskData.branch}. Воркер запустил Docker-контейнер.`
        }
      ],
      diffs: [],
      checks: [
        {
          id: 'nc1',
          name: 'TypeScript Checks',
          command: 'pnpm exec tsc --noEmit',
          status: 'running',
          duration: 'выполняется...',
          summary: 'Проверка типов в реальном времени'
        }
      ],
      reviewNotes: { reviewer: 'Safety Agent', passed: true, score: 0, feedback: [] },
      runtimeInfo: { configured: true, port: 3000 + nextNum, status: 'running', verifiedVersionHash: '00000', workingVersionHash: 'head' }
    };

    setTasks(prev => [newTask, ...prev]);
    setSelectedTaskId(newTask.id);
    setCurrentProject(prev => ({ ...prev, totalTasks: prev.totalTasks + 1 }));
    showToast(`Создана задача ${newTask.key}`);
  };

  // Delete single task
  const handleDeleteTask = (taskId: string) => {
    const taskToDelete = tasks.find(t => t.id === taskId);
    const remainingTasks = tasks.filter(t => t.id !== taskId);
    setTasks(remainingTasks);

    if (selectedTaskId === taskId) {
      if (remainingTasks.length > 0) {
        setSelectedTaskId(remainingTasks[0].id);
      }
    }

    setCurrentProject(prev => ({
      ...prev,
      totalTasks: Math.max(0, prev.totalTasks - 1)
    }));

    showToast(`Задача ${taskToDelete?.key || ''} удалена`);
  };

  // Delete batch of tasks
  const handleDeleteBatch = (taskIds: string[]) => {
    const deleteSet = new Set(taskIds);
    const remainingTasks = tasks.filter(t => !deleteSet.has(t.id));
    setTasks(remainingTasks);

    if (deleteSet.has(selectedTaskId)) {
      if (remainingTasks.length > 0) {
        setSelectedTaskId(remainingTasks[0].id);
      }
    }

    setCurrentProject(prev => ({
      ...prev,
      totalTasks: Math.max(0, prev.totalTasks - taskIds.length)
    }));

    showToast(`Удалено задач: ${taskIds.length}`);
  };

  // Batch run queue
  const handleRunQueueBatch = (taskIds: string[]) => {
    const queueSet = new Set(taskIds);
    setTasks(prev => prev.map(t => {
      if (queueSet.has(t.id)) {
        return {
          ...t,
          status: 'in_progress',
          statusLabel: 'В процессе разработки',
          currentStage: 'dev',
          currentStageLabel: 'Разработка',
          needsAttention: false,
          stages: {
            ...t.stages,
            plan: { ...t.stages.plan, status: 'completed' },
            dev: { ...t.stages.dev, status: 'running', duration: 'в очереди...' }
          },
          logs: [
            ...t.logs,
            {
              id: `queue-${Date.now()}`,
              timestamp: new Date().toLocaleTimeString().slice(0, 5),
              type: 'human',
              title: 'Задача запущена в пакетную очередь',
              content: 'Оператор запустил параллельное выполнение задачи в очереди воркера.'
            }
          ]
        };
      }
      return t;
    }));

    showToast(`Запущено в очередь воркера: ${taskIds.length} задач`);
  };

  // Apply task to git
  const handleApplyTask = (taskId: string) => {
    setTasks(prev => prev.map(t => {
      if (t.id === taskId) {
        return {
          ...t,
          status: 'accepted_applied',
          statusLabel: 'Принято и применено',
          needsAttention: false,
          stages: {
            ...t.stages,
            acceptance: {
              ...t.stages.acceptance,
              status: 'completed',
              duration: 'завершено'
            }
          }
        };
      }
      return t;
    }));
    showToast('Изменения успешно применены к ветке');
  };

  // Request changes from agent
  const handleRequestChanges = (taskId: string, feedback: string) => {
    setTasks(prev => prev.map(t => {
      if (t.id === taskId) {
        return {
          ...t,
          status: 'in_progress',
          statusLabel: 'Доработка по замечаниям',
          currentStage: 'dev',
          currentStageLabel: 'Разработка',
          needsAttention: false,
          logs: [
            ...t.logs,
            {
              id: `feedback-${Date.now()}`,
              timestamp: new Date().toLocaleTimeString().slice(0, 5),
              type: 'human',
              title: 'Запрос на доработку от оператора',
              content: feedback
            },
            {
              id: `thought-${Date.now()}`,
              timestamp: new Date().toLocaleTimeString().slice(0, 5),
              type: 'thought',
              title: 'Перепланирование задачи с учётом правок',
              content: 'Получены новые критерии от оператора. Перехожу к редактированию файлов.'
            }
          ]
        };
      }
      return t;
    }));
    showToast('Запрос на доработку отправлен агенту');
  };

  // Connect new project
  const handleConnectProject = (newProj: Project) => {
    setProjects(prev => [...prev, newProj]);
    setCurrentProject(newProj);
    showToast(`Подключен проект ${newProj.name}`);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 font-sans antialiased">
      {/* 1. Left Sidebar (Dock + Projects Drawer) */}
      <Sidebar
        currentProject={currentProject}
        projects={projects}
        onSelectProject={handleSelectProject}
        onOpenConnectModal={() => setIsConnectModalOpen(true)}
        onOpenWorkerModal={() => setIsWorkerModalOpen(true)}
        isDarkMode={isDarkMode}
        onToggleTheme={() => setIsDarkMode(!isDarkMode)}
        collapsed={collapsedSidebar}
        onToggleCollapse={() => setCollapsedSidebar(!collapsedSidebar)}
      />

      {/* 2. Main Workspace Layout */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* Top Header Bar */}
        <Header
          currentProject={currentProject}
          projects={projects}
          onSelectProject={handleSelectProject}
          onOpenConnectModal={() => setIsConnectModalOpen(true)}
          selectedTask={selectedTask}
          onRefresh={handleRefresh}
          isRefreshing={isRefreshing}
          onOpenNewTaskModal={() => setIsNewTaskModalOpen(true)}
          onOpenWorkerModal={() => setIsWorkerModalOpen(true)}
          onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
          onToggleWorker={handleToggleWorker}
          onToggleTerminal={() => setIsTerminalOpen(prev => !prev)}
          isTerminalOpen={isTerminalOpen}
          isDarkMode={isDarkMode}
          onToggleTheme={() => setIsDarkMode(!isDarkMode)}
        />

        {/* Page Banner Title */}
        <div className="px-6 py-4 border-b border-zinc-200 dark:border-zinc-800 bg-white/60 dark:bg-zinc-900/40 flex flex-wrap items-center justify-between gap-4 shrink-0">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
              Работа над проектом
            </h1>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              Результат, следующее действие и детали — в одном месте.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsTerminalOpen(prev => !prev)}
              className="px-3 py-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:bg-zinc-50 dark:hover:bg-zinc-800 text-xs font-mono text-zinc-700 dark:text-zinc-300 shadow-2xs transition-colors flex items-center gap-1.5 cursor-pointer"
              title="Открыть терминал воркера (Ctrl+`)"
            >
              <span className="text-blue-500 font-bold">&gt;_</span>
              <span>Терминал воркера</span>
              <kbd className="text-[10px] px-1 py-0.2 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-500 border border-zinc-200 dark:border-zinc-700">
                Ctrl+`
              </kbd>
            </button>

            <button
              onClick={() => setIsNewTaskModalOpen(true)}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs hover:shadow transition-all flex items-center gap-1.5 cursor-pointer active:scale-98"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Новая задача</span>
            </button>
          </div>
        </div>

        {/* Master-Detail Split Workspace */}
        <div className="flex-1 flex min-h-0 overflow-hidden relative">
          {/* Left Column: Task Queue List */}
          <TaskList
            tasks={tasks}
            selectedTask={selectedTask}
            onSelectTask={(task) => setSelectedTaskId(task.id)}
            onRefresh={handleRefresh}
            isRefreshing={isRefreshing}
            onDeleteTask={handleDeleteTask}
            onDeleteBatch={handleDeleteBatch}
            onRunQueueBatch={handleRunQueueBatch}
          />

          {/* Right Column: Detailed Task & Harness Inspector */}
          {selectedTask ? (
            <TaskDetailPane
              task={selectedTask}
              onApplyTask={handleApplyTask}
              onRequestChanges={handleRequestChanges}
              onDeleteTask={handleDeleteTask}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-zinc-400">
              Нет выбранной задачи. Создайте новую задачу или выберите из списка.
            </div>
          )}

          {/* Slide-up Worker Terminal Drawer */}
          {isTerminalOpen && (
            <div className="absolute bottom-0 left-0 right-0 z-40 p-4 pt-0 animate-in slide-in-from-bottom-4 duration-200">
              <div className="max-w-5xl mx-auto shadow-2xl">
                <InteractiveWorkerTerminal
                  project={currentProject}
                  tasks={tasks}
                  onRunTask={(taskId) => {
                    handleRunQueueBatch([taskId]);
                    showToast('Задача запущена в воркер через CLI');
                  }}
                  onClose={() => setIsTerminalOpen(false)}
                  isFloating={true}
                />
              </div>
            </div>
          )}
        </div>

        {/* Toast Feedback Notification */}
        {toastMessage && (
          <div className="absolute bottom-5 right-5 z-50 px-3.5 py-2 rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs font-medium shadow-xl flex items-center gap-2 animate-in fade-in-50 slide-in-from-bottom-2">
            <Check className="w-3.5 h-3.5 text-emerald-400 dark:text-emerald-600" />
            <span>{toastMessage}</span>
          </div>
        )}
      </div>

      {/* Modals */}
      <NewTaskModal
        isOpen={isNewTaskModalOpen}
        onClose={() => setIsNewTaskModalOpen(false)}
        onCreateTask={handleCreateTask}
        activeBranch={currentProject.activeBranch}
      />

      <ConnectProjectModal
        isOpen={isConnectModalOpen}
        onClose={() => setIsConnectModalOpen(false)}
        onConnectProject={handleConnectProject}
      />

      <WorkerModal
        isOpen={isWorkerModalOpen}
        onClose={() => setIsWorkerModalOpen(false)}
        project={currentProject}
        tasks={tasks}
        onToggleWorker={handleToggleWorker}
        onRunTask={(taskId) => {
          handleRunQueueBatch([taskId]);
          showToast('Задача запущена в воркер через терминал');
        }}
      />

      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        tasks={tasks}
        projects={projects}
        currentProject={currentProject}
        onSelectProject={handleSelectProject}
        onSelectTask={(t) => setSelectedTaskId(t.id)}
        onOpenNewTaskModal={() => setIsNewTaskModalOpen(true)}
        onOpenConnectModal={() => setIsConnectModalOpen(true)}
        onOpenWorkerModal={() => setIsWorkerModalOpen(true)}
        onToggleTerminal={() => setIsTerminalOpen(prev => !prev)}
        onToggleTheme={() => setIsDarkMode(!isDarkMode)}
        isDarkMode={isDarkMode}
      />
    </div>
  );
}
