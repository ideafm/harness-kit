import React, { useState } from 'react';
import { 
  GitBranch, 
  Clock, 
  Cpu, 
  ExternalLink, 
  CheckCircle2, 
  AlertCircle, 
  Play, 
  Share2, 
  Copy, 
  Check, 
  Terminal,
  ShieldCheck,
  ChevronRight,
  Sparkles
} from 'lucide-react';
import { Task, TaskStage } from '../types';
import { PipelineStepper } from './PipelineStepper';
import { ActionBanner } from './ActionBanner';
import { TaskDetailsTabs } from './TaskDetailsTabs';
import { Trash2 } from 'lucide-react';

interface TaskDetailPaneProps {
  task: Task;
  onApplyTask: (taskId: string) => void;
  onRequestChanges: (taskId: string, feedback: string) => void;
  onDeleteTask?: (taskId: string) => void;
}

export function TaskDetailPane({
  task,
  onApplyTask,
  onRequestChanges,
  onDeleteTask
}: TaskDetailPaneProps) {
  const [activeTab, setActiveTab] = useState<string>('history');
  const [selectedStage, setSelectedStage] = useState<TaskStage>(task.currentStage);
  const [copiedKey, setCopiedKey] = useState(false);

  const handleCopyKey = () => {
    navigator.clipboard.writeText(task.key);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const handleDelete = () => {
    if (window.confirm(`Удалить задачу ${task.key}: "${task.title}"?`)) {
      onDeleteTask?.(task.id);
    }
  };

  const handleSelectStage = (stage: TaskStage) => {
    setSelectedStage(stage);
    // Automatically switch to relevant tab when clicking a pipeline stage
    if (stage === 'plan') setActiveTab('plan');
    if (stage === 'dev') setActiveTab('diff');
    if (stage === 'checks') setActiveTab('checks');
    if (stage === 'review') setActiveTab('review');
    if (stage === 'acceptance') setActiveTab('history');
  };

  return (
    <div className="flex-1 h-full overflow-y-auto bg-white dark:bg-zinc-950 p-6 space-y-6">
      {/* Task Header Bar */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          {/* Key & Model Badge */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyKey}
              className="inline-flex items-center gap-1 font-mono text-xs font-bold px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors cursor-pointer"
              title="Скопировать ключ задачи"
            >
              <span>{task.key}</span>
              {copiedKey ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3 text-zinc-400" />}
            </button>

            <span className="text-zinc-300 dark:text-zinc-700">·</span>

            <div className="flex items-center gap-1 text-[11px] font-mono text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/40 px-2 py-0.5 rounded border border-purple-200/50 dark:border-purple-900/40">
              <Cpu className="w-3 h-3" />
              <span>{task.model}</span>
            </div>

            <span className="text-zinc-300 dark:text-zinc-700">·</span>

            <div className="flex items-center gap-1 text-[11px] font-mono text-zinc-500">
              <GitBranch className="w-3 h-3 text-zinc-400" />
              <span className="truncate max-w-[200px]">{task.branch}</span>
            </div>
          </div>

          {/* Right Action: Status Label and Delete Button */}
          <div className="flex items-center gap-2">
            <div className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              <span>{task.statusLabel}</span>
            </div>

            {onDeleteTask && (
              <button
                onClick={handleDelete}
                className="p-1.5 rounded-md border border-zinc-200 dark:border-zinc-800 text-zinc-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
                title="Удалить задачу"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Task Title */}
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 leading-snug">
          {task.title}
        </h1>
      </div>

      {/* 1. Visual Pipeline Stepper (5 stages) */}
      <section aria-label="Пайплайн задачи">
        <PipelineStepper 
          task={task} 
          onSelectStage={handleSelectStage} 
          selectedStage={selectedStage} 
        />
      </section>

      {/* 2. Action Decision Banner ("Что требуется от вас" & "Текущее состояние и результат") */}
      <section aria-label="Действия оператора">
        <ActionBanner
          task={task}
          onApplyTask={onApplyTask}
          onRequestChanges={onRequestChanges}
          onSelectTab={setActiveTab}
        />
      </section>

      {/* 3. Tab Navigation and Detailed Panes (История, Задача, План, Diff, Проверки, Ревью) */}
      <section aria-label="Детали и артефакты" className="pt-2">
        <TaskDetailsTabs
          task={task}
          activeTab={activeTab}
          onSelectTab={setActiveTab}
        />
      </section>
    </div>
  );
}
