'use client'
import React, { useState, useRef, useEffect } from 'react'
import { 
  Terminal as TerminalIcon, 
  Play, 
  Trash2, 
  X, 
  Send, 
  Copy, 
  Check, 
  Cpu, 
  Layers 
} from 'lucide-react'
import type { Status, Task } from '@/lib/contracts'

interface InteractiveTerminalProps {
  status?: Status
  selectedTask?: Task
  projectName: string
  onClose: () => void
}

interface LogEntry {
  id: string
  cmd: string
  output: React.ReactNode
  time: string
}

export function InteractiveTerminal({
  status,
  selectedTask,
  projectName,
  onClose
}: InteractiveTerminalProps) {
  const [inputVal, setInputVal] = useState('')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [copied, setCopied] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const isRunning = status?.worker.running ?? false
  const pid = status?.worker.pid
  const currentTaskId = status?.worker.task_id

  useEffect(() => {
    setLogs([
      {
        id: 'init-1',
        cmd: 'worker status',
        output: (
          <div className="space-y-1 font-mono text-xs">
            <div className={`font-semibold ${isRunning ? 'text-emerald-400' : 'text-zinc-400'}`}>
              ● tw-worker daemon {isRunning ? '[ONLINE]' : '[STOPPED]'}
            </div>
            <div className="text-zinc-300">
              Проект: <span className="text-blue-400">{projectName}</span> · PID: {pid ?? 'нет'}
            </div>
            {currentTaskId && (
              <div className="text-amber-300">
                Активная задача в очереди: #{currentTaskId}
              </div>
            )}
            {selectedTask?.observation?.terminal_command && (
              <div className="text-zinc-400">
                Команда наблюдения: <code className="text-zinc-200">{selectedTask.observation.terminal_command}</code>
              </div>
            )}
            <div className="text-zinc-500">
              Подсказка: введите &quot;help&quot; для списка команд.
            </div>
          </div>
        ),
        time: new Date().toLocaleTimeString().slice(0, 5)
      }
    ])
  }, [isRunning, pid, currentTaskId, projectName])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const handleCommand = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = inputVal.trim()
    if (!trimmed) return

    const now = new Date().toLocaleTimeString().slice(0, 5)
    let output: React.ReactNode = null

    if (trimmed === 'help') {
      output = (
        <div className="space-y-0.5 text-zinc-300">
          <div>Доступные команды терминала воркера:</div>
          <div>  <span className="text-blue-400">status</span>    - показать статус демона и воркера</div>
          <div>  <span className="text-blue-400">task</span>      - показать информацию о выбранной задаче</div>
          <div>  <span className="text-blue-400">clear</span>     - очистить окно консоли</div>
          <div className="text-zinc-500">
            Пакетные команды запуска и перезапуска контейнеров помечены [В разработке].
          </div>
        </div>
      )
    } else if (trimmed === 'status' || trimmed === 'worker status') {
      output = (
        <div className="text-zinc-300">
          Воркер: {isRunning ? 'Активен' : 'Остановлен'} (PID: {pid ?? 'нет'})
        </div>
      )
    } else if (trimmed === 'task') {
      output = selectedTask ? (
        <div className="text-zinc-300">
          Задача #{selectedTask.id}: {selectedTask.request.split('\n')[0]} (Состояние: {selectedTask.state})
        </div>
      ) : (
        <div className="text-zinc-500">Нет выбранной задачи.</div>
      )
    } else if (trimmed === 'clear') {
      setLogs([])
      setInputVal('')
      return
    } else {
      output = (
        <div className="text-amber-400/90 text-xs">
          Команда &quot;{trimmed}&quot; ожидает реализации в API контроллера.
        </div>
      )
    }

    setLogs(prev => [
      ...prev,
      {
        id: `cmd-${Date.now()}`,
        cmd: trimmed,
        output,
        time: now
      }
    ])
    setInputVal('')
  }

  const handleCopyLogs = () => {
    const text = logs.map(l => `[${l.time}] > ${l.cmd}`).join('\n')
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="w-full bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col max-h-96">
      <div className="px-4 py-2.5 bg-zinc-900 border-b border-zinc-800/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TerminalIcon className="w-4 h-4 text-emerald-400" />
          <span className="font-semibold text-zinc-200">
            Терминал автономного воркера (tw-worker)
          </span>
          <span className={`w-2 h-2 rounded-full ${isRunning ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={handleCopyLogs}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer"
            title="Скопировать историю"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={() => setLogs([])}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer"
            title="Очистить терминал"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer ml-1"
            title="Закрыть терминал (Esc или Ctrl+`)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 p-4 overflow-y-auto space-y-3 min-h-[160px] max-h-[260px] text-zinc-300">
        {logs.map(log => (
          <div key={log.id} className="space-y-1">
            <div className="flex items-center gap-2 text-zinc-500 text-[11px]">
              <span className="text-emerald-400 font-bold">&gt;</span>
              <span className="text-zinc-200 font-semibold">{log.cmd}</span>
              <span className="ml-auto text-[10px]">{log.time}</span>
            </div>
            <div className="pl-3.5 leading-relaxed">{log.output}</div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleCommand} className="p-2.5 bg-zinc-900/90 border-t border-zinc-800/80 flex items-center gap-2">
        <span className="text-emerald-400 font-bold pl-2">&gt;</span>
        <input
          type="text"
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          placeholder="worker status, task, help..."
          className="flex-1 bg-transparent text-zinc-100 placeholder:text-zinc-600 focus:outline-none text-xs"
        />
        <button
          type="submit"
          className="px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold transition-colors cursor-pointer"
        >
          Ввод
        </button>
      </form>
    </div>
  )
}
