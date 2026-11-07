import { it,expect,vi } from 'vitest'
import { fireEvent,render,screen,cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { WorkerPanel } from '@/components/worker-panel'
afterEach(cleanup)
it('для ожидающего worker использует выбранную задачу на паузе и позволяет ручное копирование',async()=>{
 const task={id:3,state:'paused',stage:'implement',updated:1,request:'Пауза',artifacts:[],observation:{task_id:3,terminal_command:'tw --project a watch TASK-003',mode:'events' as const,interactive:false as const}}
 Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:vi.fn().mockRejectedValue(Error('denied'))}})
 render(<WorkerPanel project="Альфа" selectedTask={task} onSelect={vi.fn()} status={{project:'a',tasks:[task],worker:{running:true}}}/>)
 fireEvent.click(screen.getByRole('button',{name:'Worker работает'}))
 expect(screen.getByText('Ожидает задачи')).toBeTruthy()
 expect(screen.getByText(/Время старта, последнее действие, результаты проверок, причины ожидания и история событий процесса не предоставлены/)).toBeTruthy()
 expect(screen.getByText(/Live-канал событий процесса и сохраняемые сообщения агенту пока недоступны/)).toBeTruthy()
 expect(screen.getByText('Наблюдение за задачей #3')).toBeTruthy()
 fireEvent.click(screen.getByText('Копировать команду'))
 await screen.findByText('Выделите и скопируйте команду вручную')
 const field=screen.getByRole('textbox') as HTMLTextAreaElement
 fireEvent.focus(field)
 expect(field.readOnly).toBe(true)
 expect(field.selectionEnd).toBe(task.observation.terminal_command.length)
})
it('активная задача имеет приоритет над выбранной',()=>{
 const selected={id:3,state:'paused',stage:'implement',updated:1,request:'Пауза',artifacts:[],observation:{task_id:3,terminal_command:'selected',mode:'events' as const,interactive:false as const}}
 const active={...selected,id:2,observation:{...selected.observation,task_id:2,terminal_command:'active'}}
 render(<WorkerPanel project="Альфа" selectedTask={selected} onSelect={vi.fn()} status={{project:'a',tasks:[selected,active],worker:{running:true,task_id:2}}}/>)
 fireEvent.click(screen.getByRole('button',{name:'Worker работает'}))
 expect(screen.getByDisplayValue('active')).toBeTruthy()
 expect(screen.queryByDisplayValue('selected')).toBeNull()
})
it('использует активную задачу и копирует готовую команду без изменений с ручным fallback',async()=>{
 const command="tw --project 'Альфа' watch TASK-002"
 Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:vi.fn().mockRejectedValue(Error('denied'))}})
 const select=vi.fn()
 render(<WorkerPanel project="Альфа" onSelect={select} status={{project:'a',tasks:[{id:2,stage:'implement',state:'running',updated:1,request:'Активная',artifacts:[]}],worker:{running:true,task_id:2,observation:{task_id:2,terminal_command:command,mode:'events',interactive:false}}}}/>)
 fireEvent.click(screen.getByRole('button',{name:'Worker работает'}))
 fireEvent.click(screen.getByText('Копировать команду'))
 await screen.findByText('Выделите и скопируйте команду вручную')
 expect(navigator.clipboard.writeText).toHaveBeenCalledWith(command)
 expect((screen.getByLabelText('Наблюдение за этапом и событиями · без чата') as HTMLTextAreaElement).value).toBe(command)
 fireEvent.click(screen.getByText('Открыть задачу #2'));expect(select).toHaveBeenCalledWith(2)
})
it('не показывает observation другой задачи',()=>{
 render(<WorkerPanel project="Бета" onSelect={vi.fn()} status={{project:'b',tasks:[],worker:{running:true,task_id:2,observation:{task_id:1,terminal_command:'Чужая команда',mode:'events',interactive:false}}}}/>)
 fireEvent.click(screen.getByRole('button',{name:'Worker работает'}))
 expect(screen.queryByDisplayValue('Чужая команда')).toBeNull()
 expect(screen.getByText('Команда наблюдения не предоставлена.')).toBeTruthy()
})
