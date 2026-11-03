import { it,expect } from 'vitest'
import { render,screen } from '@testing-library/react'
import { TaskProgress } from '@/components/task-progress'
import { taskProgress,taskStateLabel } from '@/lib/task-presentation'

it.each([
 [{},'Принято, применение не подтверждено'],
 [{integration:{source_commit:'a',commit:'1234567890',branch:'main'}},'Принято и применено'],
 [{integration:{source_commit:'',commit:'1234567890',branch:'main'}},'Принято, применение не подтверждено'],
 [{integration:{source_commit:'a',commit:'',branch:'main'}},'Принято, применение не подтверждено'],
 [{integration:{source_commit:'a',commit:'b',branch:''}},'Принято, применение не подтверждено'],
 [{integration_error:'Ошибка merge'},'Принято, применение остановлено'],
 [{commit_error:'Ошибка commit'},'Принято, коммит не создан'],
 [{integration_error:'Ошибка merge',commit_error:'Ошибка commit',integration:{source_commit:'a',commit:'b',branch:'main'}},'Принято, применение остановлено'],
 [{integration_error:' ',commit_error:'',integration:{source_commit:'a',commit:'b',branch:'main'}},'Принято и применено'],
 ] as const)('согласует фактическое применение %j',(fields,text)=>{
 const task={stage:'done',state:'accepted',...fields}
 expect(taskProgress(task).text).toBe(text)
 expect(taskStateLabel(task)).toBe(text)
})

it.each([['plan',0],['implement',1],['check',2],['review',3],['done',4]] as const)('отражает текущий этап %s', (stage,index)=>{
 expect(taskProgress({stage,state:'review'}).index).toBe(index)
})
it('различает ожидание приёмки, принятие и отклонение',()=>{
 expect(taskProgress({stage:'done',state:'review'}).text).toBe('Ожидает приёмки')
 expect(taskProgress({stage:'done',state:'accepted'}).text).toBe('Принято, применение не подтверждено')
 expect(taskProgress({stage:'done',state:'rejected'}).text).toContain('не завершена')
 expect(taskProgress({stage:'other',state:'running'}).index).toBeUndefined()
 expect(taskProgress({stage:'plan',state:'accepted'}).index).toBeUndefined()
 expect(taskProgress({stage:'check',state:'other'}).index).toBeUndefined()
})
it.each(['awaiting_approval','needs_input','needs_permission','rate_limited','paused','blocked','failed'])('сохраняет текущий шаг при %s',state=>{
 expect(taskProgress({stage:'implement',state}).index).toBe(1)
 expect(taskProgress({stage:'implement',state}).text).not.toBe(state)
})
it('возвращает индикатор check → implement → check без накопленного прогресса',()=>{
 const task={id:1,state:'running',stage:'check',updated:1,request:'Запрос',artifacts:[]}
 const view=render(<TaskProgress task={task}/>)
 expect(screen.getByLabelText(/Проверки/).closest('li')?.getAttribute('aria-current')).toBe('step')
 view.rerender(<TaskProgress task={{...task,stage:'implement'}}/>)
 expect(screen.getByLabelText(/Реализация/).closest('li')?.getAttribute('aria-current')).toBe('step')
 expect(screen.getByLabelText(/Проверки/).closest('li')?.getAttribute('aria-current')).toBeNull()
 view.rerender(<TaskProgress task={task}/>)
 expect(screen.getByLabelText(/Проверки/).closest('li')?.getAttribute('aria-current')).toBe('step')
 expect(screen.getAllByRole('listitem')).toHaveLength(5)
})
