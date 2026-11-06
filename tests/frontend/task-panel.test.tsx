import { it,expect,vi } from 'vitest'
import { render,screen,fireEvent,within } from '@testing-library/react'
import { TaskPanel } from '@/components/task-table'
import { TaskCard } from '@/components/task-card'
import type { Transport } from '@/lib/contracts'
import { CreateTaskSheet } from '@/components/create-task-sheet'
import { DecisionList } from '@/components/decision-list'
it.each([undefined,'https://example.com/result','javascript:alert(1)'])('честно сообщает о недоступном preview %s',url=>{
 render(<TaskCard task={{id:1,state:'review',stage:'done',updated:1,request:'Запрос',artifacts:[],preview:url?{url}:undefined}} transport={{get:vi.fn(),post:vi.fn()}} onRefresh={vi.fn()}/> )
 expect(screen.getByText(/Предпросмотр недоступен/)).toBeTruthy()
 expect(screen.queryByRole('link',{name:'Посмотреть результат'})).toBeNull()
})
it('показывает preview до решений и безопасные причины ошибок',()=>{
 const view=render(<TaskCard task={{id:1,state:'review',stage:'done',updated:1,request:'Запрос',artifacts:[],preview:{url:'http://127.0.0.1:8080/'}}} transport={{get:vi.fn(),post:vi.fn()}} onRefresh={vi.fn()}/> )
 expect(screen.getByRole('link',{name:'Посмотреть результат'}).getAttribute('href')).toBe('http://127.0.0.1:8080/')
 expect(screen.getByText(/Принять — создать коммит/)).toBeTruthy()
 view.rerender(<TaskCard task={{id:1,state:'accepted',stage:'done',updated:1,request:'Запрос',artifacts:[],integration_error:'<script>ошибка</script>',commit_error:'Ошибка коммита'}} transport={{get:vi.fn(),post:vi.fn()}} onRefresh={vi.fn()}/> )
 expect(screen.getByText('<script>ошибка</script>')).toBeTruthy()
 expect(screen.getByText('Ошибка коммита')).toBeTruthy()
 expect(view.container.querySelector('script')).toBeNull()
 expect(screen.queryByText('Подробности применения')).toBeNull()
})
it('раскрывает короткий коммит и ветку по запросу',()=>{
 render(<TaskCard task={{id:1,state:'accepted',stage:'done',updated:1,request:'Запрос',artifacts:[],integration:{source_commit:'source',commit:'1234567890',branch:'main'}}} transport={{get:vi.fn(),post:vi.fn()}} onRefresh={vi.fn()}/> )
 expect(screen.getByText('Подробности применения').closest('details')?.open).toBe(false)
 fireEvent.click(screen.getByText('Подробности применения'))
 expect(screen.getByText('Подробности применения').closest('details')?.open).toBe(true)
 expect(screen.getByText('Коммит: 12345678')).toBeTruthy()
 expect(screen.getByText('Ветка: main')).toBeTruthy()
})
it('показывает фактическую сводку и причину в карточке, не придумывает рекомендации',()=>{
 const task={id:84,state:'blocked',stage:'implement',updated:1,request:'Исходный запрос',artifacts:[],implementation_summary:'Проверки успешны, результат ожидает решения.',reason:'Исчерпаны попытки'}
 render(<TaskCard task={task} transport={{get:vi.fn(),post:vi.fn()} as Transport} onRefresh={vi.fn()}/> )
 expect(screen.getByText(task.implementation_summary)).toBeTruthy()
 expect(screen.getByText(task.implementation_summary).closest('details')?.open).toBe(false)
 fireEvent.click(screen.getByText('Подробности результата'))
 expect(screen.getByText(task.implementation_summary).closest('details')?.open).toBe(true)
 expect(screen.getByText(task.reason)).toBeTruthy()
 expect(screen.getByText(/Конкретные рекомендации для человеческой проверки не предоставлены/)).toBeTruthy()
 expect(screen.getByRole('tab',{name:'Проверки'})).toBeTruthy()
})
it('обозначает отсутствие сводки и причины, сохраняя конкретный вопрос',()=>{
 const task={id:85,state:'waiting',stage:'plan',updated:1,request:'Запрос',artifacts:[],question:'Какой формат результата нужен?'}
 render(<TaskCard task={task} transport={{get:vi.fn(),post:vi.fn()} as Transport} onRefresh={vi.fn()}/> )
 expect(screen.getByText('Сводка результата не предоставлена.')).toBeTruthy()
 expect(screen.getByText('Не предоставлена контроллером.')).toBeTruthy()
 expect(screen.getByText(task.question)).toBeTruthy()
 expect(screen.queryByText(/Конкретные рекомендации для человеческой проверки не предоставлены/)).toBeNull()
})
it('включает ожидание вопроса и ревью в решения, исключая остальные состояния',()=>{
 const states=['waiting','review','awaiting_approval','running','accepted','rejected','queued','paused','blocked','rate_limited','waiting']
 const tasks=states.map((state,index)=>({id:index+1,state,stage:'done',updated:1,request:'Запрос',artifacts:[],question:index===0?'Уточните запрос':undefined}))
 const onSelect=vi.fn();render(<DecisionList tasks={tasks} onSelect={onSelect}/> )
 const buttons=screen.getAllByRole('button')
 expect(buttons).toHaveLength(3)
 fireEvent.click(buttons[0]);fireEvent.click(buttons[1]);fireEvent.click(buttons[2])
 expect(onSelect.mock.calls).toEqual([[1],[2],[3]])
})
it('выбирает созданную задачу из ответа 201 без ожидания операции',async()=>{const onCreated=vi.fn();const get=vi.fn();const post=vi.fn().mockResolvedValue({task:{id:42},revision:'r1'});render(<CreateTaskSheet transport={{get,post} as Transport} session={{csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}} enabled onCreated={onCreated}/>);fireEvent.click(screen.getByText('＋ Новая задача'));fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Новая задача'}});fireEvent.click(screen.getByText('Создать задачу'));await vi.waitFor(()=>expect(onCreated).toHaveBeenCalledWith(42));expect(post).toHaveBeenCalledWith('tasks',{request:'Новая задача',approval_mode:'approve-plan'},expect.any(String),'csrf');expect(get).not.toHaveBeenCalled()})
it('показывает реальное пустое состояние',async()=>{const get=vi.fn().mockImplementation(async(path:string)=>{if(path==='projects')return {items:[{id:'main',name:'Проект'}],default_project_id:'main',connect_url:'http://127.0.0.1:47832/connect'};if(path==='projects/main/status')return {project:'Проект',tasks:[],worker:{running:false}};if(path==='projects/main/capabilities')return {actions:[],events:true,apply:false};return {csrf_token:'csrf'}});render(<TaskPanel transport={{get,post:vi.fn()} as Transport}/>);expect(document.body.contains(await screen.findByText('Задач пока нет.'))).toBe(true);expect((screen.getByText('＋ Новая задача') as HTMLButtonElement).disabled).toBe(true)})

import { ApiError } from '@/lib/http-transport'

it.each([400,422])('позволяет исправить запрос после окончательного %s',async(status)=>{
 const post=vi.fn().mockRejectedValueOnce(new ApiError('invalid','Исправьте запрос',status)).mockResolvedValue({task:{id:43},revision:'r2'})
 const onCreated=vi.fn()
 render(<CreateTaskSheet transport={{get:vi.fn(),post} as Transport} session={{csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}} enabled onCreated={onCreated}/>)
 fireEvent.click(screen.getByText('＋ Новая задача'))
 fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Первый запрос'}})
 fireEvent.click(screen.getByText('Создать задачу'));await screen.findByText('Исправьте запрос')
 expect(window.sessionStorage.getItem('tw-web:pending:create')).toBeNull()
 fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Исправленный запрос'}})
 fireEvent.click(screen.getByText('Создать задачу'))
 await vi.waitFor(()=>expect(onCreated).toHaveBeenCalledWith(43))
 expect(post.mock.calls[1][1]).toEqual({request:'Исправленный запрос',approval_mode:'approve-plan'})
 expect(post.mock.calls[1][2]).not.toBe(post.mock.calls[0][2])
})
it('восстанавливает создание auto после reload с прежними данными и ключом',async()=>{
 const post=vi.fn().mockRejectedValueOnce(new TypeError('Неизвестный исход')).mockResolvedValue({task:{id:44},revision:'r1'})
 const onCreated=vi.fn()
 const props={transport:{get:vi.fn(),post} as Transport,session:{csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'},enabled:true,onCreated}
 const first=render(<CreateTaskSheet {...props}/>)
 fireEvent.click(screen.getByText('＋ Новая задача'))
 fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Сохранённый запрос'}})
 fireEvent.change(screen.getByLabelText('Режим утверждения'),{target:{value:'auto'}})
 fireEvent.click(screen.getByText('Создать задачу'));await screen.findByText('Неизвестный исход')
 const stored=window.sessionStorage.getItem('tw-web:pending:create')
 if(stored===null)throw Error('Создание не сохранено')
 first.unmount()
 window.sessionStorage.clear();window.sessionStorage.setItem('tw-web:pending:create',stored)
 render(<CreateTaskSheet {...props}/>)
 fireEvent.click(screen.getByText('＋ Новая задача'))
 expect((screen.getByLabelText('Запрос') as HTMLTextAreaElement).value).toBe('Сохранённый запрос')
 expect((screen.getByLabelText('Режим утверждения') as HTMLSelectElement).value).toBe('auto')
 fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Другой запрос'}})
 fireEvent.click(screen.getByText('Создать задачу'))
 await screen.findByText('Предыдущий запрос имеет неопределённый результат. Верните прежние данные для повтора.')
 expect(post).toHaveBeenCalledTimes(1)
 fireEvent.change(screen.getByLabelText('Запрос'),{target:{value:'Сохранённый запрос'}})
 fireEvent.click(screen.getByText('Создать задачу'))
 await vi.waitFor(()=>expect(onCreated).toHaveBeenCalledWith(44))
 expect(post.mock.calls[1]).toEqual(post.mock.calls[0])
 expect(window.sessionStorage.getItem('tw-web:pending:create')).toBeNull()
})

import userEvent from '@testing-library/user-event'
import { TaskTabs } from '@/components/task-tabs'
import { TaskActions } from '@/components/task-actions'
import { SidebarProvider,SidebarTrigger } from '@/components/ui/sidebar'
import { ProjectSidebar } from '@/components/project-sidebar'

it('переключает материалы с клавиатуры и показывает полный request безопасным текстом',async()=>{
 const user=userEvent.setup()
 render(<TaskTabs task={{id:1,state:'review',stage:'done',updated:1,request:'Полный запрос\n<script>текст</script>',artifacts:[]}} transport={{get:vi.fn(),post:vi.fn()} as Transport} events={false}/>)
 const history=screen.getByRole('tab',{name:'История'})
 await user.tab();expect(document.activeElement).toBe(history)
 await user.keyboard('{ArrowRight}')
 const request=screen.getByRole('tab',{name:'Исходная задача'})
 expect(document.activeElement).toBe(request)
 expect(request.getAttribute('aria-selected')).toBe('true')
 const panel=screen.getByRole('tabpanel')
 expect(panel.textContent).toBe('Полный запрос\n<script>текст</script>')
 expect(panel.querySelector('script')).toBeNull()
 await user.keyboard('{ArrowRight}')
 expect(screen.getByRole('tab',{name:'План'}).getAttribute('aria-selected')).toBe('true')
 expect(screen.getAllByText('Документ ещё не предоставлен.')).toHaveLength(2)
})
it('открывает мобильный sidebar с клавиатуры, закрывает Escape и возвращает фокус',async()=>{
 vi.stubGlobal('innerWidth',390)
 vi.spyOn(window,'matchMedia').mockImplementation(query=>({matches:true,media:query,onchange:null,addListener:vi.fn(),removeListener:vi.fn(),addEventListener:vi.fn(),removeEventListener:vi.fn(),dispatchEvent:vi.fn()}))
 const user=userEvent.setup()
 render(<SidebarProvider><SidebarTrigger/><ProjectSidebar project="Реальный проект" count={0} running={false}/></SidebarProvider>)
 const trigger=screen.getByRole('button',{name:'Открыть меню проектов'})
 await user.tab()
 expect(document.activeElement).toBe(trigger)
 await user.keyboard('{Enter}')
 const dialog=await screen.findByRole('dialog',{name:'Проекты'})
 expect(dialog.getAttribute('data-mobile')).toBe('true')
 expect(screen.getByText('Реальный проект')).toBeTruthy()
 await user.keyboard('{Escape}')
 await vi.waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull())
 await vi.waitFor(()=>expect(document.activeElement).toBe(trigger))
})
it('без trusted widget не предлагает обход через отдельную страницу',()=>{
 const post=vi.fn()
 render(<TaskActions control={{task:{id:1,state:'awaiting_approval',stage:'planning',updated:1,request:'Запрос',artifacts:[]},revision:'r1',allowed_actions:['approve_plan'],plan:{version:7,digest:'digest7'},result:null,confirmation_urls:{approve_plan:'http://127.0.0.1:47832/confirm?id=1'}}} transport={{get:vi.fn(),post} as Transport} session={{csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}} onRefresh={vi.fn()}/>)
 expect(screen.getByText(/Утвердить план недоступно/)).toBeTruthy()
 expect(screen.queryByRole('link')).toBeNull()
 expect(post).not.toHaveBeenCalled()
})

it('поиск, фильтр и страницы не меняют выбранную задачу в URL',async()=>{
 const tasks=Array.from({length:7},(_,index)=>({id:index+1,state:index===6?'backlog':'running',stage:'implement',updated:1,request:'Задача '+(index+1),artifacts:[]}))
 window.history.replaceState(null,'','/?project=main&task=1')
 const get=vi.fn().mockImplementation(async(path:string)=>{
  if(path==='projects')return {items:[{id:'main',name:'Проект'}],default_project_id:'main',connect_url:''}
  if(path==='session')return {csrf_token:'csrf'}
  if(path.endsWith('/status'))return {project:'main',tasks,worker:{running:false}}
  if(path.endsWith('/capabilities'))return {project_id:'main',actions:[],events:false,apply:false}
  return {task:tasks[0],revision:'r1',allowed_actions:[],plan:null,result:null,confirmation_urls:{}}
 })
 render(<TaskPanel transport={{get,post:vi.fn()} as Transport}/>)
 await screen.findByRole('button',{name:'#1 Задача 1'})
 fireEvent.click(screen.getByRole('button',{name:'Далее'}))
 expect(screen.getByRole('button',{name:'#7 Задача 7'})).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'Обновить'}))
 await vi.waitFor(()=>expect(get.mock.calls.filter(([path])=>path.endsWith('/status')).length).toBeGreaterThan(1))
 expect(screen.getByText('2 / 2')).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'Бэклог'}))
 expect(screen.getByText('1 / 1')).toBeTruthy()
 expect(screen.queryByRole('button',{name:'#6 Задача 6'})).toBeNull()
 expect(new URLSearchParams(window.location.search).get('task')).toBe('1')
 fireEvent.change(screen.getByLabelText('Поиск задач'),{target:{value:'Несуществующая'}})
 expect(screen.getByText('Нет результатов поиска.')).toBeTruthy()
 window.history.replaceState(null,'','/')
})

it('сохраняет ошибки, повтор и усечение материалов во вкладках',async()=>{
 const get=vi.fn().mockRejectedValueOnce(Error('Не удалось получить проверки')).mockResolvedValue({text:'<script>вывод</script>',truncated:true})
 const user=userEvent.setup()
 const view=render(<TaskTabs task={{id:9,state:'review',stage:'done',updated:1,request:'Запрос',artifacts:['checks']}} transport={{get,post:vi.fn()} as Transport} events={false}/>)
 await user.click(screen.getByRole('tab',{name:'Проверки'}))
 expect((await screen.findByRole('alert')).textContent).toContain('Не удалось получить проверки')
 await user.click(screen.getByRole('button',{name:'Повторить'}))
 expect(await screen.findByText('<script>вывод</script>')).toBeTruthy()
 expect(screen.getByText('Артефакт усечён контроллером.')).toBeTruthy()
 expect(view.container.querySelector('script')).toBeNull()
 expect(get).toHaveBeenCalledTimes(2)
})
it('не показывает запоздалый материал после выбора другой задачи',async()=>{
 let resolve:(value:{text:string;truncated:boolean})=>void=()=>{}
 const get=vi.fn().mockImplementation(()=>new Promise(done=>{resolve=done}))
 const props={transport:{get,post:vi.fn()} as Transport,events:false}
 const view=render(<TaskTabs {...props} task={{id:1,state:'running',stage:'check',updated:1,request:'Первый запрос',artifacts:['checks']}}/>)
 await userEvent.setup().click(screen.getByRole('tab',{name:'Проверки'}))
 await vi.waitFor(()=>expect(get).toHaveBeenCalledTimes(1))
 view.rerender(<TaskTabs {...props} task={{id:2,state:'running',stage:'implement',updated:2,request:'Второй запрос',artifacts:[]}}/>)
 resolve({text:'Поздний вывод первой задачи',truncated:false})
 await vi.waitFor(()=>expect(screen.getByRole('tab',{name:'История'}).getAttribute('aria-selected')).toBe('true'))
 expect(screen.queryByText('Поздний вывод первой задачи')).toBeNull()
})

it.each(['checks','review'])('открывает %s при ожидании приёмки и сохраняет историю в раскрытии',async(name)=>{
 const get=vi.fn().mockImplementation(async(path:string)=>path.includes('/events?')?{items:[],next_cursor:'0',has_more:false}:{text:'Фактический отчёт',truncated:false})
 render(<TaskTabs task={{id:1,state:'review',stage:'done',updated:1,request:'Запрос',artifacts:[name]}} transport={{get,post:vi.fn()} as Transport} events/>)
 expect(screen.getByRole('tab',{name:name==='checks'?'Проверки':'Ревью'}).getAttribute('aria-selected')).toBe('true')
 await userEvent.setup().click(screen.getByRole('tab',{name:'История'}))
 const disclosure=screen.getByText('Полная история событий').closest('details')
 expect(disclosure?.open).toBe(false)
 fireEvent.click(screen.getByText('Полная история событий'))
 expect(disclosure?.open).toBe(true)
})

it('открывает страницу выбранной по URL задачи и убирает Markdown только из заголовка',async()=>{
 const tasks=Array.from({length:7},(_,index)=>({id:index+1,state:'running',stage:'implement',updated:1,request:'# Задача '+(index+1)+'\n<script>текст</script>',artifacts:[]}))
 window.history.replaceState(null,'','/?project=main&task=7')
 const get=vi.fn().mockImplementation(async(path:string)=>{
  if(path==='projects')return {items:[{id:'main',name:'Проект'}],default_project_id:'main',connect_url:''}
  if(path==='session')return {csrf_token:'csrf'}
  if(path.endsWith('/status'))return {project:'main',tasks,worker:{running:false}}
  if(path.endsWith('/capabilities'))return {actions:[],events:false,apply:false}
  return {task:tasks[6],revision:'r1',allowed_actions:[],plan:null,result:null,confirmation_urls:{}}
 })
 render(<TaskPanel transport={{get,post:vi.fn()} as Transport}/>)
 await screen.findByRole('button',{name:'#7 Задача 7'})
 expect(screen.getByText('2 / 2')).toBeTruthy()
 expect(screen.getByRole('heading',{name:'Задача 7'})).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'Назад'}))
 fireEvent.click(screen.getByRole('button',{name:'Обновить'}))
 await vi.waitFor(()=>expect(get.mock.calls.filter(([path])=>path.endsWith('/status')).length).toBeGreaterThan(1))
 expect(screen.getByText('1 / 2')).toBeTruthy()
 await userEvent.setup().click(screen.getByRole('tab',{name:'Исходная задача'}))
 expect(screen.getByRole('tabpanel').textContent).toBe(tasks[6].request)
 expect(document.querySelector('script')).toBeNull()
 window.history.replaceState(null,'','/')
})


it.each(['<script>Лимит исчерпан</script>','',undefined])('показывает ограничение и безопасную причину %s',reason=>{
 const task={id:17,state:'rate_limited',stage:'implement',updated:1,request:'Запрос',artifacts:[],reason}
 const view=render(<TaskCard task={task} transport={{get:vi.fn(),post:vi.fn()}} onRefresh={vi.fn()}/>)
 const notice=screen.getByRole('region',{name:'Ограничение задачи'})
 expect(within(notice).getByRole('heading',{name:'Ожидает снятия лимита'})).toBeTruthy()
 expect(within(notice).getByText(reason||'Подробности ограничения не предоставлены.')).toBeTruthy()
 expect(screen.getByText('Контроллер ожидает снятия ограничения. Срок восстановления не предоставлен.')).toBeTruthy()
 expect(view.container.querySelector('script')).toBeNull()
 expect(screen.queryByRole('button',{name:'Продолжить'})).toBeNull()
})

it('сохраняет вопрос контроллера при ограничении',()=>{
 render(<TaskCard task={{id:17,state:'rate_limited',stage:'check',updated:1,request:'Запрос',artifacts:[],question:'Уточните режим работы'}} transport={{get:vi.fn(),post:vi.fn()}} onRefresh={vi.fn()}/>)
 expect(screen.getByText('Уточните режим работы')).toBeTruthy()
 expect(screen.queryByText('Вопроса к вам нет.')).toBeNull()
})

it('различает отсутствие полномочий и пустой список действий',()=>{
 const task={id:18,state:'awaiting_approval',stage:'plan',updated:1,request:'Запрос',artifacts:[]}
 const props={task,transport:{get:vi.fn(),post:vi.fn()},onRefresh:vi.fn()}
 const view=render(<TaskCard {...props}/>)
 let actions=screen.getByRole('region',{name:'Доступные действия'})
 expect(within(actions).getByText(/Управление недоступно/)).toBeTruthy()
 expect(within(actions).queryByRole('button')).toBeNull()
 expect(screen.queryByText('Откройте план и используйте доступные действия.')).toBeNull()
 view.rerender(<TaskCard {...props} control={{task,revision:'r1',allowed_actions:[],plan:null,result:null,confirmation_urls:{}}}/>)
 actions=screen.getByRole('region',{name:'Доступные действия'})
 expect(within(actions).getByText('Сейчас нет доступных действий.')).toBeTruthy()
 expect(within(actions).queryByRole('button')).toBeNull()
})

it('показывает только фактически разрешённые действия в одном разделе',()=>{
 const task={id:19,state:'paused',stage:'implement',updated:1,request:'Запрос',artifacts:[]}
 const post=vi.fn()
 render(<TaskCard task={task} control={{task,revision:'r1',allowed_actions:['resume'],plan:null,result:null,confirmation_urls:{}}} session={{csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}} transport={{get:vi.fn(),post}} onRefresh={vi.fn()}/>)
 const actions=screen.getByRole('region',{name:'Доступные действия'})
 expect(within(actions).getAllByRole('button')).toHaveLength(1)
 expect((within(actions).getByRole('button',{name:'Продолжить'}) as HTMLButtonElement).disabled).toBe(false)
 expect(screen.queryByRole('button',{name:'Запустить'})).toBeNull()
 expect(screen.queryByRole('button',{name:'Пауза'})).toBeNull()
 expect(post).not.toHaveBeenCalled()
})
