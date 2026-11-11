'use client'
import { AttachmentPicker } from './task-attachments'
import type { Attachment } from '@/lib/contracts'
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
  onOpenChange: controlledOnOpenChange,
  defaultBackend = 'codex'
}: {
  transport: Transport
  session?: Session
  enabled: boolean
  onCreated: (id: number) => void
  open?: boolean
  onOpenChange?: (open: boolean) => void
  defaultBackend?: string
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
  const [backend, setBackend] = useState(restored?.body.backend ?? 'default')
  const [dependencies,setDependencies] = useState(restored?.body.depends_on?.join(', ') ?? '')
  const [manualAcceptance,setManualAcceptance] = useState(restored?.body.manual_acceptance ?? false)
  const [autoStart, setAutoStart] = useState(restored?.body.placement ? restored.body.placement !== 'backlog' : true)
  const [files,setFiles]=useState<Attachment[]>(restored?.files??[])
  const [uploading,setUploading]=useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<PendingCreation | undefined>(restored)
  const lock = useRef(false)

  async function submit() {
    if (lock.current || uploading || !session?.csrf_token) return
    lock.current = true
    setBusy(true)
    setError('')
    const body: { request: string; approval_mode: string; placement?: string; backend?: string; manual_acceptance?: boolean; depends_on?: number[];attachments?:string[] } = {
      request: text,
      approval_mode: mode
    }
    if (dependencies.trim()) {
      const numbers=dependencies.split(',').map(part=>Number(part.trim()))
      if(numbers.length>100||numbers.some(number=>!Number.isSafeInteger(number)||number<1)||new Set(numbers).size!==numbers.length){
        setError('Укажите разные положительные номера задач через запятую')
        lock.current=false;setBusy(false);return
      }
      body.depends_on=numbers
    }
    if (manualAcceptance) body.manual_acceptance = true
    if (backend !== 'default') {
      body.backend = backend
    }
    if (!autoStart) {
      body.placement = 'backlog'
    }
    if(files.length)body.attachments=files.map(file=>file.id)
    const signature = JSON.stringify(body)
    if (pending.current && JSON.stringify(pending.current.body) !== signature) {
      setError('Предыдущий запрос имеет неопределённый результат. Верните прежние данные для повтора.')
      lock.current = false
      setBusy(false)
      return
    }
    try {
      if (!pending.current) {
        const command = { body, files, key: crypto.randomUUID() }
        writePending(pendingSlot(transport, 'create'), command)
        pending.current = command
      }
      const created = await transport.post<{ task: Task; revision: string }>('tasks', body, pending.current.key, session.csrf_token)
      if (!created.task || !Number.isSafeInteger(created.task.id) || created.task.id <= 0 || typeof created.revision !== 'string') {
        throw Error('Контроллер вернул некорректный результат создания')
      }
      clearPending()
      setText('')
      setFiles([])
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
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-xl max-h-[90vh] overflow-y-auto bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl p-6 shadow-2xl animate-in fade-in-50 zoom-in-95 focus:outline-none"
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

            <AttachmentPicker files={files} onChange={setFiles} onBusy={setUploading} transport={transport} csrf={session?.csrf_token} disabled={busy||!enabled||Boolean(pending.current)}/>
            {/* Backend & Approval Mode grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label htmlFor="backend" className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1 flex items-center justify-between">
                  <span className="flex items-center gap-1">
                    <Cpu className="w-3 h-3 text-purple-500" />
                    <span>Исполнитель (Агент)</span>
                  </span>
                </label>
                <select
                  id="backend"
                  value={backend}
                  onChange={e => setBackend(e.target.value)}
                  disabled={busy}
                  className="w-full text-xs px-2.5 py-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer"
                >
                  <option value="default">
                    {`По умолчанию (${defaultBackend === 'gemini' ? 'Gemini' : 'Codex'})`}
                  </option>
                  <option value="gemini">Gemini (Google)</option>
                  <option value="codex">Codex (OpenAI)</option>
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

            <label className="text-xs">Зависит от задач
              <input className="w-full rounded border p-2 mt-1" value={dependencies} onChange={event=>setDependencies(event.target.value)} placeholder="Например: 14, 15" disabled={busy}/>
              <span className="text-zinc-500">Пусто — независимая задача. Запуск после применения всех указанных результатов.</span>
            </label>
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={manualAcceptance} onChange={event=>setManualAcceptance(event.target.checked)} disabled={busy}/>
              Обязательно показать мне перед применением
            </label>
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

            {Boolean(pending.current) && (
              <div className="p-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-300">
                Ожидается подтверждение предыдущего создания задачи. Нажмите «Создать задачу» для повтора запроса с сохранёнными параметрами.
              </div>
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
                disabled={busy || uploading || !session?.csrf_token || !text.trim() || !withinLimit(text, 51200)}
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
