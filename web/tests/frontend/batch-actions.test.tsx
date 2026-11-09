import { it,expect,vi } from 'vitest'
import { fireEvent,render,screen } from '@testing-library/react'
import { BatchActions } from '@/components/batch-actions'
import type { Transport } from '@/lib/contracts'
const tasks=[1,2].map(id=>({id,state:'backlog',stage:'plan',request:`Задача ${id}`,updated:1,artifacts:[]}))
const session={csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}
it('подтверждает весь набор и отправляет один batch запрос с revision',async()=>{
 const post=vi.fn().mockResolvedValue({operation_id:'op',status:'succeeded'})
 const done=vi.fn()
 render(<BatchActions tasks={tasks} transport={{projectId:'batch-delete',post,get:vi.fn().mockResolvedValue({revision:'q1'})}} session={session} disabled={false} onDone={done}/> )
 fireEvent.click(screen.getByText('Удалить выбранные'))
 expect(post).not.toHaveBeenCalled()
 fireEvent.click(screen.getByText('Переместить выбранные в корзину'))
 await screen.findByText('Групповая операция выполнена')
 expect(post).toHaveBeenCalledTimes(1)
 expect(post.mock.calls[0][0]).toBe('tasks/batch')
 expect(post.mock.calls[0][1]).toEqual({action:'delete',tasks:[1,2]})
 expect(post.mock.calls[0][4]).toBe('q1')
 expect(done).toHaveBeenCalledTimes(1)
})
it('после неизвестного исхода повторяет исходные ключ тело и revision после remount',async()=>{
 const post=vi.fn().mockRejectedValueOnce(new TypeError('Ответ потерян')).mockResolvedValue({operation_id:'op',status:'succeeded'})
 const transport={projectId:'batch-retry',post,get:vi.fn().mockResolvedValue({revision:'q1'})} as Transport
 const props={tasks,transport,session,disabled:false,onDone:vi.fn()}
 const view=render(<BatchActions {...props}/> )
 fireEvent.click(screen.getByText('В очередь'))
 await screen.findByText('Ответ потерян')
 view.unmount()
 render(<BatchActions {...props} tasks={[tasks[0]]}/> )
 expect(post).toHaveBeenCalledTimes(1)
 fireEvent.click(screen.getByText('Повторить / проверить групповую операцию'))
 await screen.findByText('Групповая операция выполнена')
 expect(post.mock.calls[1]).toEqual(post.mock.calls[0])
 expect(post.mock.calls[0][1]).toEqual({tasks:[1,2],start:true})
})
it('блокирует очередь для паузы и не отправляет команды при потере связи',()=>{
 const post=vi.fn()
 const props={tasks:[{...tasks[0],state:'paused'}],transport:{projectId:'paused',post,get:vi.fn()},session,disabled:false,onDone:vi.fn()}
 const view=render(<BatchActions {...props}/> )
 expect((screen.getByText('В очередь') as HTMLButtonElement).disabled).toBe(true)
 view.rerender(<BatchActions {...props} disabled/> )
 expect((screen.getByText('Удалить выбранные') as HTMLButtonElement).disabled).toBe(true)
 expect(post).not.toHaveBeenCalled()
})
it('уход со страницы во время preflight не отправляет команду',async()=>{
 let finish:(data:unknown)=>void=()=>{}
 const post=vi.fn()
 const transport={projectId:'leave-batch',post,get:vi.fn().mockImplementation(()=>new Promise(resolve=>{finish=resolve}))} as Transport
 const view=render(<BatchActions tasks={tasks} transport={transport} session={session} disabled={false} onDone={vi.fn()}/> )
 fireEvent.click(screen.getByText('В очередь'))
 view.unmount()
 finish({revision:'q1'})
 await Promise.resolve();await Promise.resolve()
 expect(post).not.toHaveBeenCalled()
})
