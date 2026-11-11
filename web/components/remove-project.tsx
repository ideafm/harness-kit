'use client'
import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { Button } from './ui/button'
import { 
  AlertDialog, 
  AlertDialogContent, 
  AlertDialogHeader, 
  AlertDialogTitle, 
  AlertDialogDescription, 
  AlertDialogFooter, 
  AlertDialogCancel 
} from './ui/alert-dialog'

export interface RemoveProjectProps {
  projects?: { id: string; name: string }[]
  project?: { id: string; name: string }
  onRemove: (id: string) => Promise<void>
  onRemoved?: () => void
}

export function RemoveProject({
  projects,
  project,
  onRemove,
  onRemoved,
}: RemoveProjectProps) {
  const items = project ? [project] : projects || []
  const [selected, setSelected] = useState<{ id: string; name: string } | undefined>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function remove() {
    if (!selected || busy) return
    setBusy(true)
    setError('')
    try {
      await onRemove(selected.id)
      setSelected(undefined)
      onRemoved?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось удалить проект')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="space-y-2">
        {items.map((p) => (
          <div 
            key={p.id} 
            className="rounded-xl border border-rose-200 dark:border-rose-900/50 bg-rose-50/40 dark:bg-rose-950/20 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
          >
            <div>
              <h4 className="text-xs font-semibold text-rose-900 dark:text-rose-200">
                Отключить проект «{p.name}»
              </h4>
              <p className="text-[11px] text-zinc-600 dark:text-zinc-400 mt-0.5 leading-normal max-w-sm">
                Останавливает просмотр в tw-web. Проект можно будет снова подключить в любой момент.
              </p>
            </div>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              aria-label={`Удалить проект ${p.name}`}
              onClick={() => {
                setError('')
                setSelected(p)
              }}
              className="shrink-0 gap-1.5 cursor-pointer text-xs"
            >
              <Trash2 className="w-3.5 h-3.5 shrink-0" />
              <span>Удалить {p.name}</span>
            </Button>
          </div>
        ))}
      </div>

      <AlertDialog 
        open={Boolean(selected)} 
        onOpenChange={(open) => {
          if (!open && !busy) setSelected(undefined)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить проект «{selected?.name}» из списка?</AlertDialogTitle>
            <AlertDialogDescription>
              Просмотр проекта будет остановлен. Файлы на диске и история задач сохранятся. Вернуть проект можно командой tw init в его каталоге.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {error && <p role="alert" className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Отмена</AlertDialogCancel>
            <Button 
              type="button"
              variant="destructive" 
              disabled={busy} 
              onClick={() => void remove()}
            >
              {busy ? 'Удаляем…' : 'Удалить из списка'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
