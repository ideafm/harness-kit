'use client'
import { useEffect, useRef, useState } from 'react'
import type { Session, Transport, Task } from '@/lib/contracts'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Dialog } from 'radix-ui'
import { readPending, writePending, pendingSlot, type PendingCreation } from '@/lib/transport'
import { ApiError, withinLimit } from '@/lib/http-transport'
import { Sparkles, X, Send, Cpu, Layers } from 'lucide-react'

export function CreateTaskSheet({
  transport,
  session,
  enabled,
  onCreated,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange
}: {
  transport: Transport
  session?: Session
  enabled: boolean
  onCreated: (id: number) => void
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const active = useRef(true)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])

  const [restored] = useState(() => readPending<PendingCreation>(pendingSlot(transport, 'create')))
  function clearPending() {
    if (readPending<PendingCreation>(pendingSlot(transport, 'create'))?.key === pending.current?.key) {
      writePending(pendingSlot(transport, 'create'), undefined)
    }
    pending.current = undefined
  }

  const [internalOpen, setInternalOpen] = useState(false)
  const open = controlledOpen !== undefined ? controlledOpen : internalOpen
  function setOpen(v: boolean) {
    if (controlledOnOpenChange) controlledOnOpenChange(v)
    setInternalOpen(v)
  }

  const [text, setText] = useState(restored?.body.request ?? '')
  const [mode, setMode] = useState(restored?.body.approval_mode ?? 'approve-plan')
  const [model, setModel] = useState('codex')
  const [autoStart, setAutoStart] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<PendingCreation | undefined>(restored)
  const lock = useRef(false)

  async function submit() {
    if (lock.current || !session?.csrf_token) return
    lock.current = true
    setBusy(true)
    setError('')
    const body: { request: string; approval_mode: string; placement?: string } = {
      request: text,
      approval_mode: mode
    }
    if (!autoStart) {
      body.placement = 'backlog'
    }
    const signature = JSON.stringify(body)
    if (pending.current && JSON.stringify(pending.current.body) !== signature) {
      setError('Предыдущий запрос имеет неопределённый результат. Верните прежние данные для повтора.')
      lock.current = false
      setBusy(false)
      return
    }
    try {
      if (!pending.current) {
        const command = { body, key: crypto.randomUUID() }
        writePending(pendingSlot(transport, 'create'), command)
        pending.current = command
      }
      const created = await transport.post<{ task: Task; revision: string }>('tasks', body, pending.current.key, session.csrf_token)
      if (!created.task || !Number.isSafeInteger(created.task.id) || created.task.id <= 0 || typeof created.revision !== 'string') {
        throw Error('Контроллер вернул некорректный результат создания')
      }
      clearPending()
      setText('')
      setOpen(false)
      if (active.current) onCreated(created.task.id)
    } catch (e) {
      if (e instanceof ApiError && e.status && e.status >= 400 && e.status < 500 && e.status !== 408) {
        clearPending()
      }
      setError(e instanceof Error ? e.message : 'Ошибка создания')
    } finally {
      lock.current = false
      setBusy(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={v => { if (!busy) setOpen(v) }}>
      <Dialog.Trigger asChild>
        <Button disabled={!enabled || !session?.csrf_token} className="cursor-pointer">
          ＋ Новая задача
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 z-50 bg-black/60 backdrop-blur-xs animate-in fade-in-50" />
        <Dialog.Content
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl p-6 shadow-2xl animate-in fade-in-50 zoom-in-95 focus:outline-none"
          aria-describedby={undefined}
        >
          <Dialog.Close
            aria-label="Закрыть"
            disabled={busy}
            className="absolute right-4 top-4 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 p-1.5 rounded-lg cursor-pointer transition-colors"
          >
            <X className="w-4 h-4" />
          </Dialog.Close>

          {/* Header */}
          <div className="flex items-center gap-2.5 mb-1.5">
            <div className="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center shadow-2xs shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <Dialog.Title className="text-sm sm:text-base font-bold text-zinc-900 dark:text-zinc-100">
              Создать задачу для автономного агента
            </Dialog.Title>
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-4 leading-relaxed">
            Агент выполнит полный цикл разработки: спланирует изменения, напишет код, прогонит тесты и подготовит патч.
          </p>

          <div className="space-y-4">
            {/* Request prompt */}
            <div>
              <label htmlFor="request" className="block text-xs font-semibold text-zinc-800 dark:text-zinc-200 mb-1">
                Запрос
              </label>
              <Textarea
                id="request"
                rows={5}
                className="w-full text-xs p-3 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono resize-y"
                placeholder="Подробно опишите задачу для агента: требования, поведение, файлы или проверки..."
                value={text}
                onChange={e => setText(e.target.value)}
                disabled={busy}
              />
              {!withinLimit(text, 51200) && (
                <p role="alert" className="text-xs text-rose-500 mt-1">
                  Запрос превышает 50 КиБ.
                </p>
              )}
            </div>

            {/* Model & Approval Mode grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label htmlFor="model" className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1 flex items-center justify-between">
                  <span className="flex items-center gap-1">
                    <Cpu className="w-3 h-3 text-purple-500" />
                    <span>Модель рассуждений</span>
                  </span>
                  <span className="text-[10px] font-normal text-zinc-400 dark:text-zinc-500">скоро</span>
                </label>
                <select
                  id="model"
                  value={model}
                  onChange={e => setModel(e.target.value)}
                  disabled={true}
                  title="Выбор модели на уровне задачи пока не поддерживается API; используется модель из конфигурации воркера"
                  className="w-full text-xs px-2.5 py-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-900/60 text-zinc-500 dark:text-zinc-400 cursor-not-allowed opacity-75 focus:outline-none"
                >
                  <optgroup label="Codex">
                    <option value="codex">Codex (по умолчанию)</option>
                    <option value="codex-o3-mini">Codex (o3-mini / High Reasoning)</option>
                    <option value="codex-gpt-4o">Codex (GPT-4o / Fast)</option>
                  </optgroup>
                  <optgroup label="Gemini">
                    <option value="gemini-2.5-pro">Gemini 2.5 Pro (Deep Reasoning)</option>
                    <option value="gemini-2.0-flash">Gemini 2.0 Flash (Fast Execution)</option>
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (Balanced)</option>
                  </optgroup>
                </select>
              </div>

              <div>
                <label htmlFor="mode" className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1 flex items-center gap-1">
                  <Layers className="w-3 h-3 text-blue-500" />
                  <span>Режим утверждения</span>
                </label>
                <select
                  id="mode"
                  value={mode}
                  onChange={e => setMode(e.target.value)}
                  disabled={busy}
                  className="w-full text-xs px-2.5 py-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer"
                >
                  <option value="approve-plan">Сначала утвердить план</option>
                  <option value="auto">Автоматическая работа</option>
                </select>
              </div>
            </div>

            {/* Auto Start Checkbox */}
            <div className="flex items-center gap-2 pt-0.5">
              <input
                type="checkbox"
                id="autoStart"
                checked={autoStart}
                onChange={e => setAutoStart(e.target.checked)}
                disabled={busy}
                className="rounded text-blue-600 focus:ring-blue-500 cursor-pointer"
              />
              <label htmlFor="autoStart" className="text-xs text-zinc-700 dark:text-zinc-300 select-none cursor-pointer">
                Запустить выполнение сразу через воркер harness
              </label>
            </div>

            {mode === 'auto' && (
              <p className="muted text-[11px] text-zinc-500">
                Auto не предоставляет модели человеческих полномочий приёмки или доступа.
              </p>
            )}

            {error && (
              <p role="alert" className="text-xs text-rose-600 dark:text-rose-400">
                {error}
              </p>
            )}

            {/* Footer Buttons */}
            <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-100 dark:border-zinc-800">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setOpen(false)}
                disabled={busy}
                className="cursor-pointer"
              >
                Отмена
              </Button>
              <Button
                size="sm"
                className="bg-blue-600 hover:bg-blue-700 text-white flex items-center gap-1.5 cursor-pointer shadow-xs hover:shadow"
                disabled={busy || !session?.csrf_token || !text.trim() || !withinLimit(text, 51200)}
                onClick={() => void submit()}
              >
                <Send className="w-3.5 h-3.5" />
                <span>{busy ? 'Ожидаем контроллер…' : 'Создать задачу'}</span>
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export const CreateTaskModal = CreateTaskSheet
