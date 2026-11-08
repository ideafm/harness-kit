import React, { useState, useRef, useEffect } from 'react';
import { 
  Terminal as TerminalIcon, 
  Play, 
  RotateCw, 
  Trash2, 
  Maximize2, 
  Minimize2, 
  X, 
  Send,
  HelpCircle,
  Copy,
  Check,
  Cpu,
  FolderGit2
} from 'lucide-react';
import { Project, Task } from '../types';

interface InteractiveWorkerTerminalProps {
  project: Project;
  tasks: Task[];
  onRunTask?: (taskId: string) => void;
  onClose?: () => void;
  isFloating?: boolean;
  embedded?: boolean;
}

interface CommandHistoryItem {
  id: string;
  command: string;
  output: React.ReactNode;
  timestamp: string;
}

export function InteractiveWorkerTerminal({
  project,
  tasks,
  onRunTask,
  onClose,
  isFloating = false,
  embedded = false
}: InteractiveWorkerTerminalProps) {
  const [inputVal, setInputVal] = useState('');
  const [history, setHistory] = useState<CommandHistoryItem[]>([
    {
      id: 'init-1',
      command: 'worker status',
      output: (
        <div className="text-zinc-300 space-y-0.5">
          <div className="text-emerald-400 font-semibold">● tw-worker daemon v0.9.4 [ONLINE]</div>
          <div>PID: 84920 · Порт: {project.workerPort} · Sandbox: Docker (node:22-alpine)</div>
          <div>CPU: 1.4% · Memory: 148MB / 2048MB · Concurrency limit: 2</div>
          <div className="text-zinc-500">Введите &quot;help&quot; для списка команд.</div>
        </div>
      ),
      timestamp: '10:24:00'
    }
  ]);
  const [cmdHistoryList, setCmdHistoryList] = useState<string[]>(['worker status']);
  const [historyPointer, setHistoryPointer] = useState<number>(-1);
  const [isCopied, setIsCopied] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);

  const terminalEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history]);

  const handleRunCommand = (rawCmd: string) => {
    const cmd = rawCmd.trim();
    if (!cmd) return;

    const time = new Date().toLocaleTimeString().slice(0, 8);
    let output: React.ReactNode = null;
    const parts = cmd.split(' ');
    const mainCmd = parts[0].toLowerCase();
    const arg = parts.slice(1).join(' ').trim();

    switch (mainCmd) {
      case 'help':
        output = (
          <div className="text-zinc-300 space-y-1">
            <div className="text-blue-400 font-bold">Доступные команды tw-worker CLI:</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 text-[11px] text-zinc-400">
              <div><span className="text-emerald-400 font-mono">tasks</span> — список задач проекта и их статусы</div>
              <div><span className="text-emerald-400 font-mono">run &lt;ID&gt;</span> — запустить задачу в контейнере (например: run 1)</div>
              <div><span className="text-emerald-400 font-mono">git status</span> — статус репозитория и ветки</div>
              <div><span className="text-emerald-400 font-mono">pnpm test</span> — запуск набора тестов в sandbox</div>
              <div><span className="text-emerald-400 font-mono">lint</span> — проверка типов tsc и eslint</div>
              <div><span className="text-emerald-400 font-mono">status</span> — телеметрия воркера и docker контейнера</div>
              <div><span className="text-emerald-400 font-mono">clear</span> — очистить вывод терминала</div>
            </div>
          </div>
        );
        break;

      case 'tasks':
        output = (
          <div className="space-y-1 text-zinc-300 font-mono text-[11px]">
            <div className="text-blue-400 font-bold font-sans">Очередь задач проекта {project.name}:</div>
            <div className="border-t border-zinc-800 pt-1 divide-y divide-zinc-900">
              {tasks.map(t => (
                <div key={t.id} className="py-1 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-blue-400">{t.key}</span>
                    <span className="truncate max-w-xs text-zinc-200">{t.title}</span>
                  </div>
                  <div className="flex items-center gap-2 text-zinc-400">
                    <span className="text-[10px] text-purple-400">[{t.model}]</span>
                    <span className={t.status === 'accepted_applied' ? 'text-emerald-400' : 'text-amber-400'}>
                      {t.currentStageLabel}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
        break;

      case 'status':
      case 'worker':
        output = (
          <div className="text-zinc-300 space-y-1 font-mono text-[11px]">
            <div className="text-emerald-400 font-bold">tw-worker daemon diagnostics:</div>
            <div>• Репозиторий: <span className="text-blue-400">{project.repoPath}</span></div>
            <div>• Ветка: <span className="text-zinc-200">{project.activeBranch}</span></div>
            <div>• HTTP / WS: <span className="text-zinc-200">http://127.0.0.1:{project.workerPort}</span></div>
            <div>• Docker Sandbox: <span className="text-emerald-400">node:22-alpine (healthy)</span></div>
            <div>• Доступные провайдеры LLM: claude-3-7-sonnet, gemini-2.0-flash, gpt-4o</div>
            <div>• Активных соединений: 1 клиент (tw-web browser)</div>
          </div>
        );
        break;

      case 'run':
        if (!arg) {
          output = <div className="text-rose-400">Ошибка: укажите номер или ключ задачи (например: run 1 или run TASK-5)</div>;
        } else {
          const targetTask = tasks.find(t => 
            t.num.toString() === arg || 
            t.key.toLowerCase() === arg.toLowerCase() ||
            t.id === arg
          );
          if (targetTask) {
            onRunTask?.(targetTask.id);
            output = (
              <div className="space-y-1 text-[11px] font-mono">
                <div className="text-emerald-400">✓ Задача {targetTask.key} успешно отправлена в Docker контейнер!</div>
                <div className="text-zinc-400">[harness] Spawning worker subprocess: PID 91044</div>
                <div className="text-purple-400">[model: {targetTask.model}] Generating context plan graph...</div>
                <div className="text-zinc-500">Следите за прогрессом на панели этапов или вкладке &quot;История&quot;.</div>
              </div>
            );
          } else {
            output = <div className="text-rose-400">Задача &quot;{arg}&quot; не найдена в текущем проекте. Введите &quot;tasks&quot;.</div>;
          }
        }
        break;

      case 'git':
        if (arg === 'status') {
          output = (
            <div className="font-mono text-[11px] text-zinc-300 space-y-0.5">
              <div className="text-blue-400">On branch {project.activeBranch}</div>
              <div>Your branch is up to date with &apos;origin/{project.activeBranch}&apos;.</div>
              <div className="text-zinc-400 pt-1">Changes not staged for commit:</div>
              <div className="text-rose-400 pl-4">modified:   src/components/PipelineStepper.tsx</div>
              <div className="text-rose-400 pl-4">modified:   src/components/TaskDetailPane.tsx</div>
              <div className="text-zinc-500 pt-1">Untracked files:</div>
              <div className="text-emerald-400 pl-4">src/components/InteractiveWorkerTerminal.tsx</div>
            </div>
          );
        } else {
          output = <div className="text-zinc-400 font-mono">git: {arg || 'команда выполнена успешно'}.</div>;
        }
        break;

      case 'test':
      case 'pnpm':
      case 'npm':
        output = (
          <div className="font-mono text-[11px] space-y-0.5">
            <div className="text-zinc-400">$ vitest run --coverage</div>
            <div className="text-emerald-400">✓ src/components/__tests__/PipelineStepper.test.tsx (5 tests passed)</div>
            <div className="text-emerald-400">✓ src/utils/__tests__/harness.test.ts (7 tests passed)</div>
            <div className="text-zinc-300 font-semibold pt-1">Test Files: 2 passed (2) | Tests: 12 passed (12)</div>
            <div className="text-zinc-400">Duration: 1.84s (transform 140ms, setup 0ms, collect 320ms, tests 1.38s)</div>
          </div>
        );
        break;

      case 'lint':
        output = (
          <div className="font-mono text-[11px] text-emerald-400 space-y-0.5">
            <div>$ tsc --noEmit && eslint src/</div>
            <div>✓ 0 errors, 0 warnings found in 14 modules.</div>
          </div>
        );
        break;

      case 'clear':
        setHistory([]);
        setInputVal('');
        return;

      default:
        output = (
          <div className="text-zinc-400 font-mono text-[11px]">
            bash: {cmd}: команда выполнена с кодом возврата 0. Введите <span className="text-blue-400">help</span> для списка специфичных команд harness.
          </div>
        );
        break;
    }

    setHistory(prev => [
      ...prev,
      {
        id: `cmd-${Date.now()}`,
        command: cmd,
        output,
        timestamp: time
      }
    ]);

    setCmdHistoryList(prev => [...prev, cmd]);
    setHistoryPointer(-1);
    setInputVal('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleRunCommand(inputVal);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (cmdHistoryList.length === 0) return;
      const nextIdx = historyPointer === -1 ? cmdHistoryList.length - 1 : Math.max(0, historyPointer - 1);
      setHistoryPointer(nextIdx);
      setInputVal(cmdHistoryList[nextIdx] || '');
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyPointer === -1) return;
      const nextIdx = historyPointer + 1;
      if (nextIdx >= cmdHistoryList.length) {
        setHistoryPointer(-1);
        setInputVal('');
      } else {
        setHistoryPointer(nextIdx);
        setInputVal(cmdHistoryList[nextIdx] || '');
      }
    }
  };

  const handleCopyAll = () => {
    const raw = history.map(h => `$ ${h.command}`).join('\n');
    navigator.clipboard.writeText(raw);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const PRESET_COMMANDS = ['help', 'tasks', 'status', 'git status', 'pnpm test', 'clear'];

  return (
    <div className={`flex flex-col rounded-xl overflow-hidden border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-2xl transition-all ${
      isMaximized 
        ? 'fixed inset-4 z-50' 
        : embedded 
          ? 'w-full h-full min-h-[340px] rounded-lg' 
          : isFloating 
            ? 'w-full h-96' 
            : 'w-full h-72'
    }`}>
      {/* Terminal Titlebar */}
      <div className="px-3.5 py-2 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between text-xs select-none shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
          </div>

          <div className="flex items-center gap-1.5 font-mono text-[11px] text-zinc-300">
            <TerminalIcon className="w-3.5 h-3.5 text-blue-400" />
            <span>tw-worker-pty :47831</span>
            <span className="text-zinc-500">({project.name})</span>
          </div>
        </div>

        {/* Quick presets & window controls */}
        <div className="flex items-center gap-1.5">
          <div className="hidden sm:flex items-center gap-1 mr-2">
            {PRESET_COMMANDS.map(preset => (
              <button
                key={preset}
                onClick={() => handleRunCommand(preset)}
                className="px-1.5 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 text-[10px] font-mono transition-colors cursor-pointer"
              >
                {preset}
              </button>
            ))}
          </div>

          <button
            onClick={handleCopyAll}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer"
            title="Скопировать историю команд"
          >
            {isCopied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          <button
            onClick={() => setIsMaximized(!isMaximized)}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer"
            title={isMaximized ? 'Свернуть' : 'Развернуть во весь экран'}
          >
            {isMaximized ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer ml-1"
              title="Закрыть терминал"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Terminal Output Area */}
      <div 
        onClick={() => inputRef.current?.focus()}
        className="flex-1 p-3.5 overflow-y-auto font-mono text-xs space-y-3 cursor-text bg-zinc-950"
      >
        {history.map(item => (
          <div key={item.id} className="space-y-1">
            <div className="flex items-center gap-2 text-zinc-400 text-[11px]">
              <span className="text-blue-400 font-bold">tw-worker@{project.name}:~$</span>
              <span className="text-zinc-100 font-semibold">{item.command}</span>
              <span className="text-zinc-600 text-[10px] ml-auto select-none">{item.timestamp}</span>
            </div>
            <div className="pl-2 border-l border-zinc-800/80">
              {item.output}
            </div>
          </div>
        ))}
        <div ref={terminalEndRef} />
      </div>

      {/* Terminal Input Prompt Bar */}
      <div className="p-2.5 bg-zinc-900/90 border-t border-zinc-800 flex items-center gap-2 font-mono text-xs shrink-0">
        <span className="text-emerald-400 font-bold select-none text-[11px]">
          tw-worker@{project.name}:~$
        </span>
        <input
          ref={inputRef}
          type="text"
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Введите команду... (например: help, tasks, run 1, git status)"
          className="flex-1 bg-transparent border-none outline-none text-zinc-100 placeholder:text-zinc-600 font-mono text-xs"
        />
        <button
          onClick={() => handleRunCommand(inputVal)}
          disabled={!inputVal.trim()}
          className="px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-sans flex items-center gap-1 transition-colors disabled:opacity-30 cursor-pointer"
        >
          <Send className="w-3 h-3" />
          <span>Выполнить</span>
        </button>
      </div>
    </div>
  );
}
