import { it,expect,vi } from 'vitest'
import { render,screen,fireEvent } from '@testing-library/react'
import { TaskPanel } from '@/components/task-table'
import type { Transport } from '@/lib/contracts'
import { CreateTaskSheet } from '@/components/create-task-sheet'
import { DecisionList } from '@/components/decision-list'
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
it('показывает реальное пустое состояние',async()=>{const get=vi.fn().mockImplementation(async(path:string)=>{if(path==='projects')return {items:[{id:'main',name:'Проект'}],default_project_id:'main',connect_url:'http://127.0.0.1:47832/connect'};if(path==='projects/main/status')return {project:'Проект',tasks:[],worker:{running:false}};if(path==='projects/main/capabilities')return {actions:[],events:true,apply:false};return {csrf_token:'csrf'}});render(<TaskPanel transport={{get,post:vi.fn()} as Transport}/>);expect(document.body.contains(await screen.findByText('Задач пока нет. Создайте первую задачу.'))).toBe(true);expect((screen.getByText('＋ Новая задача') as HTMLButtonElement).disabled).toBe(true)})

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

it('переключает все вкладки с клавиатуры и сохраняет доступные названия',async()=>{
 const user=userEvent.setup()
 render(<TaskTabs task={{id:1,state:'review',stage:'done',updated:1,request:'Запрос',artifacts:[]}} transport={{get:vi.fn(),post:vi.fn()} as Transport} events={false}/>)
 await user.tab()
 expect(document.activeElement).toBe(screen.getByRole('tab',{name:'Обзор'}))
 for(const name of ['Спецификация / план','Diff','Проверки','Ревью','События']){
  await user.keyboard('{ArrowRight}')
  await vi.waitFor(()=>expect(screen.getByRole('tab',{name} ).getAttribute('aria-selected')).toBe('true'))
  expect(document.activeElement).toBe(screen.getByRole('tab',{name}))
 }
 expect(screen.getByText('События недоступны.')).toBeTruthy()
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
it('диалог утверждения показывает точную версию и возвращает фокус после Escape',async()=>{
 const user=userEvent.setup()
 render(<TaskActions control={{task:{id:1,state:'awaiting_approval',stage:'planning',updated:1,request:'Запрос',artifacts:[],risk:'high',scope:'large'},revision:'r1',allowed_actions:['approve_plan'],plan:{version:7,digest:'digest7'},result:null,confirmation_urls:{approve_plan:'http://127.0.0.1:47832/confirm?id=1'}}} transport={{get:vi.fn(),post:vi.fn()} as Transport} session={{csrf_token:'csrf',confirmation_origin:'http://127.0.0.1:47832'}} onRefresh={vi.fn()}/>)
 const trigger=screen.getByRole('button',{name:'Утвердить план'})
 await user.tab();await user.keyboard('{Enter}')
 expect(await screen.findByRole('alertdialog')).toBeTruthy()
 expect(screen.getByText('Версия плана: 7 · Риск: high · Объём: large')).toBeTruthy()
 await user.keyboard('{Escape}')
 await vi.waitFor(()=>expect(screen.queryByRole('alertdialog')).toBeNull())
 await vi.waitFor(()=>expect(document.activeElement).toBe(trigger))
})
