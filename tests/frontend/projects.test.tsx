import { afterEach,it,expect,vi } from 'vitest'
import { act,fireEvent,render,screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Control,Transport } from '@/lib/contracts'
import { useTaskData } from '@/hooks/use-task-data'
import { projectTransport,pendingSlot,readPending,writePending } from '@/lib/transport'
import { CreateTaskSheet } from '@/components/create-task-sheet'
import { TaskActions } from '@/components/task-actions'
import { ProjectSidebar } from '@/components/project-sidebar'
import { SidebarProvider } from '@/components/ui/sidebar'
import { TaskPanel } from '@/components/task-table'

const session={csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}
const task={id:1,state:'running',stage:'implement',updated:1,request:'Задача',artifacts:[]}
const control:Control={task,revision:'r1',allowed_actions:['start'],plan:null,result:null,confirmation_urls:{}}
const projects={items:[{id:'a',name:'Альфа'},{id:'b',name:'Бета'}],default_project_id:'a',connect_url:'http://127.0.0.1:47832/connect'}
afterEach(()=>window.history.replaceState(null,'','/'))
function api(){
 const get=vi.fn<(path:string,signal?:AbortSignal)=>Promise<unknown>>().mockImplementation(async(path:string)=>{
  if(path==='projects')return projects
  if(path==='session')return session
  if(path.endsWith('/status'))return {project:path,tasks:[task],worker:{running:false}}
  if(path.endsWith('/capabilities'))return {actions:['create'],events:false,apply:false}
  if(path.endsWith('/control'))return control
  throw Error(path)
 })
 const post=vi.fn()
 return {get,post} as Transport & {get:typeof get;post:typeof post}
}
function Harness({base}:{base:Transport}){
 const data=useTaskData(base)
 return <><button onClick={()=>data.selectProject('b')}>Бета</button><button onClick={()=>data.selectProject('a')}>Альфа</button><button onClick={()=>data.select(1)}>Выбрать</button><output>{data.status?`${data.projectId}:${data.selected??'нет'}`:'пусто'}</output><p>{data.projects?.items.map(p=>p.name).join(', ')}</p><p>{data.error}</p>{data.status&&<p>{String(data.status.project)}</p>}<CreateTaskSheet key={data.projectId} transport={data.transport} session={data.session} enabled={Boolean(data.capabilities)} onCreated={data.select}/></>
}
it('кодирует проект одним сегментом и сохраняет аргументы команд',async()=>{
 const base=api();base.get.mockResolvedValue({});base.post.mockResolvedValue({})
 const transport=projectTransport(base,'a/b ?')
 await transport.get('session');await transport.get('tasks/1/events');await transport.get('tasks/1/artifacts/diff');await transport.get('operations/op')
 await transport.post('tasks/1/actions',{action:'start'},'key','csrf','rev')
 expect(base.get.mock.calls.map(c=>c[0])).toEqual(['session','projects/a%2Fb%20%3F/tasks/1/events','projects/a%2Fb%20%3F/tasks/1/artifacts/diff','projects/a%2Fb%20%3F/operations/op'])
 expect(base.post).toHaveBeenCalledWith('projects/a%2Fb%20%3F/tasks/1/actions',{action:'start'},'key','csrf','rev')
})
it('восстанавливает URL, сбрасывает задачу и изолирует одинаковые id',async()=>{
 window.history.replaceState(null,'','/?project=a&task=1')
 const base=api();render(<Harness base={base}/>)
 await screen.findByText('a:1')
 fireEvent.click(screen.getByText('Бета'));await screen.findByText('b:нет')
 expect(new URLSearchParams(window.location.search).has('task')).toBe(false)
 fireEvent.click(screen.getByText('Выбрать'));await screen.findByText('b:1')
 expect(base.get.mock.calls.some(c=>c[0]==='projects/b/tasks/1/control')).toBe(true)
 expect(window.location.search).toContain('project=b&task=1')
 act(()=>{window.history.replaceState(null,'','/?project=a&task=1');window.dispatchEvent(new PopStateEvent('popstate'))})
 await screen.findByText('a:1')
})
it.each(['.','..'])('показывает ошибку dot segment %s без чужих данных и проектных запросов',async(id)=>{
 window.history.replaceState(null,'','/?project='+encodeURIComponent(id)+'&task=1')
 const base=api();const original=base.get.getMockImplementation()!
 base.get.mockImplementation((path:string,signal?:AbortSignal)=>path==='projects'?Promise.resolve({...projects,items:[...projects.items,{id,name:'Особый проект'}]}):original(path,signal))
 render(<Harness base={base}/>)
 await screen.findByText('Идентификатор проекта нельзя безопасно передать в URL')
 expect(screen.getByText('пусто')).toBeTruthy()
 expect(base.get.mock.calls.every(c=>c[0]==='projects'||c[0]==='session')).toBe(true)
 expect(base.post).not.toHaveBeenCalled()
 expect(screen.queryByText('a:1')).toBeNull()
})
it.each(['?project=unknown&task=1','?project=a&task=99','?project=a&task=bad'])('не подменяет неизвестный контекст %s',async(query)=>{
 window.history.replaceState(null,'','/'+query)
 const base=api();render(<Harness base={base}/>)
 await screen.findByText(query.includes('unknown')?'Неизвестный проект':'Неизвестная задача в выбранном проекте')
 expect(screen.queryByText('a:1')).toBeNull()
 expect(base.get.mock.calls.some(c=>c[0].endsWith('/control'))).toBe(false)
})
it('игнорирует поздний ответ проекта, даже если mock игнорирует abort',async()=>{
 const base=api();const original=base.get.getMockImplementation()!
 let finish:(value:unknown)=>void=()=>{}
 base.get.mockImplementation((path:string,signal?:AbortSignal)=>path==='projects/a/status'?new Promise(resolve=>{finish=resolve}):original(path,signal))
 render(<Harness base={base}/>)
 await vi.waitFor(()=>expect(base.get).toHaveBeenCalledWith('projects/a/status',expect.anything()))
 fireEvent.click(screen.getByText('Бета'));await screen.findByText('b:нет')
 await act(async()=>finish({project:'Чужие данные',tasks:[task],worker:{running:false}}))
 expect(screen.queryByText('Чужие данные')).toBeNull();expect(screen.getByText('b:нет')).toBeTruthy()
})
it('создаёт задачу только в выбранном проекте',async()=>{
 const base=api();base.post.mockResolvedValue({task,revision:'r1'})
 render(<Harness base={base}/>);await screen.findByText('a:нет')
 fireEvent.click(screen.getByText('Бета'));await screen.findByText('b:нет')
 fireEvent.click(screen.getByText('＋ Новая задача'));fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Новый запрос'}});fireEvent.click(screen.getByText('Создать задачу'))
 await vi.waitFor(()=>expect(base.post).toHaveBeenCalledWith('projects/b/tasks',{request:'Новый запрос',approval_mode:'approve-plan'},expect.any(String),'csrf',undefined))
 await screen.findByText('b:1')
})
it('сохраняет старые слоты и разделяет pending по проектам',()=>{
 const base=api();const a=projectTransport(base,'a');const b=projectTransport(base,'b')
 writePending('create',{key:'legacy'});writePending(pendingSlot(a,'create'),{key:'a'});writePending(pendingSlot(b,'create'),{key:'b'})
 writePending(pendingSlot(a,'task:1'),{operation:'op-a'});writePending(pendingSlot(b,'task:1'),{operation:'op-b'})
 expect(readPending('create')).toEqual({key:'legacy'})
 expect(readPending(pendingSlot(a,'create'))).toEqual({key:'a'})
 expect(readPending(pendingSlot(b,'task:1'))).toEqual({operation:'op-b'})
})
it('сохраняет operation после ухода и восстанавливает GET без POST',async()=>{
 const base=api();let finish:(value:unknown)=>void=()=>{}
 base.post.mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
 const a=projectTransport(base,'a');const b=projectTransport(base,'b');const refresh=vi.fn()
 const first=render(<TaskActions control={control} transport={a} session={session} onRefresh={refresh}/>)
 fireEvent.click(screen.getByText('Запустить'));first.unmount()
 const other=render(<TaskActions control={control} transport={b} session={session} onRefresh={refresh}/>)
 await act(async()=>finish({operation_id:'op-a',status:'pending',task_id:1}))
 expect(screen.queryByText('Повторить команду / проверить результат')).toBeNull()
 expect(refresh).not.toHaveBeenCalled()
 expect(readPending<{operation:string}>(pendingSlot(a,'task:1'))?.operation).toBe('op-a')
 other.unmount();base.get.mockResolvedValue({status:'succeeded'})
 render(<TaskActions control={control} transport={a} session={session} onRefresh={refresh}/>)
 fireEvent.click(screen.getByText('Повторить команду / проверить результат'));await screen.findByText('Команда выполнена контроллером')
 expect(base.post).toHaveBeenCalledTimes(1)
 expect(base.get).toHaveBeenCalledWith('projects/a/operations/op-a',undefined)
})
it('обновляет список проектов при возврате фокуса и видимости',async()=>{
 const base=api();render(<Harness base={base}/>);await screen.findByText('a:нет')
 const count=base.get.mock.calls.filter(c=>c[0]==='projects').length
 const original=base.get.getMockImplementation()!
 base.get.mockImplementation((path:string,signal?:AbortSignal)=>path==='projects'?Promise.resolve({...projects,items:[...projects.items,{id:'c',name:'Гамма'}]}):original(path,signal))
 act(()=>window.dispatchEvent(new Event('focus')))
 await vi.waitFor(()=>expect(base.get.mock.calls.filter(c=>c[0]==='projects').length).toBeGreaterThan(count))
 await screen.findByText('Альфа, Бета, Гамма')
 act(()=>document.dispatchEvent(new Event('visibilitychange')))
 await vi.waitFor(()=>expect(base.get.mock.calls.filter(c=>c[0]==='projects').length).toBeGreaterThan(count+1))
})
it('открывает доверенное подключение отдельной страницей без регистрации пути',()=>{
 const onSelect=vi.fn()
 render(<SidebarProvider><ProjectSidebar project="Альфа" count={1} running={false} projects={projects} selected="a" onSelect={onSelect}/></SidebarProvider>)
 expect(screen.getByRole('button',{name:'Альфа'}).getAttribute('aria-current')).toBe('page')
 const link=screen.getByRole('link',{name:'Подключить проект'})
 expect(link.getAttribute('href')).toBe(projects.connect_url)
 expect(link.getAttribute('target')).toBe('_blank')
 expect(link.getAttribute('rel')).toBe('noopener noreferrer')
 fireEvent.click(screen.getByRole('button',{name:'Бета'}));expect(onSelect).toHaveBeenCalledWith('b')
})
it('не повторяет создание при смене проекта и сохраняет неопределённый исход для возврата',async()=>{
 const base=api();let fail:(reason:unknown)=>void=()=>{}
 base.post.mockImplementation(()=>new Promise((_,reject)=>{fail=reject}))
 const a=projectTransport(base,'a');const b=projectTransport(base,'b');const onCreated=vi.fn()
 const first=render(<CreateTaskSheet transport={a} session={session} enabled onCreated={onCreated}/>)
 fireEvent.click(screen.getByText('＋ Новая задача'));fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Сохранённый запрос'}});fireEvent.click(screen.getByText('Создать задачу'))
 const stored=window.sessionStorage.getItem(`tw-web:pending:${pendingSlot(a,'create')}`)
 first.unmount()
 const second=render(<CreateTaskSheet transport={b} session={session} enabled onCreated={onCreated}/>)
 await act(async()=>fail(new TypeError('Неизвестный исход')))
 expect(base.post).toHaveBeenCalledTimes(1);expect(onCreated).not.toHaveBeenCalled()
 expect(window.sessionStorage.getItem(`tw-web:pending:${pendingSlot(a,'create')}`)).toBe(stored)
 second.unmount();base.post.mockResolvedValue({task,revision:'r1'})
 render(<CreateTaskSheet transport={a} session={session} enabled onCreated={onCreated}/>)
 expect(base.post).toHaveBeenCalledTimes(1)
 fireEvent.click(screen.getByText('＋ Новая задача'))
 expect((screen.getByLabelText('Запрос') as HTMLTextAreaElement).value).toBe('Сохранённый запрос')
 fireEvent.click(screen.getByText('Создать задачу'));await vi.waitFor(()=>expect(onCreated).toHaveBeenCalledWith(1))
 expect(base.post.mock.calls[1]).toEqual(base.post.mock.calls[0])
})
it('изолирует артефакты одинаковых task id и игнорирует позднее содержимое',async()=>{
 const user=userEvent.setup()
 const base=api();const original=base.get.getMockImplementation()!
 let finish:(value:unknown)=>void=()=>{}
 base.get.mockImplementation((path:string,signal?:AbortSignal)=>{
  if(path.endsWith('/status'))return Promise.resolve({project:path,tasks:[{...task,artifacts:['diff']}],worker:{running:false}})
  if(path.endsWith('/control'))return Promise.resolve({...control,task:{...task,artifacts:['diff']}})
  if(path==='projects/a/tasks/1/artifacts/diff')return new Promise(resolve=>{finish=resolve})
  if(path==='projects/b/tasks/1/artifacts/diff')return Promise.resolve({task:1,artifact:'diff',text:'<b>Артефакт Беты</b>',truncated:false})
  return original(path,signal)
 })
 render(<TaskPanel transport={base}/>)
 fireEvent.click(await screen.findByRole('button',{name:'#1 Задача'}))
 await user.click(await screen.findByRole('tab',{name:'Изменения'}))
 await vi.waitFor(()=>expect(base.get).toHaveBeenCalledWith('projects/a/tasks/1/artifacts/diff',expect.anything()))
 fireEvent.click(screen.getByRole('button',{name:'Бета'}))
 await vi.waitFor(()=>expect(screen.getByRole('button',{name:'Бета'}).getAttribute('aria-current')).toBe('page'))
 fireEvent.click(await screen.findByRole('button',{name:'#1 Задача'}))
 await user.click(await screen.findByRole('tab',{name:'Изменения'}))
 await screen.findByText('<b>Артефакт Беты</b>')
 await act(async()=>finish({task:1,artifact:'diff',text:'Чужой артефакт Альфы',truncated:false}))
 expect(screen.queryByText('Чужой артефакт Альфы')).toBeNull()
 expect(screen.getByText('<b>Артефакт Беты</b>')).toBeTruthy()
 expect(document.querySelector('.artifact b')).toBeNull()
})
it('после ухода во время GET не продолжает polling и сохраняет операцию',async()=>{
 const base=api();let finish:(value:unknown)=>void=()=>{}
 base.post.mockResolvedValue({operation_id:'poll-op',status:'pending',task_id:1})
 base.get.mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
 const transport=projectTransport(base,'a')
 const first=render(<TaskActions control={control} transport={transport} session={session} onRefresh={vi.fn()}/>)
 fireEvent.click(screen.getByText('Запустить'))
 await vi.waitFor(()=>expect(base.get).toHaveBeenCalledTimes(1))
 first.unmount()
 await act(async()=>finish({status:'pending'}))
 expect(base.get).toHaveBeenCalledTimes(1)
 expect(readPending<{operation:string}>(pendingSlot(transport,'task:1'))?.operation).toBe('poll-op')
})

it('read-only без csrf загружает данные и не получает команды',async()=>{
 window.history.replaceState(null,'','/?project=a&task=1')
 const base=api();const original=base.get.getMockImplementation()!
 base.get.mockImplementation((path:string,signal?:AbortSignal)=>path==='session'?Promise.resolve({confirmation_origin:session.confirmation_origin}):original(path,signal))
 render(<Harness base={base}/>)
 await screen.findByText('a:1')
 expect((screen.getByRole('button',{name:'＋ Новая задача'}) as HTMLButtonElement).disabled).toBe(true)
 expect(base.post).not.toHaveBeenCalled()
})
