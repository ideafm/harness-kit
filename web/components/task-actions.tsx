'use client'
import { useEffect, useRef, useState } from 'react'
import type { Control, Transport, Session, Operation } from '@/lib/contracts'
import { AppIcon } from './app-icon'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { TrustedDecisionWidget } from './trusted-decision-widget'
import { DecisionDialog } from './decision-dialog'
import { Dialog } from 'radix-ui'
import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription, AlertDialogCancel } from './ui/alert-dialog'
import { ApiError, withinLimit } from '@/lib/http-transport'
import { readPending, writePending, pendingSlot, type PendingCommand } from "@/lib/transport"
import { label } from '@/lib/task-presentation'

export function TaskActions({
  control,
  transport,
  session,
  onRefresh,
  requestDelete = false,
  onDeleteRequestHandled,
  commandsDisabled = false,
  modalAnswer = false
}: {
  control: Control
  transport: Transport
  session?: Session
  onRefresh: () => void
  requestDelete?: boolean
  onDeleteRequestHandled?: () => void
  commandsDisabled?: boolean
  modalAnswer?: boolean
}) {
  const slot = pendingSlot(transport, `task:${control.task.id}`)
  const active = useRef(true)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])

  const [restored] = useState(() => readPending<PendingCommand>(slot))
  function save(value: PendingCommand | undefined) {
    const stored = readPending<PendingCommand>(slot)
    if (!pending.current || stored?.key === pending.current.key) writePending(slot, value)
    pending.current = value
  }

  const [answer, setAnswer] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  useEffect(() => {
    if (!requestDelete || commandsDisabled) return
    if (control.allowed_actions.includes('delete')) setDeleteOpen(true)
    onDeleteRequestHandled?.()
  }, [requestDelete, commandsDisabled, control.allowed_actions, onDeleteRequestHandled])
  const locked = useRef(false)
  const pending = useRef<PendingCommand | undefined>(restored)

  async function run(action?: string, targetBackend?: string) {
    if (commandsDisabled || locked.current || !session?.csrf_token) return
    if (action && pending.current) return
    if (!pending.current) {
      if (!action || !control.allowed_actions.includes(action)) return
      let body: Record<string, unknown> = { action }
      if (action === 'answer') {
        body = { action, question_id: control.pending_question_id, text: answer }
      } else if (action === 'switch_backend') {
        body = { action, backend: targetBackend || (control.task.backend === 'gemini' ? 'codex' : 'gemini') }
      }
      try {
        save({ action, taskId: control.task.id, body, revision: control.revision, key: crypto.randomUUID() })
      } catch {
        setMessage("Не удалось сохранить команду. Отправка отменена.")
        return
      }
    }
    const command = pending.current
    if (!command) return
    if (!['start', 'pause', 'resume', 'answer', 'switch_backend', 'delete', 'restore', 'enqueue'].includes(command.action) || !['start', 'pause', 'resume', 'answer', 'switch_backend', 'delete', 'restore', 'enqueue'].includes(String(command.body.action))) {
      setMessage('Решение доступно только в доверенной форме контроллера.')
      return
    }
    locked.current = true
    setBusy(true)
    setMessage('')
    try {
      if (!command.operation) {
        try {
          const accepted = await transport.post<Operation>(`tasks/${command.taskId}/actions`, command.body, command.key, session.csrf_token, command.revision)
          command.operation = accepted.operation_id
          save(command)
        } catch (e) {
          if (e instanceof ApiError && e.status && e.status >= 400 && e.status < 500 && e.status !== 408) {
            save(undefined)
            if (active.current) onRefresh()
          }
          throw e
        }
      }
      if (!command.operation) throw Error('Контроллер не вернул идентификатор операции')
      for (let i = 0; i < 30; i++) {
        if (!active.current) return
        const result = await transport.get<Operation>(`operations/${encodeURIComponent(command.operation)}`)
        if (!active.current) return
        if (result.status === 'failed') {
          save(undefined)
          if (active.current) onRefresh()
          throw Error(result.error?.message || 'Команда отклонена')
        }
        if (result.status === 'succeeded') {
          save(undefined)
          setMessage('Команда выполнена контроллером')
          setDeleteOpen(false)
          if (command.action === 'answer' && answer === command.body.text) {
            setAnswer('')
            setDialogOpen(false)
          }
          if (active.current) onRefresh()
          return
        }
        if (result.status !== 'pending') throw Error('Неизвестный статус операции')
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
      setMessage('Операция ещё выполняется. Повторите проверку.')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Ошибка команды')
    } finally {
      locked.current = false
      setBusy(false)
    }
  }

  const allowed = control.allowed_actions

  return (
    <div className="actions flex flex-col gap-2 w-full">
      <div className="flex flex-col gap-2 w-full">
        {['enqueue', 'start', 'pause', 'resume'].filter(a => allowed.includes(a)).map(a => (
          <Button
            key={a}
            className="w-full flex items-center justify-center gap-1.5 cursor-pointer"
            disabled={commandsDisabled || busy || Boolean(pending.current) || !session?.csrf_token}
            onClick={() => void run(a)}
          >
            <AppIcon name="worker" />
            {label(a)}
          </Button>
        ))}

        {allowed.includes('delete') && (
          <details><summary className="text-xs cursor-pointer">Другие действия</summary>
            <Button variant="outline" disabled={commandsDisabled || busy || Boolean(pending.current) || !session?.csrf_token} onClick={() => setDeleteOpen(true)}>Удалить задачу</Button>
            <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
              <AlertDialogContent>
                <AlertDialogTitle>Удалить задачу TASK-{String(control.task.id).padStart(3, '0')}?</AlertDialogTitle>
                <AlertDialogDescription>Задача будет перемещена во вкладку «Удалённые». История и файлы сохранятся.</AlertDialogDescription>
                {message && <p role="alert">{message}</p>}
                <AlertDialogCancel disabled={busy}>Отмена</AlertDialogCancel>
                <Button disabled={commandsDisabled || busy || Boolean(pending.current)} onClick={() => void run('delete')}>Переместить в удалённые</Button>
              </AlertDialogContent>
            </AlertDialog>
          </details>
        )}
        {control.task.state === 'running' && <Button variant="outline" disabled title="Работающую задачу удалить нельзя">Удалить задачу</Button>}
        {allowed.includes('restore') && <Button disabled={commandsDisabled || busy || Boolean(pending.current) || !session?.csrf_token} onClick={() => void run('restore')}>Восстановить задачу</Button>}

        {allowed.includes('switch_backend') && (
          <Button
            variant="outline"
            className="w-full flex items-center justify-center gap-1.5 cursor-pointer border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-950/40"
            disabled={commandsDisabled || busy || Boolean(pending.current) || !session?.csrf_token}
            onClick={() => void run('switch_backend', control.task.backend === 'gemini' ? 'codex' : 'gemini')}
          >
            <AppIcon name="worker" />
            {control.task.backend === 'gemini' ? 'Переключить на Codex (OpenAI)' : 'Переключить на Gemini (Google)'}
          </Button>
        )}

        {allowed.includes('answer') && (
          modalAnswer ? (
            <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
              <Dialog.Trigger asChild>
                <Button
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs flex items-center justify-center gap-1.5 cursor-pointer"
                  disabled={commandsDisabled || busy || Boolean(pending.current) || !session?.csrf_token}
                >
                  <AppIcon name="worker" />
                  <span>Ответить на вопрос</span>
                </Button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="dialog-overlay" />
                <Dialog.Content className="details-dialog max-w-lg bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-zinc-900 dark:text-zinc-100 rounded-xl shadow-xl" aria-describedby={undefined}>
                  <header className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 p-4">
                    <Dialog.Title className="text-sm font-semibold flex items-center gap-2">
                      <AppIcon name="worker" />
                      <span>Ответ на вопрос агента</span>
                    </Dialog.Title>
                    <Dialog.Close aria-label="Закрыть" className="p-1 rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 cursor-pointer">
                      <AppIcon name="close" />
                    </Dialog.Close>
                  </header>
                  <div className="dialog-body space-y-4 p-5">
                    {control.task.question && (
                      <div className="p-3 bg-zinc-50 dark:bg-zinc-800/60 rounded-lg border border-zinc-200 dark:border-zinc-700 text-xs">
                        <strong className="block text-zinc-900 dark:text-zinc-100 mb-1 font-semibold">Вопрос агента:</strong>
                        <p className="text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">{control.task.question}</p>
                      </div>
                    )}
                    <div className="space-y-1.5">
                      <label htmlFor="answer" className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                        Ответ на вопрос
                      </label>
                      <Textarea
                        id="answer"
                        rows={4}
                        value={answer}
                        onChange={e => setAnswer(e.target.value)}
                        disabled={busy}
                        placeholder="Введите ответ или уточнение для агента..."
                        className="w-full text-xs p-3 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    {!withinLimit(answer, 16384) && (
                      <p role="alert" className="text-xs text-rose-500">
                        Ответ превышает 16 КиБ.
                      </p>
                    )}
                    <div className="flex items-center justify-between pt-2">
                      <p role="status" className="text-xs text-zinc-500">
                        {busy ? 'Ожидаем подтверждения контроллера…' : message}
                      </p>
                      <div className="flex items-center gap-2">
                        <Dialog.Close asChild>
                          <Button type="button" variant="outline" size="sm" disabled={busy} className="cursor-pointer">
                            Отмена
                          </Button>
                        </Dialog.Close>
                        <Button
                          size="sm"
                          className="bg-blue-600 hover:bg-blue-700 text-white cursor-pointer"
                          disabled={commandsDisabled || busy || Boolean(pending.current) || !session?.csrf_token || !control.pending_question_id || !answer.trim() || !withinLimit(answer, 16384)}
                          onClick={() => void run('answer')}
                        >
                          Отправить ответ
                        </Button>
                      </div>
                    </div>
                  </div>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          ) : (
            <div className="space-y-2">
              <label htmlFor="answer">Ответ на вопрос</label>
              <Textarea id="answer" value={answer} onChange={e => setAnswer(e.target.value)} disabled={busy} />
              <Button
                disabled={commandsDisabled || busy || Boolean(pending.current) || !session?.csrf_token || !control.pending_question_id || !answer.trim() || !withinLimit(answer, 16384)}
                onClick={() => void run('answer')}
              >
                Отправить ответ
              </Button>
              {!withinLimit(answer, 16384) && <p role="alert">Ответ превышает 16 КиБ.</p>}
            </div>
          )
        )}

        <div className="flex flex-col gap-2">
        {['approve_plan', 'revise_plan', 'accept_result', 'request_changes', 'reject_result'].filter(a => allowed.includes(a)).map(a => {
          const widget = (
            <TrustedDecisionWidget
              control={control}
              disabled={commandsDisabled}
              session={busy || pending.current ? undefined : session}
              project={transport.projectId}
              action={a}
              onRefresh={onRefresh}
            />
          )
          return !['revise_plan','request_changes','reject_result'].includes(a) ? (
            <div key={a} className="w-full">{widget}</div>
          ) : (
            <DecisionDialog key={a} title={label(a)} disabled={commandsDisabled || busy || Boolean(pending.current) || !session?.csrf_token}>
              {widget}
            </DecisionDialog>
          )
        })}
        </div>
      </div>

      {control.task.state === 'needs_permission' && (
        <p className="muted text-xs text-zinc-500">
          Ответ не предоставляет доступ к защищённому ресурсу. Требуется отдельный механизм разрешений контроллера.
        </p>
      )}

      {!allowed.length && (
        <p className="muted text-xs text-zinc-500">
          Сейчас нет доступных действий.
        </p>
      )}

      {pending.current && (
        <div className="space-y-2 p-2 bg-amber-50 dark:bg-amber-950/40 rounded border border-amber-200 dark:border-amber-800 text-xs">
          <p>Ожидается результат команды «{label(pending.current.action)}». Повтор сохраняет исходные данные и версию.</p>
          <Button size="sm" className="w-full text-xs" disabled={commandsDisabled || busy || !session?.csrf_token} onClick={() => void run()}>
            Повторить команду / проверить результат
          </Button>
        </div>
      )}

      {(!modalAnswer || !dialogOpen) && (
        <p role="status" className="text-xs text-zinc-500">
          {busy ? 'Ожидаем подтверждения контроллера…' : message}
        </p>
      )}
    </div>
  )
}
