import { it,expect,vi } from 'vitest'
import { render,screen,fireEvent } from '@testing-library/react'
import { TaskActions } from '@/components/task-actions'
import type { Control,Transport } from '@/lib/contracts'
import { ApiError } from '@/lib/http-transport'
const control:Control={task:{id:1,state:'needs_input',stage:'planning',request:'Запрос',updated:1,artifacts:[]},revision:'r1',allowed_actions:['answer','approve_plan','revise_plan','accept_result','request_changes','reject_result'],pending_question_id:'q1',plan:{version:2,digest:'digest'},result:null,confirmation_urls:{approve_plan:'http://127.0.0.1:47832/confirm?id=1'}}
const session={csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}
it('повторяет неопределённый POST с исходными телом, ключом и revision после polling',async()=>{
 const post=vi.fn().mockRejectedValueOnce(new TypeError('Сеть недоступна')).mockResolvedValue({operation_id:'op',status:'pending',task_id:1})
 const get=vi.fn().mockResolvedValue({status:'succeeded'});const transport={get,post} as Transport
 const {rerender}=render(<TaskActions control={control} session={session} transport={transport} onRefresh={vi.fn()}/> )
 fireEvent.change(screen.getByLabelText('Ответ на вопрос'),{target:{value:'Исходный ответ'}})
 fireEvent.click(screen.getByText('Отправить ответ'))
 await screen.findByText('Сеть недоступна')
 rerender(<TaskActions control={{...control,revision:'r2',allowed_actions:[],pending_question_id:'q2'}} session={session} transport={transport} onRefresh={vi.fn()}/> )
 fireEvent.click(screen.getByText('Повторить команду / проверить результат'))
 await screen.findByText('Команда выполнена контроллером')
 expect(post).toHaveBeenCalledTimes(2)
 expect(post.mock.calls[1]).toEqual(post.mock.calls[0])
 expect(post.mock.calls[1][1]).toEqual({action:'answer',question_id:'q1',text:'Исходный ответ'})
 expect(post.mock.calls[1][4]).toBe('r1')
})
it('освобождает команду после окончательного 409 и использует новую revision',async()=>{
 const post=vi.fn().mockRejectedValueOnce(new ApiError('conflict','Версия устарела',409)).mockResolvedValue({operation_id:'op',status:'pending',task_id:1})
 const transport={post,get:vi.fn().mockResolvedValue({status:'succeeded'})} as Transport
 const refresh=vi.fn();const initial={...control,allowed_actions:['pause']}
 const {rerender}=render(<TaskActions control={initial} session={session} transport={transport} onRefresh={refresh}/> )
 fireEvent.click(screen.getByText('Пауза'));await screen.findByText('Версия устарела')
 expect(screen.queryByText('Повторить команду / проверить результат')).toBeNull()
 expect(refresh).toHaveBeenCalledTimes(1)
 rerender(<TaskActions control={{...initial,revision:'r2',allowed_actions:['resume']}} session={session} transport={transport} onRefresh={refresh}/> )
 fireEvent.click(screen.getByText('Продолжить'));await screen.findByText('Команда выполнена контроллером')
 expect(post.mock.calls[1][4]).toBe('r2')
 expect(post.mock.calls[1][2]).not.toBe(post.mock.calls[0][2])
})
it('после сбоя GET проверяет прежнюю операцию без повторного POST',async()=>{
 const post=vi.fn().mockResolvedValue({operation_id:'op',status:'pending',task_id:1})
 const get=vi.fn().mockRejectedValueOnce(new TypeError('Ошибка проверки')).mockResolvedValue({status:'succeeded'})
 render(<TaskActions control={{...control,allowed_actions:['start']}} session={session} transport={{get,post} as Transport} onRefresh={vi.fn()}/> )
 fireEvent.click(screen.getByText('Запустить'));await screen.findByText('Ошибка проверки')
 fireEvent.click(screen.getByText('Повторить команду / проверить результат'));await screen.findByText('Команда выполнена контроллером')
 expect(post).toHaveBeenCalledTimes(1)
 expect(get.mock.calls).toEqual([['operations/op'],['operations/op']])
})
it('сохраняет ввод при обновлении snapshot',()=>{const transport={get:vi.fn(),post:vi.fn()} as Transport;const refresh=vi.fn();const {rerender}=render(<TaskActions control={control} transport={transport} onRefresh={refresh}/>);fireEvent.change(screen.getByLabelText('Ответ на вопрос'),{target:{value:'Несохранённый ответ'}});rerender(<TaskActions control={{...control,revision:'r2',task:{...control.task,updated:2}}} transport={transport} onRefresh={refresh}/>);expect((screen.getByLabelText('Ответ на вопрос') as HTMLTextAreaElement).value).toBe('Несохранённый ответ')})
it('передаёт решение встроенному origin без POST и фиктивного успеха',()=>{
 const post=vi.fn();render(<TaskActions control={{...control,confirmation_widgets:{approve_plan:'http://127.0.0.1:47832/confirm/embed?id=1'}}} session={session} transport={{projectId:'a',get:vi.fn(),post} as Transport} onRefresh={vi.fn()}/>)
 expect(screen.getByTitle('Утвердить план').getAttribute('src')).toBe('http://127.0.0.1:47832/confirm/embed?id=1')
 expect(screen.queryByRole('link',{name:'Открыть подтверждение'})).toBeNull()
 expect(post).not.toHaveBeenCalled()
 expect(screen.queryByText('Команда выполнена контроллером')).toBeNull()
})
it('ждёт GET операции и отправляет question_id',async()=>{let finish:(value:unknown)=>void=()=>{};const get=vi.fn().mockImplementation(()=>new Promise(resolve=>{finish=resolve}));const post=vi.fn().mockResolvedValue({operation_id:'op',status:'pending',task_id:1});render(<TaskActions control={control} session={{csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}} transport={{get,post} as Transport} onRefresh={vi.fn()}/>);fireEvent.change(screen.getByLabelText('Ответ на вопрос'),{target:{value:'Ответ'}});fireEvent.click(screen.getByText('Отправить ответ'));await vi.waitFor(()=>expect(get).toHaveBeenCalled());expect(post).toHaveBeenCalledWith('tasks/1/actions',{action:'answer',question_id:'q1',text:'Ответ'},expect.any(String),'csrf','r1');expect(screen.queryByText('Команда выполнена контроллером')).toBeNull();finish({status:'succeeded'});expect(document.body.contains(await screen.findByText('Команда выполнена контроллером'))).toBe(true)})

it('восстанавливает неизвестную команду после переключения задачи и перезагрузки вкладки',async()=>{
 const post=vi.fn().mockRejectedValueOnce(new TypeError('Связь потеряна')).mockResolvedValue({operation_id:'op',status:'pending',task_id:1})
 const transport={post,get:vi.fn().mockResolvedValue({status:'succeeded'})} as Transport
 const props={control,session,transport,onRefresh:vi.fn()}
 const first=render(<TaskActions {...props}/>)
 fireEvent.change(screen.getByLabelText('Ответ на вопрос'),{target:{value:'Точный ответ'}})
 fireEvent.click(screen.getByText('Отправить ответ'));await screen.findByText('Связь потеряна')
 const stored=window.sessionStorage.getItem('tw-web:pending:task:1')
 if(stored===null)throw Error('Команда не сохранена')
 expect(stored).not.toContain('csrf')
 first.unmount()
 const other=render(<TaskActions {...props} control={{...control,task:{...control.task,id:2}}}/>)
 expect(screen.queryByText('Повторить команду / проверить результат')).toBeNull()
 other.unmount()
 window.sessionStorage.clear()
 window.sessionStorage.setItem('tw-web:pending:task:1',stored)
 render(<TaskActions {...props} control={{...control,revision:'r2',pending_question_id:'q2'}}/>)
 fireEvent.click(screen.getByText('Повторить команду / проверить результат'))
 await screen.findByText('Команда выполнена контроллером')
 expect(post.mock.calls[1]).toEqual(post.mock.calls[0])
 expect(window.sessionStorage.getItem('tw-web:pending:task:1')).toBeNull()
})
it('после remount продолжает GET сохранённой операции без повторного POST',async()=>{
 const post=vi.fn().mockResolvedValue({operation_id:'saved-op',status:'pending',task_id:1})
 const get=vi.fn().mockRejectedValueOnce(new TypeError('Нет результата')).mockResolvedValue({status:'succeeded'})
 const props={control:{...control,allowed_actions:['start']},session,transport:{get,post} as Transport,onRefresh:vi.fn()}
 const first=render(<TaskActions {...props}/>)
 fireEvent.click(screen.getByText('Запустить'));await screen.findByText('Нет результата')
 first.unmount()
 render(<TaskActions {...props}/>)
 fireEvent.click(screen.getByText('Повторить команду / проверить результат'));await screen.findByText('Команда выполнена контроллером')
 expect(post).toHaveBeenCalledTimes(1)
 expect(get.mock.calls).toEqual([['operations/saved-op'],['operations/saved-op']])
})

it('не отправляет команду, если невозможно сохранить ключ до POST',async()=>{
 const post=vi.fn()
 render(<TaskActions control={{...control,allowed_actions:['start']}} session={session} transport={{get:vi.fn(),post} as Transport} onRefresh={vi.fn()}/>)
 vi.spyOn(Storage.prototype,'setItem').mockImplementationOnce(()=>{throw new Error('Хранилище недоступно')})
 fireEvent.click(screen.getByText('Запустить'))
 await screen.findByText('Не удалось сохранить команду. Отправка отменена.')
 expect(post).not.toHaveBeenCalled()
})
