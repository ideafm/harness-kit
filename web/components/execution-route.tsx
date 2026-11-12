import type {Task} from '@/lib/contracts'
import {executionProfiles} from '@/lib/execution-profiles'
export function ExecutionRoute({task}:{task:Task}){
 const policy=task.execution_policy
 if(!policy)return null
 const labels:Record<string,string>={plan:'План',implement:'Реализация',review:'Ревью'}
 function model(backend:string,value:string){return backend==='gemini'?`Gemini · ${value||'модель агента'}`:value==='gpt-6-astra'?'Astra':value==='gpt-6.1-sol'?'Sol':value||'модель агента'}
 return <section aria-label="Маршрут исполнения" className="mb-3 space-y-2 rounded-xl border border-zinc-200 bg-white p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900"><div className="font-semibold">{executionProfiles[policy.profile]??policy.profile}</div><div className="flex flex-wrap gap-2">{Object.entries(labels).map(([stage,label])=>{const route=policy.stages[stage];return route?<span key={stage} className={`rounded-md px-2 py-1 ${task.stage===stage?'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300':'bg-zinc-50 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400'}`}>{label}: {model(route.backend,route.model)}</span>:null})}</div>{policy.history.length>0&&<details><summary>Почему модель повышена ({policy.history.length})</summary><ul className="mt-2 space-y-1">{policy.history.map((item,index)=><li key={index}>{labels[item.stage]??item.stage}: {model(item.backend,item.model)} — {item.reason}</li>)}</ul></details>}</section>
}
