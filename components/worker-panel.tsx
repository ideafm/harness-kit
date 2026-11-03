'use client'
import { useState } from 'react'
import { Dialog } from 'radix-ui'
import type { Status,Task } from '@/lib/contracts'
import { TaskDetailsDialog } from './task-details-dialog'
import { label } from '@/lib/task-presentation'
export function WorkerPanel({status,project,selectedTask,onSelect}:{status?:Status;project:string;selectedTask?:Task;onSelect:(id:number)=>void}){
 const [message,setMessage]=useState('')
 const active=status?.tasks.find(task=>task.id===status.worker.task_id)
 const selected=status?.tasks.find(task=>task.id===selectedTask?.id)
 const watched=active||selected
 const valid=(candidate:Task['observation'])=>candidate&&candidate.task_id===watched?.id&&candidate.mode==='events'&&candidate.interactive===false&&typeof candidate.terminal_command==='string'&&candidate.terminal_command.trim()?candidate:undefined
 const observation=active?(valid(status?.worker.observation)||valid(active.observation)):valid(selected?.observation)
 async function copy(){if(!observation)return;try{await navigator.clipboard.writeText(observation.terminal_command);setMessage('Команда скопирована')}catch{setMessage('Выделите и скопируйте команду вручную')}}
 return <TaskDetailsDialog title={status?.worker.running?'Worker работает':'Worker не запущен'} icon="worker"><p>Проект: {project}</p><p>{!status?.worker.running?'Worker остановлен':active?`Выполняется задача #${active.id}`:'Ожидает задачи'}</p>{active&&<><Dialog.Close asChild><button className="detail-button" onClick={()=>onSelect(active.id)}>Открыть задачу #{active.id}</button></Dialog.Close><p>Этап: {label(active.stage)}</p></>}{observation?<><p>Наблюдение за задачей #{watched?.id}</p><label htmlFor="watch-command">Наблюдение за этапом и событиями · без чата</label><textarea key={observation.terminal_command} id="watch-command" className="terminal-command" readOnly value={observation.terminal_command} onFocus={event=>event.target.select()}/><button className="detail-button" onClick={()=>void copy()}>Копировать команду</button><p role="status">{message}</p></>:<p>Команда наблюдения не предоставлена.</p>}<h3>Сведения о процессе</h3><p>Время старта, последнее действие, результаты проверок, причины ожидания и история событий процесса не предоставлены контроллером. История задачи доступна отдельно и не является историей процесса.</p><p>Просмотр не останавливает работу. Live-канал событий процесса и сохраняемые сообщения агенту пока недоступны; для них требуется отдельный backend-контракт.</p></TaskDetailsDialog>
}
