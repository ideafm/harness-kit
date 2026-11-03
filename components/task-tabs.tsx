import type { Task,Transport } from '@/lib/contracts'
import { ArtifactView } from './artifact-view'
import { EventList } from './event-list'
import { TaskDetailsDialog } from './task-details-dialog'
export function TaskTabs({task,transport,events}:{task:Task;transport:Transport;events:boolean}){
 const has=(name:string)=>Array.isArray(task.artifacts)?task.artifacts.includes(name):Boolean(task.artifacts&&name in task.artifacts)
 const artifact=(name:string)=>has(name)?<ArtifactView task={task.id} name={name} transport={transport}/>:<p>Документ ещё не предоставлен.</p>
 return <div className="detail-tools"><TaskDetailsDialog iconOnly title="Исходная задача"><pre className="artifact">{task.request}</pre></TaskDetailsDialog><TaskDetailsDialog iconOnly title="План" icon="plan">{artifact('specification')}{artifact('plan')}</TaskDetailsDialog>{[['diff','Изменения'],['checks','Проверки'],['review','Ревью']].map(([name,title])=><TaskDetailsDialog iconOnly key={name} title={title} icon={name==='checks'?'check':name}>{artifact(name)}</TaskDetailsDialog>)}<TaskDetailsDialog iconOnly title="История" icon="history">{events?<EventList task={task.id} transport={transport}/>:<p>События недоступны.</p>}</TaskDetailsDialog></div>
}
