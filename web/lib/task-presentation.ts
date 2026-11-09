export const labels:Record<string,string>={trashed:'Удалена',delete:'Удалить',restore:'Восстановить',backlog:'Бэклог',awaiting_approval:'Ожидает утверждения',accepted:'Принята',rejected:'Отклонена',waiting:'Ожидает ответа',blocked:'Заблокирована',rate_limited:'Ожидает снятия лимита',start:'Запустить',pause:'Пауза',resume:'Продолжить',answer:'Ответить',switch_backend:'Сменить исполнителя',approve_plan:'Утвердить план',revise_plan:'Вернуть план с замечаниями',accept_result:'Принять',request_changes:'Доработать',reject_result:'Отклонить',needs_input:'Нужен ответ',needs_permission:'Нужно разрешение',running:'В работе',done:'Приёмка не подтверждена',failed:'Ошибка',paused:'Приостановлена',queued:'В очереди',plan:'Спецификация и план',implement:'Реализация',check:'Проверки',planning:'Спецификация и план',implementation:'Реализация',review:'Ревью',checks:'Проверки'}
export const label=(value:string)=>labels[value]||value
export const date=(value:number)=>Number.isFinite(value)?new Date(value*1000).toLocaleString('ru-RU'):'Не сообщено'

export const progressSteps=['Спецификация и план','Реализация','Проверки','Ревью','Приёмка']
export function taskProgress(task:PresentedTask){
 const stages:Record<string,number>={plan:0,planning:0,implement:1,implementation:1,check:2,checks:2,review:3,done:4}
 const index=stages[task.stage]
 const known=['trashed','backlog','queued','running','review','accepted','rejected','awaiting_approval','waiting','blocked','rate_limited','needs_input','needs_permission','failed','paused','done'].includes(task.state)
 if(index===undefined||!known||(task.state==='accepted'&&task.stage!=='done'))return {index:undefined,text:`Неизвестное сочетание: ${task.stage} / ${task.state}`}
 if(task.state==='accepted')return {index:4,text:acceptanceLabel(task)}
 if(task.state==='rejected')return {index,text:'Отклонена; приёмка не завершена'}
 if(task.stage==='done')return {index,text:task.state==='review'?'Ожидает приёмки':`Приёмка не подтверждена: ${label(task.state)}`}
 return {index,text:label(task.state)}
}
export const taskStateLabel=(task:PresentedTask)=>taskProgress(task).index===undefined?taskProgress(task).text:task.state==='accepted'?acceptanceLabel(task):task.stage==='done'&&task.state==='review'?'Ожидает приёмки':label(task.state)

type PresentedTask={stage:string;state:string;integration?:{source_commit:string;commit:string;branch:string};integration_error?:string;commit_error?:string}
export function acceptanceLabel(task:PresentedTask){
 if(task.integration_error?.trim())return 'Принято, применение остановлено'
 if(task.commit_error?.trim())return 'Принято, коммит не создан'
 if(task.integration?.source_commit?.trim()&&task.integration.commit?.trim()&&task.integration.branch?.trim())return 'Принято и применено'
 return 'Принято, применение не подтверждено'
}


export const progressIcons=['plan','implement','check','review','acceptance']
export function taskStateIcon(task:PresentedTask){
 const index=taskProgress(task).index
 if(index===undefined||task.integration_error?.trim()||task.commit_error?.trim())return 'error'
 const icons:Record<string,string>={rate_limited:'limit',paused:'pause',failed:'error',blocked:'error',rejected:'error',waiting:'waiting',needs_input:'waiting',needs_permission:'limit',awaiting_approval:'waiting',queued:'waiting',backlog:'waiting',accepted:'check'}
 return icons[task.state]||progressIcons[index]
}
