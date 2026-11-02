import { it,expect } from 'vitest'
import { render,screen } from '@testing-library/react'
import { TaskProgress } from '@/components/task-progress'
import { taskProgress } from '@/lib/task-presentation'

it.each([['plan',0],['implement',1],['check',2],['review',3],['done',4]] as const)('отражает текущий этап %s', (stage,index)=>{
 expect(taskProgress({stage,state:'review'}).index).toBe(index)
})
it('различает ожидание приёмки, принятие и отклонение',()=>{
 expect(taskProgress({stage:'done',state:'review'}).text).toBe('Ожидает приёмки')
 expect(taskProgress({stage:'done',state:'accepted'}).text).toBe('Принято человеком')
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
 expect(screen.getByText('Проверки').getAttribute('aria-current')).toBe('step')
 view.rerender(<TaskProgress task={{...task,stage:'implement'}}/>)
 expect(screen.getByText('Реализация').getAttribute('aria-current')).toBe('step')
 expect(screen.getByText('Проверки').getAttribute('aria-current')).toBeNull()
 view.rerender(<TaskProgress task={task}/>)
 expect(screen.getByText('Проверки').getAttribute('aria-current')).toBe('step')
 expect(screen.getAllByRole('listitem')).toHaveLength(5)
})
