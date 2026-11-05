import type { Task,Transport } from '@/lib/contracts'
import { ArtifactView } from './artifact-view'
import { EventList } from './event-list'
import { Tabs,TabsList,TabsTrigger,TabsContent } from './ui/tabs'
export function TaskTabs({task,transport,events}:{task:Task;transport:Transport;events:boolean}){
 const has=(name:string)=>Array.isArray(task.artifacts)?task.artifacts.includes(name):Boolean(task.artifacts&&name in task.artifacts)
 const artifact=(name:string)=>has(name)?<ArtifactView key={task.id+name} task={task.id} name={name} transport={transport}/>:<p>Документ ещё не предоставлен.</p>
 return <Tabs key={task.id} defaultValue={task.state==='review'&&task.stage==='done'?(has('checks')?'checks':has('review')?'review':'events'):'events'} className="task-materials"><TabsList variant="line" aria-label="Материалы задачи"><TabsTrigger value="events">История</TabsTrigger><TabsTrigger value="request">Исходная задача</TabsTrigger><TabsTrigger value="plan">План</TabsTrigger>{[['diff','Изменения'],['checks','Проверки'],['review','Ревью']].map(([name,title])=><TabsTrigger key={name} value={name}>{title}</TabsTrigger>)}</TabsList><TabsContent value="events">{events?<details><summary>Полная история событий</summary><EventList task={task.id} transport={transport}/></details>:<p>События недоступны.</p>}</TabsContent><TabsContent value="request"><pre className="artifact">{task.request}</pre></TabsContent><TabsContent value="plan"><h3>Спецификация</h3>{artifact('specification')}<h3>План</h3>{artifact('plan')}</TabsContent>{['diff','checks','review'].map(name=><TabsContent key={name} value={name}>{artifact(name)}</TabsContent>)}</Tabs>
}
