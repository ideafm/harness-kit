'use client'
import { useEffect, useRef, useState } from 'react'
import type { Session, Task, Transport } from '@/lib/contracts'
import { ApiError } from '@/lib/http-transport'
import { pendingSlot, readPending, writePending } from '@/lib/transport'
import { Button } from './ui/button'
import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription, AlertDialogCancel } from './ui/alert-dialog'

type PendingBatch = {path:string;body:Record<string,unknown>;key:string;revision:string;operation?:string}
type Result = {operation_id:string;status:string;error?:{message:string}}

export function BatchActions({tasks,transport,session,disabled,onDone}:{tasks:Task[];transport:Transport;session?:Session;disabled:boolean;onDone:()=>void}) {
 const slot=pendingSlot(transport,'batch')
 const pending=useRef<PendingBatch|undefined>(readPending<PendingBatch>(slot))
 const active=useRef(true)
 useEffect(()=>{active.current=true;return()=>{active.current=false}},[])
 const locked=useRef(false)
 const [busy,setBusy]=useState(false)
 const [message,setMessage]=useState('')
 const [deleting,setDeleting]=useState<number[]>()
 const [,render]=useState(0)
 const unavailable=disabled||busy||!session?.csrf_token
 function save(command:PendingBatch|undefined){writePending(slot,command);pending.current=command;if(active.current)render(n=>n+1)}
 async function run(action?:'delete'|'queue'){
  if(unavailable||locked.current||!session?.csrf_token)return
  if(action&&pending.current)return
  locked.current=true;setBusy(true);setMessage('')
  try{
   if(!pending.current){
    const ids=action==='delete'?deleting:tasks.map(t=>t.id)
    if(!ids?.length||ids.length>100)throw Error('Выберите от 1 до 100 задач')
    const queue=await transport.get<{revision:string}>('queue')
    if(!active.current)return
    save({path:action==='delete'?'tasks/batch':'queue',body:action==='delete'?{action:'delete',tasks:ids}:{tasks:ids,start:true},key:crypto.randomUUID(),revision:queue.revision})
   }
   const command=pending.current!
   let result:Result
   if(command.operation){
    result=await transport.get<Result>(`operations/${encodeURIComponent(command.operation)}`)
    if(result.status==='pending'&&command.path==='queue'&&active.current)result=await transport.post<Result>(command.path,command.body,command.key,session.csrf_token,command.revision)
   }else{
    try{
     result=await transport.post<Result>(command.path,command.body,command.key,session.csrf_token,command.revision)
    }catch(error){
     if(error instanceof ApiError&&error.status&&error.status>=400&&error.status<500&&error.status!==408)save(undefined)
     throw error
    }
    command.operation=result.operation_id;save(command)
   }
   if(result.status==='pending'){
    if(active.current)setMessage('Операция выполняется. Проверьте результат.');return
   }
   if(result.status!=='succeeded'&&result.status!=='failed')throw Error('Неизвестный статус операции')
   save(undefined)
   if(!active.current)return
   setDeleting(undefined)
   onDone()
   if(result.status==='failed')throw Error(result.error?.message||'Групповая операция не выполнена')
   setMessage('Групповая операция выполнена')
  }catch(error){if(active.current)setMessage(error instanceof Error?error.message:'Ошибка групповой операции')}
  finally{locked.current=false;if(active.current)setBusy(false)}
 }
 const canDelete=tasks.length>0&&tasks.length<=100&&tasks.every(t=>!['running','trashed'].includes(t.state))
 const canQueue=tasks.length>0&&tasks.length<=100&&tasks.every(t=>['backlog','queued'].includes(t.state))
 return <div className="space-y-2 text-xs">
  <div className="flex flex-wrap items-center gap-2">
   <span>Выбрано: {tasks.length}</span>
   <Button size="sm" variant="outline" disabled={unavailable||!!pending.current||!canDelete} onClick={()=>setDeleting(tasks.map(t=>t.id))}>Удалить выбранные</Button>
   <Button size="sm" variant="outline" title="В очередь доступны только задачи из бэклога и очереди" disabled={unavailable||!!pending.current||!canQueue} onClick={()=>void run('queue')}>В очередь</Button>
   {pending.current&&<Button size="sm" disabled={unavailable} onClick={()=>void run()}>Повторить / проверить групповую операцию</Button>}
  </div>
  {tasks.length>100&&<p role="alert">За один раз доступно не больше 100 задач.</p>}
  {message&&<p role="status">{message}</p>}
  <AlertDialog open={!!deleting} onOpenChange={open=>{if(!open&&!busy)setDeleting(undefined)}}>
   <AlertDialogContent>
    <AlertDialogTitle>Удалить выбранные задачи ({deleting?.length})?</AlertDialogTitle>
    <AlertDialogDescription>Задачи {deleting?.map(id=>`#${id}`).join(', ')} будут перемещены в корзину вместе. История и файлы сохранятся.</AlertDialogDescription>
    {message&&<p role="alert">{message}</p>}
    <AlertDialogCancel disabled={busy}>Отмена</AlertDialogCancel>
    <Button disabled={unavailable||!!pending.current} onClick={()=>void run('delete')}>Переместить выбранные в корзину</Button>
   </AlertDialogContent>
  </AlertDialog>
 </div>
}
