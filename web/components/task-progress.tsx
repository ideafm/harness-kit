import type { Task } from '@/lib/contracts'
import { progressSteps,progressIcons,taskProgress } from '@/lib/task-presentation'
import { AppIcon } from './app-icon'
export function TaskProgress({task,compact=false}:{task:Task;compact?:boolean}){
 const progress=taskProgress(task)
 return <div className={compact?'task-progress compact':'task-progress'}><ol aria-label={`Этапы задачи #${task.id}`}>{progressSteps.map((step,index)=><li key={step} aria-current={progress.index===index?'step':undefined}><span tabIndex={0} className="stage-dot" aria-label={step+(progress.index===index?' — текущий этап':'')} data-tip={step+(progress.index===index?' — текущий этап':' — завершение не подтверждено')}><AppIcon name={progressIcons[index]}/></span>{!compact&&<span className="stage-label" aria-hidden="true">{['План','Разработка','Проверки','Ревью','Приёмка'][index]}</span>}</li>)}</ol><p className="current-stage">{progress.index===undefined?progress.text:`Текущий этап: ${progressSteps[progress.index]}`}</p>{!compact&&progress.index!==undefined&&<p className="muted">{progress.text}</p>}</div>
}
