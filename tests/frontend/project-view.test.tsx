import { it,expect,vi } from 'vitest'
import { render,screen,fireEvent,act } from '@testing-library/react'
import { ProjectView } from '@/components/project-view'
import { viewReady } from '@/hooks/use-project-view'
import { ApiError } from '@/lib/http-transport'
import type { ProjectViewResponse,Task,Transport } from '@/lib/contracts'

it('реальный контракт разделяет If-Match и ревизию результата после succeeded',async()=>{
 const selection='71e70245-68d1-4b59-a0b1-32605b8ea023'
 const digest='a'.repeat(64)
 const ready=data()
 ready.revision='b'.repeat(64)
 Object.assign(ready.view!,{revision:`${selection}:${digest}`,requested:{task:1,mode:'checked',revision:selection},source_digest:digest})
 const building={...ready,view:{...ready.view!,current:false,building:true}}
 let current:ProjectViewResponse=building
 const get=vi.fn().mockImplementation(async()=>current)
 const post=vi.fn().mockResolvedValue({operation_id:'op',task_id:1,status:'succeeded'})
 const url=`http://localhost:8080/tasks/1?version=${digest}`
 vi.useFakeTimers()
 const view=render(<ProjectView task={{...task,preview:{url,persistent:true,current:true,read_only:true,mode:'checked',version:digest}}} transport={{get,post}} enabled session={session}/>)
 try{
  await act(async()=>{})
  fireEvent.click(screen.getByText('Показать проверенную версию'))
  await act(async()=>{})
  expect(screen.getByText('Подготовка')).toBeTruthy()
  expect(screen.queryByRole('link')).toBeNull()
  current=ready
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
  expect(screen.getByText('Готово')).toBeTruthy()
  expect(screen.getByRole('link',{name:'Открыть результат'}).getAttribute('href')).toBe(url)
  expect(post).toHaveBeenCalledWith('tasks/1/view',{action:'select',mode:'checked'},expect.any(String),'csrf',ready.revision)
  expect(screen.getByText(`Версия исходников: ${digest.slice(0,12)}`)).toBeTruthy()
  expect(screen.getByText(`Полная версия исходников: ${digest}`).closest('details')?.open).toBe(false)
 }finally{view.unmount();vi.useRealTimers()}
})
it.each([null,'other-selection:digest','selection-uuid:other-digest'])('не подтверждает неверную ревизию опубликованного просмотра %s',revision=>{
 const value=data();value.view!.revision=revision
 expect(viewReady(value,1)).toBe(false)
})
it('токен If-Match не участвует в подтверждении готовности',()=>{
 const value=data();value.revision=null
 expect(viewReady(value,1)).toBe(true)
})
it.each(['revision','task','mode'] as const)('не подтверждает противоречивый requested: %s',kind=>{
 const value=data()
 if(kind==='revision')value.view!.requested!.revision='old-revision'
 if(kind==='task')value.view!.requested!.task=2
 if(kind==='mode')value.view!.requested!.mode='working'
 expect(viewReady(value,1)).toBe(false)
})
it('просмотр без requested не подтверждает согласованность версии',()=>{
 const value=data();value.view!.requested=null
 expect(viewReady(value,1)).toBe(false)
 expect(viewReady(value,2)).toBe(false)
})
it.each(['independent-version',42,undefined] as const)('не открывает persistent результат с несовпадающей или отсутствующей версией %s',async version=>{
 const url='http://localhost:8080/tasks/1?version=independent'
 render(<ProjectView task={{...task,preview:{url,persistent:true,current:true,read_only:true,mode:'checked',version}}} transport={{get:vi.fn().mockResolvedValue(data()),post:vi.fn()}} enabled session={session}/>)
 await screen.findByText('Готово')
 expect(screen.queryByRole('link',{name:'Открыть результат'})).toBeNull()
})

it.each(['error','stopped','unavailable'] as const)('после succeeded показывает %s вместо бесконечной подготовки',async(kind)=>{
 const terminal=data()
 if(kind==='error')terminal.view!.error='Ошибка сборки'
 if(kind==='stopped')terminal.view!.running=false
 if(kind==='unavailable'){terminal.available=false;terminal.reason='Просмотр отключён';terminal.view=null}
 const get=vi.fn().mockResolvedValueOnce(data()).mockResolvedValue(terminal)
 const post=vi.fn().mockResolvedValue({operation_id:'op',task_id:1,status:'succeeded'})
 vi.useFakeTimers()
 const view=render(<ProjectView task={task} transport={{get,post}} enabled session={session}/>)
 try{
  await act(async()=>{})
  fireEvent.click(screen.getByText('Показать проверенную версию'))
  await act(async()=>{})
  const label=kind==='error'?'Ошибка подготовки':kind==='stopped'?'Просмотр остановлен':'Просмотр отсутствует'
  expect(screen.getByText(label)).toBeTruthy()
  expect(screen.queryByText('Подготовка')).toBeNull()
  await act(async()=>{await vi.advanceTimersByTimeAsync(4000)})
  expect(screen.getByText(label)).toBeTruthy()
  expect(screen.queryByText('Подготовка')).toBeNull()
  expect(post).toHaveBeenCalledTimes(1)
 }finally{view.unmount();vi.useRealTimers()}
})
it('refresh проходит pending и operations succeeded, затем ждёт готовность GET',async()=>{
 const building=data();building.view!.building=true;building.view!.current=false
 let current=data()
 const get=vi.fn().mockImplementation(async(path:string)=>path==='operations/refresh-op'?{operation_id:'refresh-op',task_id:1,status:'succeeded'}:current)
 const post=vi.fn().mockImplementation(async()=>{current=building;return {operation_id:'refresh-op',task_id:1,status:'pending'}})
 vi.useFakeTimers()
 const view=render(<ProjectView task={task} transport={{get,post}} enabled session={session}/>)
 try{
  await act(async()=>{})
  fireEvent.click(screen.getByText('Повторить подготовку'))
  await act(async()=>{})
  expect(post).toHaveBeenCalledWith('tasks/1/view',{action:'refresh',mode:'checked'},expect.any(String),'csrf','view-r1')
  expect(screen.getByText('Подготовка')).toBeTruthy()
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
  expect(get.mock.calls.some(([path])=>path==='operations/refresh-op')).toBe(true)
  expect(screen.queryByText('Готово')).toBeNull()
  current=data()
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
  expect(screen.getByText('Готово')).toBeTruthy()
  expect(post).toHaveBeenCalledTimes(1)
 }finally{view.unmount();vi.useRealTimers()}
})
it('поздний ответ operations другого проекта не меняет новый scope',async()=>{
 let resolve:(value:unknown)=>void=()=>{}
 const get=vi.fn().mockImplementation((path:string)=>path==='operations/old-op'?new Promise(done=>{resolve=done}):Promise.resolve(data()))
 const first:Transport={projectId:'old-project',get,post:vi.fn().mockResolvedValue({operation_id:'old-op',task_id:1,status:'pending'})}
 const second:Transport={projectId:'new-project',get:vi.fn().mockResolvedValue({...data(),reason:'Новый проект'}),post:vi.fn()}
 vi.useFakeTimers()
 const view=render(<ProjectView task={task} transport={first} enabled session={session}/>)
 try{
  await act(async()=>{})
  fireEvent.click(screen.getByText('Показать рабочую версию'))
  await act(async()=>{})
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
  expect(get.mock.calls.some(([path])=>path==='operations/old-op')).toBe(true)
  view.rerender(<ProjectView task={task} transport={second} enabled session={session}/>)
  await act(async()=>{})
  await act(async()=>resolve({operation_id:'old-op',task_id:1,status:'failed',error:{message:'Поздняя ошибка операции'}}))
  expect(screen.queryByText('Поздняя ошибка операции')).toBeNull()
  expect(screen.getByText('Новый проект')).toBeTruthy()
  expect(screen.getByText('Готово')).toBeTruthy()
  expect(second.post).not.toHaveBeenCalled()
 }finally{view.unmount();vi.useRealTimers()}
})

const task:Task={id:1,state:'review',stage:'done',updated:1,request:'Запрос',artifacts:[]}
const session={csrf_token:'csrf',confirmation_origin:''}
function data(active=1):ProjectViewResponse{return {task_id:1,available:true,reason:null,revision:'view-r1',view:{revision:'selection-uuid:digest',url:'http://localhost:8080/',running:true,requested:{task:active,mode:'checked',revision:'selection-uuid'},active_task:active,mode:'checked',source_digest:'digest',current:true,building:false,message:''}}}
it('без capability не читает endpoint и не показывает runtime controls',()=>{
 const get=vi.fn();const post=vi.fn()
 render(<ProjectView task={task} transport={{get,post}} session={session}/>)
 expect(get).not.toHaveBeenCalled();expect(post).not.toHaveBeenCalled()
 expect(screen.queryByRole('button')).toBeNull()
})
it('legacy preview с read_only без capability сохраняет ссылку без готовности постоянного просмотра',()=>{
 const url='http://localhost:8080/tasks/1?version=legacy'
 const get=vi.fn();const post=vi.fn()
 render(<ProjectView task={{...task,preview:{url,read_only:true}}} transport={{get,post}} session={session}/>)
 expect(screen.getByRole('link',{name:'Открыть результат'}).getAttribute('href')).toBe(url)
 expect(screen.queryByText('Готово')).toBeNull()
 expect(screen.queryByRole('button')).toBeNull()
 expect(get).not.toHaveBeenCalled();expect(post).not.toHaveBeenCalled()
})
it('readonly не отправляет команд и не показывает кнопок',async()=>{
 const get=vi.fn().mockResolvedValue(data());const post=vi.fn()
 render(<ProjectView task={task} transport={{get,post}} enabled session={{...session,csrf_token:''}}/>)
 await screen.findByText('Готово')
 expect(screen.queryByRole('button')).toBeNull();expect(post).not.toHaveBeenCalled()
})
it('выбор карточки только читает; явный switch использует revision просмотра и показывает previous task',async()=>{
 const get=vi.fn().mockResolvedValue(data(9));const post=vi.fn().mockResolvedValue({operation_id:'op',task_id:1,status:'succeeded'})
 render(<ProjectView task={task} transport={{get,post,projectId:'main'}} enabled session={session}/>)
 await screen.findByText(/Сохранена предыдущая версия задачи 9/)
 expect(post).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'Показать рабочую версию'}))
 await vi.waitFor(()=>expect(post).toHaveBeenCalledWith('tasks/1/view',{action:'select',mode:'working'},expect.any(String),'csrf','view-r1'))
 expect(screen.queryByText('Готово')).toBeNull()
})
it('failed в успешном envelope остаётся ошибкой и обновляет GET',async()=>{
 const get=vi.fn().mockResolvedValue(data());const post=vi.fn().mockResolvedValue({operation_id:'op',task_id:1,status:'failed',error:{code:'build',message:'Сборка отклонена',retryable:false}})
 render(<ProjectView task={task} transport={{get,post}} enabled session={session}/>)
 await screen.findByText('Готово');fireEvent.click(screen.getByText('Показать проверенную версию'))
 await screen.findByText('Сборка отклонена');expect(get.mock.calls.length).toBeGreaterThan(1)
})
it('после потери ответа и reload явно повторяет прежние ключ, тело и revision',async()=>{
 const get=vi.fn().mockResolvedValue(data());const post=vi.fn().mockRejectedValueOnce(new TypeError('Ответ потерян')).mockResolvedValue({operation_id:'op',task_id:1,status:'succeeded'})
 const transport={get,post,projectId:'retry-project'}
 const first=render(<ProjectView task={task} transport={transport} enabled session={session}/>)
 await screen.findByText('Готово');fireEvent.click(screen.getByText('Показать рабочую версию'))
 await screen.findByText('Ответ потерян');first.unmount()
 render(<ProjectView task={task} transport={transport} enabled session={session}/>)
 await screen.findByText('Повторить прежнюю операцию');expect(post).toHaveBeenCalledTimes(1)
 fireEvent.click(screen.getByText('Повторить прежнюю операцию'))
 await vi.waitFor(()=>expect(post).toHaveBeenCalledTimes(2))
 expect(post.mock.calls[1]).toEqual(post.mock.calls[0])
})
it('поздний GET одинакового task_id другого проекта не меняет новый scope',async()=>{
 let resolve:(value:ProjectViewResponse)=>void=()=>{}
 const first:Transport={projectId:'a',get:vi.fn().mockImplementation(()=>new Promise(done=>{resolve=done})),post:vi.fn()}
 const second:Transport={projectId:'b',get:vi.fn().mockResolvedValue({...data(),reason:'Проект Б'}),post:vi.fn()}
 const view=render(<ProjectView task={task} transport={first} enabled session={session}/>)
 view.rerender(<ProjectView task={task} transport={second} enabled session={session}/>)
 await screen.findByText('Проект Б')
 await act(async()=>resolve({...data(9),reason:'Поздний проект А'}))
 expect(screen.queryByText('Поздний проект А')).toBeNull()
 expect(screen.getByText('Проект Б')).toBeTruthy()
})
it('готовая ссылка сохраняет путь и параметры preview, не берёт постоянный адрес',async()=>{
 const url='http://127.0.0.1:8080/tasks/1?digest=abc'
 render(<ProjectView task={{...task,preview:{url,persistent:true,current:true,read_only:true,mode:'checked',version:'digest'}}} transport={{get:vi.fn().mockResolvedValue(data()),post:vi.fn()}} enabled session={session}/>)
 expect((await screen.findByRole('link',{name:'Открыть результат'})).getAttribute('href')).toBe(url)
})
it('не открывает persistent preview при несовпадении режима или current',async()=>{
 render(<ProjectView task={{...task,preview:{url:'http://localhost:8080/task/1',persistent:true,current:false,read_only:true,mode:'working'}}} transport={{get:vi.fn().mockResolvedValue(data()),post:vi.fn()}} enabled session={session}/>)
 await screen.findByText('Готово');expect(screen.queryByRole('link')).toBeNull()
 expect(screen.getByText(/Результат: рабочая, неподтверждённая/)).toBeTruthy()
})
it('null revision блокирует select и противоречивый requested не доказывает готовность',async()=>{
 const value=data();value.revision=null
 render(<ProjectView task={task} transport={{get:vi.fn().mockResolvedValue(value),post:vi.fn()}} enabled session={session}/>)
 await screen.findByText(/контроллер не предоставил ревизию/)
 expect((screen.getByText('Показать проверенную версию') as HTMLButtonElement).disabled).toBe(true)
 const stale=data();stale.view!.requested={task:1,mode:'checked',revision:'old'}
 expect(viewReady(stale,1)).toBe(false);expect(viewReady(data(2),1)).toBe(false)
})
it('двойной клик не создаёт вторую команду; ошибка хранилища отменяет отправку',async()=>{
 const post=vi.fn().mockImplementation(()=>new Promise(()=>{}))
 const transport={get:vi.fn().mockResolvedValue(data()),post}
 const first=render(<ProjectView task={task} transport={transport} enabled session={session}/>)
 await screen.findByText('Готово')
 fireEvent.click(screen.getByText('Показать проверенную версию'));fireEvent.click(screen.getByText('Показать проверенную версию'))
 expect(post).toHaveBeenCalledTimes(1);first.unmount();window.sessionStorage.clear()
 const set=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw Error('Хранилище недоступно')})
 post.mockClear()
 render(<ProjectView task={task} transport={transport} enabled session={session}/>)
 await screen.findByText('Готово');fireEvent.click(screen.getByText('Показать проверенную версию'))
 await screen.findByText('Хранилище недоступно');expect(post).not.toHaveBeenCalled();set.mockRestore()
})
it('восстановленная операция проверяется явно и не переносится в другой проект',async()=>{
 window.sessionStorage.setItem('tw-web:pending:project:a:view:1',JSON.stringify({project:'a',task:1,body:{action:'select',mode:'working'},revision:'old',key:'same',operation:'op'}))
 const post=vi.fn();const get=vi.fn().mockImplementation(async(path:string)=>path==='operations/op'?{operation_id:'op',task_id:1,status:'succeeded'}:data())
 const first=render(<ProjectView task={task} transport={{projectId:'b',get,post}} enabled session={session}/>)
 await screen.findByText('Готово');expect(screen.queryByText('Повторить прежнюю операцию')).toBeNull();first.unmount()
 render(<ProjectView task={task} transport={{projectId:'a',get,post}} enabled session={session}/>)
 await screen.findByText('Повторить прежнюю операцию')
 expect(get.mock.calls.some(([path])=>path==='operations/op')).toBe(false)
 fireEvent.click(screen.getByText('Повторить прежнюю операцию'))
 await vi.waitFor(()=>expect(get).toHaveBeenCalledWith('operations/op'))
 expect(post).not.toHaveBeenCalled()
})
it('отклонённое переключение режима сбрасывает подготовку и сохраняет готовую проверенную ссылку',async()=>{
 const post=vi.fn().mockRejectedValue(new ApiError('conflict','Ревизия устарела',409))
 const get=vi.fn().mockResolvedValue(data())
 const preview={url:'http://localhost:3000/tasks/1?version=checked',persistent:true,current:true,read_only:true,mode:'checked' as const,version:'digest'}
 render(<ProjectView task={{...task,preview}} transport={{get,post}} enabled session={session}/>)
 await screen.findByText('Готово');fireEvent.click(screen.getByText('Показать рабочую версию'))
 await screen.findByText('Ревизия устарела')
 await screen.findByText('Готово')
 expect(screen.queryByText('Подготовка')).toBeNull()
 expect(screen.getByRole('link',{name:'Открыть результат'}).getAttribute('href')).toBe(preview.url)
 expect(post).toHaveBeenCalledWith('tasks/1/view',{action:'select',mode:'working'},expect.any(String),'csrf','view-r1')
 expect(post).toHaveBeenCalledTimes(1);expect(get.mock.calls.length).toBeGreaterThan(1)
 expect(screen.queryByText('Повторить прежнюю операцию')).toBeNull()
})
it('поздний POST после смены задачи не обновляет её состояние',async()=>{
 let resolve:(value:unknown)=>void=()=>{}
 const post=vi.fn().mockImplementation(()=>new Promise(done=>{resolve=done}))
 const transport={get:vi.fn().mockImplementation(async(path:string)=>path==='tasks/2/view'?{...data(2),task_id:2,reason:'Вторая задача'}:data()),post}
 const view=render(<ProjectView task={task} transport={transport} enabled session={session}/>)
 await screen.findByText('Готово');fireEvent.click(screen.getByText('Показать рабочую версию'))
 view.rerender(<ProjectView task={{...task,id:2}} transport={transport} enabled session={session}/>)
 await screen.findByText('Вторая задача')
 await act(async()=>resolve({operation_id:'op',task_id:1,status:'failed',error:{message:'Поздний отказ'}}))
 expect(screen.queryByText('Поздний отказ')).toBeNull()
 expect(screen.getByText('Вторая задача')).toBeTruthy()
})
it('фоновый GET сохраняет блок, а ошибка обновления блокирует новые команды',async()=>{
 let reject:(error:Error)=>void=()=>{}
 const get=vi.fn().mockResolvedValueOnce(data()).mockImplementation(()=>new Promise((_,fail)=>{reject=fail}))
 vi.useFakeTimers()
 const view=render(<ProjectView task={task} transport={{get,post:vi.fn()}} enabled session={session}/>)
 try{
  await act(async()=>{})
  expect(screen.getByText('Готово')).toBeTruthy()
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
  expect(screen.getByText('Версия исходников: digest')).toBeTruthy()
  await act(async()=>reject(Error('Обновление недоступно')))
  expect(screen.getByText(/Данные просмотра устарели/)).toBeTruthy()
  expect(screen.getByText('Версия исходников: digest')).toBeTruthy()
  expect((screen.getByText('Показать рабочую версию') as HTMLButtonElement).disabled).toBe(true)
 }finally{view.unmount();vi.useRealTimers()}
})
