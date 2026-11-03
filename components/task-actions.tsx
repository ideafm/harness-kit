'use client'
import { useEffect,useRef,useState } from 'react'
import type { Control,Transport,Session,Operation } from '@/lib/contracts'
import { AppIcon } from './app-icon'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { TrustedDecisionWidget } from './trusted-decision-widget'
import { TaskDetailsDialog } from './task-details-dialog'
import { ApiError,withinLimit } from '@/lib/http-transport'
import { readPending,writePending,pendingSlot,type PendingCommand } from "@/lib/transport"
import { label } from '@/lib/task-presentation'
export function TaskActions({control,transport,session,onRefresh}:{control:Control;transport:Transport;session?:Session;onRefresh:()=>void}){
 const slot=pendingSlot(transport,`task:${control.task.id}`)
 const active=useRef(true);useEffect(()=>{active.current=true;return()=>{active.current=false}},[])
 const [restored]=useState(()=>readPending<PendingCommand>(slot))
 function save(value:PendingCommand|undefined){const stored=readPending<PendingCommand>(slot);if(!pending.current||stored?.key===pending.current.key)writePending(slot,value);pending.current=value}
 const [answer,setAnswer]=useState('');const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);const locked=useRef(false);const pending=useRef<PendingCommand|undefined>(restored)
 async function run(action?:string){
  if(locked.current||!session?.csrf_token)return
  if(action&&pending.current)return
  if(!pending.current){
   if(!action||!control.allowed_actions.includes(action))return
   const body=action==='answer'?{action,question_id:control.pending_question_id,text:answer}:{action}
   try{save({action,taskId:control.task.id,body,revision:control.revision,key:crypto.randomUUID()})}catch{setMessage("Не удалось сохранить команду. Отправка отменена.");return}
  }
  const command=pending.current
  if(!command)return
  if(!['start','pause','resume','answer'].includes(command.action)||!['start','pause','resume','answer'].includes(String(command.body.action))){setMessage('Решение доступно только в доверенной форме контроллера.');return}
  locked.current=true;setBusy(true);setMessage('')
  try{
   if(!command.operation){
    try{
     const accepted=await transport.post<Operation>(`tasks/${command.taskId}/actions`,command.body,command.key,session.csrf_token,command.revision)
     command.operation=accepted.operation_id
     save(command)
    }catch(e){
     if(e instanceof ApiError&&e.status&&e.status>=400&&e.status<500&&e.status!==408){save(undefined);if(active.current)onRefresh()}
     throw e
    }
   }
   if(!command.operation)throw Error('Контроллер не вернул идентификатор операции')
   for(let i=0;i<30;i++){
    if(!active.current)return
    const result=await transport.get<Operation>(`operations/${encodeURIComponent(command.operation)}`)
    if(!active.current)return
    if(result.status==='failed'){save(undefined);if(active.current)onRefresh();throw Error(result.error?.message||'Команда отклонена')}
    if(result.status==='succeeded'){
     save(undefined);setMessage('Команда выполнена контроллером')
     if(command.action==='answer'&&answer===command.body.text)setAnswer('')
     if(active.current)onRefresh();return
    }
    if(result.status!=='pending')throw Error('Неизвестный статус операции')
    await new Promise(resolve=>setTimeout(resolve,1000))
   }
   setMessage('Операция ещё выполняется. Повторите проверку.')
  }catch(e){setMessage(e instanceof Error?e.message:'Ошибка команды')}
  finally{locked.current=false;setBusy(false)}
 }
 const allowed=control.allowed_actions
 return <div className="actions"><div className="flex flex-wrap gap-2">{['start','pause','resume'].filter(a=>allowed.includes(a)).map(a=><Button key={a} disabled={busy||Boolean(pending.current)||!session?.csrf_token} onClick={()=>void run(a)}><AppIcon name="worker"/>{label(a)}</Button>)}{['approve_plan','revise_plan','accept_result','request_changes','reject_result'].filter(a=>allowed.includes(a)).map(a=>{const widget=<TrustedDecisionWidget control={control} session={busy||pending.current?undefined:session} project={transport.projectId} action={a} onRefresh={onRefresh}/>;return a==='approve_plan'||a==='accept_result'?<div key={a}>{widget}</div>:<TaskDetailsDialog key={a} title={label(a)}>{widget}</TaskDetailsDialog>})}</div>{allowed.includes('answer')&&<div className="space-y-2"><label htmlFor="answer">Ответ на вопрос</label><Textarea id="answer" value={answer} onChange={e=>setAnswer(e.target.value)} disabled={busy}/><Button disabled={busy||Boolean(pending.current)||!session?.csrf_token||!control.pending_question_id||!answer.trim()||!withinLimit(answer,16384)} onClick={()=>void run('answer')}>Отправить ответ</Button>{!withinLimit(answer,16384)&&<p role="alert">Ответ превышает 16 КиБ.</p>}</div>}{control.task.state==='needs_permission'&&<p className="muted">Ответ не предоставляет доступ к защищённому ресурсу. Требуется отдельный механизм разрешений контроллера.</p>}{!allowed.length&&<p className="muted">Сейчас нет доступных действий.</p>}{pending.current&&<div className="space-y-2"><p>Ожидается результат команды «{label(pending.current.action)}». Повтор сохраняет исходные данные и версию.</p><Button disabled={busy||!session?.csrf_token} onClick={()=>void run()}>Повторить команду / проверить результат</Button></div>}<p role="status">{busy?'Ожидаем подтверждения контроллера…':message}</p></div>
}
