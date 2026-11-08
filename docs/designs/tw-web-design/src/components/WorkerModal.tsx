import React, { useState } from 'react';
import { 
  X, 
  Cpu, 
  Play, 
  Square, 
  RotateCw, 
  Terminal, 
  Activity, 
  CheckCircle2, 
  AlertCircle,
  Settings,
  HardDrive
} from 'lucide-react';
import { Project, Task } from '../types';
import { InteractiveWorkerTerminal } from './InteractiveWorkerTerminal';

interface WorkerModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project;
  tasks?: Task[];
  onToggleWorker: () => void;
  onRunTask?: (taskId: string) => void;
}

export function WorkerModal({ 
  isOpen, 
  onClose, 
  project, 
  tasks = [], 
  onToggleWorker,
  onRunTask 
}: WorkerModalProps) {
  const [activeTab, setActiveTab] = useState<'settings' | 'terminal'>('settings');
  const [concurrency, setConcurrency] = useState('2');
  const [sandboxType, setSandboxType] = useState('docker');
  const [logView, setLogView] = useState(true);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in-50">
      <div className={`bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl w-full p-5 shadow-2xl relative transition-all duration-200 ${
        activeTab === 'terminal' ? 'max-w-3xl' : 'max-w-xl'
      }`}>
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 p-1 rounded-lg cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 mb-1">
          <div className="w-7 h-7 rounded-lg bg-emerald-600 text-white flex items-center justify-center">
            <Cpu className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
            Управление воркером harness
          </h2>
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
          Локальный фоновый сервис выполнения задач, изоляции файловой системы и интеграции с LLM.
        </p>

        {/* Tab switchers: Settings vs Interactive Terminal */}
        <div className="flex items-center gap-2 mb-4 border-b border-zinc-200 dark:border-zinc-800 pb-2">
          <button
            onClick={() => setActiveTab('settings')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'settings'
                ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
            }`}
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Параметры и статус</span>
          </button>

          <button
            onClick={() => setActiveTab('terminal')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'terminal'
                ? 'bg-blue-600 text-white'
                : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>Интерактивный CLI терминал</span>
            <span className="text-[9px] px-1.5 py-0.2 rounded-full font-mono bg-blue-500/20 text-blue-300 ml-1">
              fork
            </span>
          </button>
        </div>

        {activeTab === 'terminal' ? (
          <div className="h-[420px]">
            <InteractiveWorkerTerminal
              project={project}
              tasks={tasks}
              onRunTask={onRunTask}
              embedded={true}
            />
          </div>
        ) : (
          <>
            {/* Status Callout Card */}
            <div className={`p-3.5 rounded-xl border flex items-center justify-between mb-4 ${
              project.workerRunning
                ? 'bg-emerald-50/60 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/60'
                : 'bg-zinc-50 dark:bg-zinc-800/50 border-zinc-200 dark:border-zinc-700'
            }`}>
              <div className="flex items-center gap-2.5">
                <div className={`w-3 h-3 rounded-full ${project.workerRunning ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-400'}`} />
                <div>
                  <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                    {project.workerRunning ? 'Worker активен и слушает команды' : 'Worker остановлен'}
                  </div>
                  <div className="text-[11px] text-zinc-500 dark:text-zinc-400 font-mono">
                    PID: 84920 · Порт: {project.workerPort} · ws://127.0.0.1:{project.workerPort}/events
                  </div>
                </div>
              </div>

              <button
                onClick={onToggleWorker}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer ${
                  project.workerRunning
                    ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 border border-rose-200 dark:border-rose-900 hover:bg-rose-100'
                    : 'bg-emerald-600 text-white hover:bg-emerald-700'
                }`}
              >
                {project.workerRunning ? (
                  <>
                    <Square className="w-3.5 h-3.5 fill-current" />
                    <span>Остановить</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Запустить</span>
                  </>
                )}
              </button>
            </div>

            {/* Configuration settings */}
            <div className="grid grid-cols-2 gap-3 mb-4 text-xs">
              <div>
                <label className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                  Режим изоляции (Sandbox)
                </label>
                <select
                  value={sandboxType}
                  onChange={(e) => setSandboxType(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200"
                >
                  <option value="docker">Docker контейнер (Строгая изоляция)</option>
                  <option value="node">Node.js subprocess (Быстрый старт)</option>
                  <option value="bubblewrap">Bubblewrap / Landlock (Linux jail)</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                  Параллельные задачи
                </label>
                <select
                  value={concurrency}
                  onChange={(e) => setConcurrency(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200"
                >
                  <option value="1">1 задача (Минимальное потребление CPU)</option>
                  <option value="2">2 задачи (Рекомендуется)</option>
                  <option value="4">4 задачи (Многоядерный CPU)</option>
                </select>
              </div>
            </div>

            {/* Live daemon stdout log */}
            <div>
              <div className="flex items-center justify-between mb-1.5 text-xs text-zinc-500">
                <span className="font-semibold text-zinc-800 dark:text-zinc-200 flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-zinc-400" />
                  <span>Лог демона воркера</span>
                </span>
                <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-400">
                  ● live stream
                </span>
              </div>

              <div className="p-3 rounded-lg bg-zinc-950 text-zinc-300 font-mono text-[11px] h-32 overflow-y-auto border border-zinc-800 space-y-1">
                <div className="text-zinc-500">[10:24:00] [harness-daemon] Starting HTTP/WS server on 127.0.0.1:{project.workerPort}</div>
                <div className="text-zinc-500">[10:24:01] [sandbox-init] Docker environment verified. Found image `node:22-alpine`</div>
                <div className="text-emerald-400">[10:24:02] [task-queue] TASK-1 dispatched to claude-3-7-sonnet runner</div>
                <div className="text-zinc-400">[10:26:45] [checks] Ran: pnpm exec tsc --noEmit (exit code: 0)</div>
                <div className="text-zinc-400">[10:27:40] [stage-transition] TASK-1 transitioned to `acceptance` stage</div>
                <div className="text-amber-400">[10:27:41] [harness] Awaiting human operator approval for commit</div>
              </div>
            </div>
          </>
        )}

        <div className="flex items-center justify-end gap-2 pt-4 mt-4 border-t border-zinc-100 dark:border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs font-semibold hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors cursor-pointer"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}
