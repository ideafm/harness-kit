'use client'
import { useEffect,useRef,useState } from 'react'
import type { ProjectViewResponse,ViewMode,ViewOperation,Transport } from '@/lib/contracts'
import { pendingSlot,readPending,writePending } from '@/lib/transport'
import { ApiError } from '@/lib/http-transport'

type Command={project:string;task?:number|null;body:{action:'select'|'refresh'|'stop';mode:ViewMode};revision:string;key:string;operation?:string}
type State={data?:ProjectViewResponse;stale:boolean;error:string;pending?:Command;busy:boolean;waiting?:ViewMode}
type Runtime={scope:string;alive:boolean;sequence:number;locked:boolean;pending?:Command;pollOperation:boolean;load:()=>Promise<void>}
function validate(data:ProjectViewResponse,task?:number){
 if(data.actions!==undefined&&(!Array.isArray(data.actions)||data.actions.some(action=>!['select','refresh','stop'].includes(action))))return false
 if(task!==undefined){
  if(data.task_id!==task)return false
 }else{
  if(data.task_id!==null&&!Number.isSafeInteger(data.task_id))return false
 }
 if(typeof data.available!=='boolean'||!(data.revision===null||typeof data.revision==='string')||!(data.reason===null||typeof data.reason==='string'))return false
 const v=data.view
 if(v===null)return true
 if(!v||!(v.revision===null||typeof v.revision==='string')||typeof v.running!=='boolean'||typeof v.current!=='boolean'||typeof v.building!=='boolean'||typeof v.message!=='string'||!(v.url===null||typeof v.url==='string')||!(v.source_digest===null||typeof v.source_digest==='string')||!(v.active_task===null||Number.isSafeInteger(v.active_task))||!(v.mode===null||['checked','working'].includes(v.mode)))return false
 if(v.error!==undefined&&typeof v.error!=='string'&&(!v.error||typeof v.error.message!=='string'))return false
 return v.requested===null||Boolean(v.requested&&Number.isSafeInteger(v.requested.task)&&['checked','working'].includes(v.requested.mode)&&(v.requested.revision===null||typeof v.requested.revision==='string'))
}
export function viewReady(data:ProjectViewResponse|undefined,task?:number,mode?:ViewMode){
 const v=data?.view
 const activeTask=task??v?.active_task??v?.requested?.task
 if(!activeTask)return false
 if(task!==undefined&&data?.task_id!==task)return false
 return Boolean(data?.available&&v&&v.running&&v.current&&!v.building&&!v.error&&v.active_task===activeTask&&(v.mode==='checked'||v.mode==='working')&&(!mode||v.mode===mode)&&v.source_digest&&(v.requested&&v.requested.revision&&v.revision===`${v.requested.revision}:${v.source_digest}`&&v.requested.task===activeTask&&v.requested.mode===v.mode))
}
export function useProjectView(transport:Transport,task?:number,enabled:boolean=true,csrf?:string){
 const scope=`${transport.projectId??''}:${task??'project'}:${enabled}`
 const [state,setState]=useState<State>({stale:true,error:'',busy:false})
 const runtime=useRef<Runtime|null>(null)
 function finish(op:ViewOperation,ctx:Runtime,slot:string){
  if((task!==undefined&&op.task_id!==task)||!['pending','failed','succeeded'].includes(op.status)||typeof op.operation_id!=='string'||!op.operation_id||(ctx.pending?.operation&&ctx.pending.operation!==op.operation_id)||(op.error&&typeof op.error.message!=='string'))throw Error('Некорректная операция просмотра')
  if(op.error||op.status==='failed'){
   writePending(slot,undefined);ctx.pending=undefined;ctx.pollOperation=false
   setState(s=>({...s,pending:undefined,busy:false,waiting:undefined,stale:true,error:op.error?.message||'Подготовка отклонена'}));void ctx.load();return
  }
  if(op.status==='pending'){
   const pending={...ctx.pending!,operation:op.operation_id};writePending(slot,pending);ctx.pending=pending;ctx.pollOperation=true
   setState(s=>({...s,pending,busy:true,error:''}));return
  }
  writePending(slot,undefined);ctx.pending=undefined;ctx.pollOperation=false
  setState(s=>({...s,pending:undefined,busy:false,stale:true,error:''}));void ctx.load()
 }
 useEffect(()=>{
  const slot=pendingSlot(transport,task!==undefined?`view:${task}`:'view:project')
  const ctx:Runtime={scope,alive:true,sequence:0,locked:false,pollOperation:false,load:async()=>{}}
  runtime.current=ctx
  setState({stale:true,error:'',busy:false})
  if(!enabled)return()=>{ctx.alive=false}
  let storageError=''
  try{
   const p=readPending<Command>(slot)
   if(p){if(p.project!==(transport.projectId??'')||(task!==undefined?p.task!==task:p.task!==undefined&&p.task!==null&&!Number.isSafeInteger(p.task))||!p.body||!['select','refresh','stop'].includes(p.body.action)||!['checked','working'].includes(p.body.mode)||Object.keys(p.body).sort().join(',')!=='action,mode'||typeof p.revision!=='string'||!p.revision||typeof p.key!=='string'||!p.key||(p.operation!==undefined&&(typeof p.operation!=='string'||!p.operation)))throw Error('Некорректная сохранённая команда просмотра');ctx.pending=p}
  }catch(e){storageError=e instanceof Error?e.message:'Хранилище недоступно';ctx.locked=true}
  setState({stale:true,error:storageError,pending:ctx.pending,busy:ctx.locked})
  const abort=new AbortController()
  let viewAbort:AbortController|undefined
  const endpoint=task!==undefined?`tasks/${task}/view`:'view'
  ctx.load=async()=>{
   const sequence=++ctx.sequence
   viewAbort?.abort()
   viewAbort=new AbortController()
   const signal=viewAbort.signal
   try{
    const data=await transport.get<ProjectViewResponse>(endpoint,signal)
    if(!ctx.alive||sequence!==ctx.sequence)return
    if(!validate(data,task))throw Error('Некорректный ответ просмотра')
    setState(s=>({...s,data,stale:false,waiting:!ctx.pending&&viewReady(data,task,s.waiting)?undefined:s.waiting,error:storageError||s.error}))
   }catch(e){if(ctx.alive&&sequence===ctx.sequence)setState(s=>({...s,stale:true,error:e instanceof Error?e.message:'Ошибка обновления просмотра'}))}
  }
  let timer:ReturnType<typeof setTimeout>
  async function poll(){
   if(!ctx.locked)await ctx.load()
   if(ctx.alive&&ctx.pollOperation&&ctx.pending?.operation&&!ctx.locked){
    ctx.locked=true
    try{const op=await transport.get<ViewOperation>(`operations/${encodeURIComponent(ctx.pending.operation)}`,abort.signal);if(ctx.alive)finish(op,ctx,slot)}catch(e){if(ctx.alive){ctx.pollOperation=false;setState(s=>({...s,busy:false,error:e instanceof Error?e.message:'Неизвестный исход операции'}))}}finally{ctx.locked=false}
   }
   if(ctx.alive)timer=setTimeout(poll,2000)
  }
  void poll()
  return()=>{ctx.alive=false;abort.abort();viewAbort?.abort();clearTimeout(timer)}
 },[transport,task,enabled,scope])
 async function send(action:'select'|'refresh'|'stop',mode:ViewMode,retry=false){
  const ctx=runtime.current
  if(!enabled||!csrf?.trim()||!ctx?.alive||ctx.scope!==scope||ctx.locked)return
  if(!retry&&(ctx.pending||state.stale||!state.data?.revision))return
  if(!retry&&action==='stop'&&!state.data?.actions?.includes('stop'))return
  if(retry&&!ctx.pending)return
  const slot=pendingSlot(transport,task!==undefined?`view:${task}`:'view:project')
  ctx.locked=true;ctx.sequence++
  let command=ctx.pending
  const endpoint=task!==undefined?`tasks/${task}/view`:'view'
  try{
   if(!command){command={project:transport.projectId??'',task:task??null,body:{action,mode},revision:state.data!.revision!,key:crypto.randomUUID()};writePending(slot,command);ctx.pending=command}
   setState(s=>({...s,busy:true,pending:command,error:'',waiting:command!.body.action==='stop'?undefined:command!.body.mode,stale:true}))
   const op=command.operation?await transport.get<ViewOperation>(`operations/${encodeURIComponent(command.operation)}`):await transport.post<ViewOperation>(endpoint,command.body,command.key,csrf,command.revision)
   if(ctx.alive)finish(op,ctx,slot)
  }catch(e){
   if(ctx.alive){
    const rejected=e instanceof ApiError&&Boolean(e.status&&e.status>=400&&e.status<500)
    if(rejected){try{writePending(slot,undefined);ctx.pending=undefined}catch{};void ctx.load()}
    setState(s=>({...s,busy:false,pending:ctx.pending,waiting:rejected?undefined:s.waiting,stale:true,error:e instanceof Error?e.message:'Неизвестный исход команды'}))
   }
  }finally{ctx.locked=false}
 }
 const visible=runtime.current?.scope===scope?state:{stale:true,error:'',busy:false} as State
 const ready=!visible.stale&&!visible.pending&&viewReady(visible.data,task,visible.waiting)
 return {...visible,ready,send,canSend:enabled&&Boolean(csrf?.trim())&&!visible.stale&&!visible.busy&&!visible.pending&&Boolean(visible.data?.revision),retry:()=>send('select',state.pending?.body.mode??'checked',true)}
}
