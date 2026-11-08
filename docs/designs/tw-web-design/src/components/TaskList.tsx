import React, { useState } from 'react';
import { 
  Search, 
  RefreshCw, 
  FileText, 
  Code2, 
  CheckSquare, 
  Eye, 
  ShieldCheck, 
  Check, 
  Clock, 
  AlertCircle,
  Filter,
  CheckCircle2,
  Trash2,
  Play,
  Zap,
  X,
  SlidersHorizontal,
  ChevronRight,
  List,
  Rows
} from 'lucide-react';
import { Task, TaskStage } from '../types';

interface TaskListProps {
  tasks: Task[];
  selectedTask: Task;
  onSelectTask: (task: Task) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  onDeleteTask: (taskId: string) => void;
  onDeleteBatch: (taskIds: string[]) => void;
  onRunQueueBatch: (taskIds: string[]) => void;
}

const STAGES = [
  { id: 'plan' as TaskStage, label: 'План', icon: FileText },
  { id: 'dev' as TaskStage, label: 'Код', icon: Code2 },
  { id: 'checks' as TaskStage, label: 'Тесты', icon: CheckSquare },
  { id: 'review' as TaskStage, label: 'Ревью', icon: Eye },
  { id: 'acceptance' as TaskStage, label: 'Приёмка', icon: ShieldCheck }
];

export function TaskList({
  tasks,
  selectedTask,
  onSelectTask,
  onRefresh,
  isRefreshing,
  onDeleteTask,
  onDeleteBatch,
  onRunQueueBatch
}: TaskListProps) {
  const [filter, setFilter] = useState<'all' | 'needs_you' | 'backlog' | 'completed'>('all');
  const [search, setSearch] = useState('');
  const [density, setDensity] = useState<'compact' | 'normal'>('compact');
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(new Set());
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const filteredTasks = tasks.filter((task) => {
    // Filter by tab
    if (filter === 'needs_you' && !task.needsAttention) return false;
    if (filter === 'backlog' && task.status !== 'backlog') return false;
    if (filter === 'completed' && task.status !== 'accepted_applied') return false;

    // Filter by search query
    if (search.trim()) {
      const q = search.toLowerCase();
      return (
        task.title.toLowerCase().includes(q) ||
        task.key.toLowerCase().includes(q) ||
        task.statusLabel.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const needsAttentionCount = tasks.filter(t => t.needsAttention).length;

  // Toggle single task in multi-select
  const toggleSelectTask = (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedTaskIds(prev => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  };

  // Select all or deselect all
  const toggleSelectAll = () => {
    if (selectedTaskIds.size === filteredTasks.length) {
      setSelectedTaskIds(new Set());
    } else {
      setSelectedTaskIds(new Set(filteredTasks.map(t => t.id)));
    }
  };

  // Run batch queue
  const handleRunQueue = () => {
    if (selectedTaskIds.size === 0) return;
    onRunQueueBatch(Array.from(selectedTaskIds));
    setSelectedTaskIds(new Set());
  };

  // Delete batch
  const handleDeleteBatch = () => {
    if (selectedTaskIds.size === 0) return;
    if (window.confirm(`Вы уверены, что хотите удалить ${selectedTaskIds.size} задач?`)) {
      onDeleteBatch(Array.from(selectedTaskIds));
      setSelectedTaskIds(new Set());
    }
  };

  // Single delete with confirmation
  const handleDeleteSingle = (taskId: string, taskKey: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm(`Удалить задачу ${taskKey}?`)) {
      onDeleteTask(taskId);
      setSelectedTaskIds(prev => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
    }
  };

  const isAllSelected = filteredTasks.length > 0 && selectedTaskIds.size === filteredTasks.length;

  return (
    <div className="w-[420px] lg:w-[460px] xl:w-[500px] border-r border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-950/60 flex flex-col h-full shrink-0 select-none transition-all">
      {/* Top Section: Header, Controls & Search */}
      <div className="p-3.5 border-b border-zinc-200 dark:border-zinc-800 space-y-2.5 bg-white/70 dark:bg-zinc-900/70">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
              Задачи проекта
            </h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 font-mono text-zinc-600 dark:text-zinc-400 font-semibold">
              {tasks.length}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Density Toggle (Compact narrow strips vs Normal cards) */}
            <div className="flex items-center p-0.5 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-500">
              <button
                onClick={() => setDensity('compact')}
                className={`p-1 rounded transition-colors cursor-pointer ${density === 'compact' ? 'bg-white dark:bg-zinc-700 text-blue-600 dark:text-blue-400 shadow-2xs' : 'hover:text-zinc-900 dark:hover:text-zinc-100'}`}
                title="Компактный вид (узкие полоски)"
              >
                <Rows className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setDensity('normal')}
                className={`p-1 rounded transition-colors cursor-pointer ${density === 'normal' ? 'bg-white dark:bg-zinc-700 text-blue-600 dark:text-blue-400 shadow-2xs' : 'hover:text-zinc-900 dark:hover:text-zinc-100'}`}
                title="Развернутый вид"
              >
                <List className="w-3.5 h-3.5" />
              </button>
            </div>

            <button
              onClick={onRefresh}
              className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200 flex items-center gap-1 transition-colors p-1 rounded-md cursor-pointer"
              title="Обновить список задач"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-blue-600' : ''}`} />
            </button>
          </div>
        </div>

        {/* Filter Segmented Control Tabs */}
        <div className="flex items-center p-1 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-xs font-medium">
          <button
            onClick={() => setFilter('all')}
            className={`flex-1 py-1 rounded-md transition-all text-center cursor-pointer ${
              filter === 'all'
                ? 'bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 shadow-2xs font-semibold'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100'
            }`}
          >
            Все ({tasks.length})
          </button>

          <button
            onClick={() => setFilter('needs_you')}
            className={`flex-1 py-1 rounded-md transition-all text-center relative cursor-pointer ${
              filter === 'needs_you'
                ? 'bg-white dark:bg-zinc-900 text-blue-600 dark:text-blue-400 shadow-2xs font-semibold'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100'
            }`}
          >
            <span>Нужно вам</span>
            {needsAttentionCount > 0 && (
              <span className="ml-1 px-1 rounded-full text-[10px] bg-blue-100 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300 font-bold">
                {needsAttentionCount}
              </span>
            )}
          </button>

          <button
            onClick={() => setFilter('backlog')}
            className={`flex-1 py-1 rounded-md transition-all text-center cursor-pointer ${
              filter === 'backlog'
                ? 'bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 shadow-2xs font-semibold'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100'
            }`}
          >
            Бэклог
          </button>
        </div>

        {/* Search input with shortcut hint */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-zinc-400" />
          <input
            type="text"
            placeholder="Найти задачу по названию, ключу или статусу..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-xs rounded-lg pl-8 pr-3 py-1.5 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2.5 top-2 text-[10px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 cursor-pointer"
            >
              Очистить
            </button>
          )}
        </div>

        {/* Select All Bar */}
        <div className="flex items-center justify-between text-[11px] text-zinc-500 dark:text-zinc-400 pt-0.5">
          <button
            onClick={toggleSelectAll}
            className="flex items-center gap-1.5 hover:text-zinc-900 dark:hover:text-zinc-200 cursor-pointer"
          >
            <input
              type="checkbox"
              checked={isAllSelected}
              onChange={toggleSelectAll}
              className="rounded text-blue-600 focus:ring-blue-500 cursor-pointer"
            />
            <span>{isAllSelected ? 'Снять выбор' : 'Выбрать все задачи'}</span>
          </button>

          {selectedTaskIds.size > 0 && (
            <span className="font-semibold text-blue-600 dark:text-blue-400">
              Выбрано: {selectedTaskIds.size}
            </span>
          )}
        </div>
      </div>

      {/* FLOATING BATCH ACTION BAR (When tasks are selected) */}
      {selectedTaskIds.size > 0 && (
        <div className="px-3 py-2 bg-blue-50 dark:bg-blue-950/50 border-b border-blue-200 dark:border-blue-900/60 flex items-center justify-between text-xs animate-in slide-in-from-top-2">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-blue-900 dark:text-blue-200 font-mono text-[11px]">
              {selectedTaskIds.size} {selectedTaskIds.size === 1 ? 'задача' : 'задач'}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Run in Queue Button */}
            <button
              onClick={handleRunQueue}
              className="px-2.5 py-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium flex items-center gap-1 transition-colors shadow-2xs cursor-pointer text-xs"
              title="Запустить выбранные задачи в очередь воркера"
            >
              <Zap className="w-3 h-3 fill-current" />
              <span>Запустить очередь</span>
            </button>

            {/* Delete Batch Button */}
            <button
              onClick={handleDeleteBatch}
              className="p-1 rounded-md hover:bg-rose-100 dark:hover:bg-rose-950/60 text-rose-600 dark:text-rose-400 transition-colors cursor-pointer"
              title="Удалить выбранные задачи"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>

            {/* Clear Selection */}
            <button
              onClick={() => setSelectedTaskIds(new Set())}
              className="p-1 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 cursor-pointer"
              title="Снять выбор"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Task Rows List: Ultra-compact strips or normal mode */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {filteredTasks.length === 0 ? (
          <div className="p-8 text-center text-xs text-zinc-400">
            Нет задач, удовлетворяющих условиям фильтра.
          </div>
        ) : (
          filteredTasks.map((task) => {
            const isSelected = task.id === selectedTask.id;
            const isChecked = selectedTaskIds.has(task.id);
            const isAcceptedUnconfirmed = task.status === 'accepted_unconfirmed';
            const isAcceptedApplied = task.status === 'accepted_applied';
            const isInProgress = task.status === 'in_progress';

            if (density === 'compact') {
              /* ================= COMPACT NARROW STRIP (УЗКАЯ ПОЛОСКА) ================= */
              return (
                <div
                  key={task.id}
                  onClick={() => onSelectTask(task)}
                  className={`px-2.5 py-2 rounded-lg border text-left cursor-pointer transition-all duration-150 group flex items-center justify-between gap-2.5 ${
                    isSelected
                      ? 'bg-blue-50/80 dark:bg-blue-950/40 border-blue-500 dark:border-blue-500 shadow-2xs ring-1 ring-blue-500/30'
                      : isChecked
                      ? 'bg-zinc-100/90 dark:bg-zinc-800/80 border-zinc-300 dark:border-zinc-700'
                      : 'bg-white dark:bg-zinc-900/70 border-zinc-200/80 dark:border-zinc-800/80 hover:border-zinc-300 dark:hover:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-900'
                  }`}
                  title={`${task.key}: ${task.title} (${task.statusLabel})`}
                >
                  {/* Left: Checkbox, ID, attention marker, and truncated title */}
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    {/* Checkbox for Batch Selection */}
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onClick={(e) => toggleSelectTask(task.id, e)}
                      onChange={() => {}}
                      className="rounded text-blue-600 focus:ring-blue-500 shrink-0 cursor-pointer"
                    />

                    {/* Task Number / ID */}
                    <span className="font-mono text-[11px] font-bold text-zinc-600 dark:text-zinc-400 shrink-0 w-8">
                      #{task.num}
                    </span>

                    {/* Title (Single line truncated) */}
                    <span className={`text-xs font-medium truncate leading-tight ${
                      isSelected 
                        ? 'text-blue-950 dark:text-blue-100 font-semibold' 
                        : 'text-zinc-800 dark:text-zinc-200 group-hover:text-blue-600 dark:group-hover:text-blue-400'
                    }`}>
                      {task.title}
                    </span>
                  </div>

                  {/* Right: Status badge & Delete button on hover */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    {/* 5 mini pipeline step dots */}
                    <div className="hidden sm:flex items-center gap-1 bg-zinc-100/80 dark:bg-zinc-800/60 px-1.5 py-0.5 rounded">
                      {STAGES.map((s) => {
                        const stageData = task.stages[s.id];
                        const isStageCompleted = stageData?.status === 'completed';
                        const isStageActive = task.currentStage === s.id;

                        return (
                          <div
                            key={s.id}
                            className={`w-1.5 h-1.5 rounded-full ${
                              isStageActive
                                ? 'bg-blue-600 dark:bg-blue-400 ring-2 ring-blue-300 dark:ring-blue-900 scale-125'
                                : isStageCompleted
                                ? 'bg-emerald-500 dark:bg-emerald-400'
                                : 'bg-zinc-300 dark:bg-zinc-700'
                            }`}
                            title={`Этап: ${s.label}`}
                          />
                        );
                      })}
                    </div>

                    {/* Status Pill */}
                    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap ${
                      isAcceptedUnconfirmed
                        ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200/60 dark:border-amber-900/40'
                        : isAcceptedApplied
                        ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200/60 dark:border-emerald-900/40'
                        : isInProgress
                        ? 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200/60 dark:border-blue-900/40'
                        : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500'
                    }`}>
                      {isAcceptedApplied ? (
                        <CheckCircle2 className="w-2.5 h-2.5 text-emerald-500 shrink-0" />
                      ) : isAcceptedUnconfirmed ? (
                        <Check className="w-2.5 h-2.5 text-amber-500 shrink-0" />
                      ) : (
                        <Clock className="w-2.5 h-2.5 text-blue-500 shrink-0" />
                      )}
                      <span className="truncate max-w-[80px]">{task.currentStageLabel}</span>
                    </span>

                    {/* Quick Single Delete Button (visible on hover) */}
                    <button
                      onClick={(e) => handleDeleteSingle(task.id, task.key, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-100 dark:hover:bg-rose-950/60 text-zinc-400 hover:text-rose-600 dark:hover:text-rose-400 transition-all cursor-pointer"
                      title="Удалить задачу"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              );
            }

            /* ================= NORMAL DETAILED VIEW ================= */
            return (
              <div
                key={task.id}
                onClick={() => onSelectTask(task)}
                className={`p-3 rounded-xl border text-left cursor-pointer transition-all duration-150 group relative ${
                  isSelected
                    ? 'bg-white dark:bg-zinc-900 border-blue-500 dark:border-blue-500 shadow-sm ring-1 ring-blue-500/30'
                    : isChecked
                    ? 'bg-zinc-100/90 dark:bg-zinc-800/80 border-zinc-300 dark:border-zinc-700'
                    : 'bg-white/80 dark:bg-zinc-900/60 border-zinc-200/90 dark:border-zinc-800/80 hover:border-zinc-300 dark:hover:border-zinc-700 hover:shadow-2xs'
                }`}
              >
                <div className="flex items-center justify-between text-xs mb-1">
                  <div className="flex items-center gap-2 font-mono text-[11px] font-semibold text-zinc-500 dark:text-zinc-400">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onClick={(e) => toggleSelectTask(task.id, e)}
                      onChange={() => {}}
                      className="rounded text-blue-600 focus:ring-blue-500 cursor-pointer"
                    />
                    <span>#{task.num}</span>
                    <span className="text-zinc-300 dark:text-zinc-600">·</span>
                    <span className="text-zinc-700 dark:text-zinc-300">{task.key}</span>
                  </div>

                  <div className="flex items-center gap-1">
                    {task.needsAttention && (
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" title="Требуется ваше действие" />
                    )}
                    <button
                      onClick={(e) => handleDeleteSingle(task.id, task.key, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-100 text-zinc-400 hover:text-rose-600 transition-all cursor-pointer"
                      title="Удалить задачу"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                <h3 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 leading-snug line-clamp-2 mb-2 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                  {task.title}
                </h3>

                <div className="flex items-center justify-between pt-2 border-t border-zinc-100 dark:border-zinc-800/80">
                  <div className="flex items-center gap-1">
                    {STAGES.map((s) => {
                      const Icon = s.icon;
                      const stageData = task.stages[s.id];
                      const isStageCompleted = stageData?.status === 'completed';
                      const isStageActive = task.currentStage === s.id;

                      return (
                        <div
                          key={s.id}
                          className={`w-4.5 h-4.5 rounded flex items-center justify-center text-[10px] ${
                            isStageActive
                              ? 'bg-blue-600 text-white shadow-2xs font-bold'
                              : isStageCompleted
                              ? 'bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300'
                              : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-400'
                          }`}
                        >
                          <Icon className="w-2.5 h-2.5" />
                        </div>
                      );
                    })}
                  </div>

                  <span className="text-[10px] font-medium text-zinc-500 dark:text-zinc-400">
                    {task.currentStageLabel}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
