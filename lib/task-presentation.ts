export const labels:Record<string,string>={awaiting_approval:'Ожидает утверждения',accepted:'Принята',rejected:'Отклонена',waiting:'Ожидает ответа',blocked:'Заблокирована',rate_limited:'Ожидает снятия лимита',start:'Запустить',pause:'Пауза',resume:'Продолжить',answer:'Ответить',approve_plan:'Утвердить план',revise_plan:'Вернуть план с замечаниями',accept_result:'Принять результат',request_changes:'Вернуть с замечаниями',reject_result:'Окончательно отклонить',needs_input:'Нужен ответ',needs_permission:'Нужно разрешение',running:'В работе',done:'Приёмка не подтверждена',failed:'Ошибка',paused:'Приостановлена',queued:'В очереди',plan:'Спецификация и план',implement:'Реализация',check:'Проверки',planning:'Спецификация и план',implementation:'Реализация',review:'Ревью',checks:'Проверки'}
export const label=(value:string)=>labels[value]||value
export const date=(value:number)=>Number.isFinite(value)?new Date(value*1000).toLocaleString('ru-RU'):'Не сообщено'

export const progressSteps=['Спецификация и план','Реализация','Проверки','Ревью','Приёмка']
export function taskProgress(task:{stage:string;state:string}){
 const stages:Record<string,number>={plan:0,planning:0,implement:1,implementation:1,check:2,checks:2,review:3,done:4}
 const index=stages[task.stage]
 const known=['queued','running','review','accepted','rejected','awaiting_approval','waiting','blocked','rate_limited','needs_input','needs_permission','failed','paused','done'].includes(task.state)
 if(index===undefined||!known||(task.state==='accepted'&&task.stage!=='done'))return {index:undefined,text:`Неизвестное сочетание: ${task.stage} / ${task.state}`}
 if(task.state==='accepted')return {index:4,text:'Принято человеком'}
 if(task.state==='rejected')return {index,text:'Отклонена; приёмка не завершена'}
 if(task.stage==='done')return {index,text:task.state==='review'?'Ожидает приёмки':`Приёмка не подтверждена: ${label(task.state)}`}
 return {index,text:label(task.state)}
}
export const taskStateLabel=(task:{stage:string;state:string})=>task.stage==='done'&&task.state==='review'?'Ожидает приёмки':label(task.state)

