import type { Task } from '@/lib/contracts'
import { progressSteps,taskProgress } from '@/lib/task-presentation'

export function TaskProgress({task,compact=false}:{task:Task;compact?:boolean}){
 const progress=taskProgress(task)
 return <div className={compact?'task-progress compact':'task-progress'}><ol aria-label={`Этапы задачи #${task.id}`}>{progressSteps.map((step,index)=><li key={step} aria-current={progress.index===index?'step':undefined}><span aria-hidden="true">{index+1}. </span>{step}</li>)}</ol><p className="muted">{progress.text}</p></div>
}
