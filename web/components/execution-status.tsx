'use client'
import { useEffect,useState } from 'react'
import { Activity,Clock3,PauseCircle } from 'lucide-react'
import type { Task } from '@/lib/contracts'
import { ExecutionRoute } from './execution-route'
import { formatDuration } from '@/lib/task-presentation'
export function ExecutionStatus({task}:{task:Task}){
 const [now,setNow]=useState(()=>Date.now()/1000)
 useEffect(()=>{setNow(Date.now()/1000);if(task.state!=='running')return;const timer=setInterval(()=>setNow(Date.now()/1000),1000);return()=>clearInterval(timer)},[task.id,task.state])
 const value=task.execution
 if(!value)return null
 const elapsed=value.started_at===null?null:Math.max(0,now-value.started_at)
 return <><ExecutionRoute task={task}/><section aria-label="Состояние исполнения" className="rounded-xl border border-blue-100 bg-blue-50/40 p-4 dark:border-blue-900/40 dark:bg-blue-950/10"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-2 text-sm font-semibold">{value.waiting?<PauseCircle className="size-4 text-amber-500"/>:<Activity className="size-4 text-blue-500"/>}{value.title}</h3><div className="flex items-center gap-3 text-xs text-zinc-500">{value.attempt>0&&task.state==='running'&&<span>Попытка {value.attempt}</span>}{elapsed!==null&&task.state==='running'&&<span className="flex items-center gap-1"><Clock3 className="size-3.5"/>{formatDuration(elapsed)}</span>}</div></div>{value.detail&&<p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{value.detail}</p>}{value.retry_at&&<p className="mt-2 text-xs">Следующая попытка: {new Date(value.retry_at*1000).toLocaleString('ru-RU')}</p>}<div className="mt-3 flex flex-wrap justify-between gap-2 border-t border-blue-100 pt-2 text-[11px] text-zinc-500 dark:border-blue-900/40">{value.next&&<span>Дальше: {value.next}</span>}<span>Последняя активность: {new Date(value.last_activity_at*1000).toLocaleTimeString('ru-RU')}</span></div></section></>
}
