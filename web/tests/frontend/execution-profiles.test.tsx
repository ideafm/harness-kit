import {it,expect,vi} from 'vitest'
import {render,screen,fireEvent} from '@testing-library/react'
import {CreateTaskSheet} from '@/components/create-task-sheet'
import {ExecutionRoute} from '@/components/execution-route'
import type {Task} from '@/lib/contracts'
it('использует профиль проекта и даёт сменить его для одной задачи',async()=>{
 const post=vi.fn().mockResolvedValue({task:{id:8},revision:'r8'})
 const created=vi.fn()
 render(<CreateTaskSheet transport={{get:vi.fn(),post}} session={{csrf_token:'csrf',confirmation_origin:''}} enabled defaultExecutionProfile="auto-balanced" defaultBackend="gemini" onCreated={created}/> )
 fireEvent.click(screen.getByRole('button',{name:'＋ Новая задача'}))
 expect((screen.getByLabelText('Профиль исполнения') as HTMLSelectElement).value).toBe('default')
 expect(screen.getByText(/План: Sol; при сложности или риске/)).toBeTruthy()
 fireEvent.change(screen.getByLabelText('Профиль исполнения'),{target:{value:'thorough'}})
 expect(screen.getByText(/План: Astra → реализация: Gemini → ревью: Astra/)).toBeTruthy()
 fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Сделать изменение'}})
 fireEvent.click(screen.getByRole('button',{name:'Создать задачу'}))
 await vi.waitFor(()=>expect(created).toHaveBeenCalledWith(8))
 expect(post).toHaveBeenCalledWith('tasks',expect.objectContaining({execution_profile:'thorough'}),expect.any(String),'csrf')
})
it('передаёт default balanced явно, сохраняя выбор при повторе',async()=>{
 const post=vi.fn().mockRejectedValue(new TypeError('Связь потеряна'))
 render(<CreateTaskSheet transport={{projectId:'profile-default',get:vi.fn(),post}} session={{csrf_token:'csrf',confirmation_origin:''}} enabled defaultExecutionProfile="auto-balanced" onCreated={vi.fn()}/> )
 fireEvent.click(screen.getByRole('button',{name:'＋ Новая задача'}))
 fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Изменение'}})
 fireEvent.click(screen.getByRole('button',{name:'Создать задачу'}))
 await screen.findByText('Связь потеряна')
 expect(post.mock.calls[0][1].execution_profile).toBe('auto-balanced')
 fireEvent.click(screen.getByRole('button',{name:'Создать задачу'}))
 await vi.waitFor(()=>expect(post).toHaveBeenCalledTimes(2))
 expect(post.mock.calls[1]).toEqual(post.mock.calls[0])
})
it('показывает реальный маршрут и причину повышения модели',()=>{
 const task:Task={id:1,state:'running',stage:'implement',updated:1,request:'task',artifacts:[],execution_policy:{version:1,profile:'auto-balanced',stages:{plan:{backend:'codex',model:'gpt-6-astra'},implement:{backend:'gemini',model:'configured-model'},review:{backend:'codex',model:'gpt-6-astra'}},history:[{stage:'plan',backend:'codex',model:'gpt-6-astra',reason:'Критические изменения'}]}}
 render(<ExecutionRoute task={task}/> )
 expect(screen.getByText('План: Astra')).toBeTruthy()
 expect(screen.getByText('Реализация: Gemini · configured-model')).toBeTruthy()
 expect(screen.getByText(/Критические изменения/)).toBeTruthy()
})
