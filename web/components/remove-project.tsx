'use client'
import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { Button } from './ui/button'
import { AlertDialog,AlertDialogContent,AlertDialogHeader,AlertDialogTitle,AlertDialogDescription,AlertDialogFooter,AlertDialogCancel } from './ui/alert-dialog'
export function RemoveProject({projects,onRemove}:{projects:{id:string;name:string}[];onRemove:(id:string)=>Promise<void>}){
 const [selected,setSelected]=useState<{id:string;name:string}>()
 const [busy,setBusy]=useState(false)
 const [error,setError]=useState('')
 async function remove(){if(!selected||busy)return;setBusy(true);setError('');try{await onRemove(selected.id);setSelected(undefined)}catch(e){setError(e instanceof Error?e.message:'Не удалось удалить проект')}finally{setBusy(false)}}
 return <><details className="px-2 py-2 text-xs text-zinc-500"><summary className="cursor-pointer">Управление проектами</summary><div className="mt-2 space-y-1">{projects.map(project=><button key={project.id} className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-rose-50 hover:text-rose-700" aria-label={`Удалить проект ${project.name}`} onClick={()=>{setError('');setSelected(project)}}><Trash2 className="size-3.5 shrink-0"/><span className="truncate">Удалить {project.name}</span></button>)}</div></details><AlertDialog open={Boolean(selected)} onOpenChange={open=>{if(!open&&!busy)setSelected(undefined)}}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Удалить проект «{selected?.name}» из списка?</AlertDialogTitle><AlertDialogDescription>Просмотр проекта будет остановлен. Файлы на диске и история задач сохранятся. Вернуть проект можно командой tw init в его каталоге.</AlertDialogDescription></AlertDialogHeader>{error&&<p role="alert" className="text-sm text-rose-600">{error}</p>}<AlertDialogFooter><AlertDialogCancel disabled={busy}>Отмена</AlertDialogCancel><Button variant="destructive" disabled={busy} onClick={()=>void remove()}>{busy?'Удаляем…':'Удалить из списка'}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog></>
}
