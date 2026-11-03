'use client'
import { useCallback,useEffect,useMemo,useRef,useState } from 'react'
import type { Status,Transport,Control,Capabilities,Session,Projects } from '@/lib/contracts'
import { projectTransport } from '@/lib/transport'

function locationSelection(){
 const params=new URLSearchParams(typeof window==='undefined'?'':window.location.search)
 const raw=params.get('task');const id=raw!==null&&/^\d+$/.test(raw)?Number(raw):undefined
 return {project:params.get('project'),task:id!==undefined&&id>0&&Number.isSafeInteger(id)?id:undefined,invalidTask:raw!==null&&(!id||!Number.isSafeInteger(id))}
}
export function useTaskData(base:Transport) {
 const [loadedProject,setLoadedProject]=useState<string>();const [projects,setProjects]=useState<Projects>();const [choice,setChoice]=useState(locationSelection)
 const [status,setStatus]=useState<Status>();const [selected,setSelected]=useState<number>();const [control,setControl]=useState<Control>();const [capabilities,setCapabilities]=useState<Capabilities>();const [session,setSession]=useState<Session>();const [error,setError]=useState('');const [projectError,setProjectError]=useState('');const [loading,setLoading]=useState(true)
 const current=useRef(0);const listing=useRef(0)
 const projectId=choice.project??projects?.default_project_id
 const valid=projects?.items.some(p=>p.id===projectId)??false
 const transport=useMemo(()=>projectTransport(base,projectId??''),[base,projectId])
 const refreshProjects=useCallback(async()=>{const version=++listing.current;try{const value=await base.get<Projects>('projects');if(!Array.isArray(value.items)||value.items.some(p=>typeof p.id!=='string'||typeof p.name!=='string')||typeof value.default_project_id!=='string'||typeof value.connect_url!=='string')throw Error('Некорректный список проектов');if(version===listing.current){setProjects(value);setProjectError('')}}catch(e){if(version===listing.current)setProjectError(e instanceof Error?e.message:'Ошибка проектов')}},[base])
 useEffect(()=>{void refreshProjects();const focus=()=>void refreshProjects();const visible=()=>{if(document.visibilityState==='visible')focus()};window.addEventListener('focus',focus);document.addEventListener('visibilitychange',visible);return()=>{listing.current++;window.removeEventListener('focus',focus);document.removeEventListener('visibilitychange',visible)}},[refreshProjects])
 useEffect(()=>{if(choice.project!==null||!projects)return;const project=projects.default_project_id;const url=new URL(window.location.href);url.searchParams.set('project',project);window.history.replaceState(null,'',url);setChoice(old=>({...old,project}))},[projects,choice.project])
 const navigate=useCallback((project:string,task?:number)=>{current.current++;setStatus(undefined);setControl(undefined);setCapabilities(undefined);setSession(undefined);setSelected(undefined);setLoading(true);const url=new URL(window.location.href);url.searchParams.set('project',project);url.searchParams.delete('task');if(task)url.searchParams.set('task',String(task));window.history.pushState(null,'',url);setChoice({project,task,invalidTask:false})},[])
 useEffect(()=>{const pop=()=>{current.current++;setStatus(undefined);setControl(undefined);setCapabilities(undefined);setSession(undefined);setSelected(undefined);setChoice(locationSelection())};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop)},[])
 const refresh=useCallback(async(signal?:AbortSignal)=>{
  const version=++current.current
  if(!valid){setLoading(false);return}
  try{
   const [next,caps,sess]=await Promise.all([transport.get<Status>('status',signal),transport.get<Capabilities>('capabilities',signal),transport.get<Session>('session',signal)])
   if(version!==current.current||signal?.aborted)return
   if(!Array.isArray(next.tasks)||!next.worker||typeof next.worker.running!=='boolean'||next.tasks.some(t=>!Number.isSafeInteger(t.id)||t.id<=0||typeof t.request!=='string')||(caps.project_id!==undefined&&caps.project_id!==projectId)||!Array.isArray(caps.actions)||typeof caps.events!=='boolean'||(sess.csrf_token!==undefined&&typeof sess.csrf_token!=='string'))throw Error('Некорректные данные контроллера')
   const wanted=choice.task;const found=wanted?next.tasks.find(t=>t.id===wanted):undefined
   const ctrl=found?await transport.get<Control>(`tasks/${found.id}/control`,signal):undefined
   if(ctrl&&(!Array.isArray(ctrl.allowed_actions)||typeof ctrl.revision!=='string'||ctrl.task.id!==wanted))throw Error('Некорректные данные управления')
   if(version!==current.current||signal?.aborted)return
   setLoadedProject(projectId);setStatus(next);setSelected(found?.id);setControl(ctrl);setCapabilities(caps);setSession(sess.csrf_token?sess:undefined);setError(choice.invalidTask||wanted&&!found?'Неизвестная задача в выбранном проекте':'')
  }catch(e){if(version===current.current&&!signal?.aborted){setError(e instanceof Error?e.message:'Ошибка соединения');setControl(undefined);setCapabilities(undefined);setSession(undefined)}}finally{if(version===current.current)setLoading(false)}
 },[transport,projectId,valid,choice])
 useEffect(()=>{const abort=new AbortController();let timer:ReturnType<typeof setTimeout>;let stopped=false;async function poll(){await refresh(abort.signal);if(!stopped)timer=setTimeout(poll,5000)}void poll();return()=>{stopped=true;abort.abort();current.current++;clearTimeout(timer)}},[refresh])
 const visible=valid&&loadedProject===projectId
 return {projects,projectId,transport,status:visible?status:undefined,selected:visible?selected:undefined,select:(id:number)=>{if(projectId)navigate(projectId,id)},selectProject:(id:string)=>navigate(id),control:visible?control:undefined,capabilities:visible?capabilities:undefined,session:visible?session:undefined,error:projectError||(!valid&&projects?(projects.items.length?'Неизвестный проект':'Проекты пока не подключены'):error),loading,refresh:async()=>{void refreshProjects();await refresh()}}
}
