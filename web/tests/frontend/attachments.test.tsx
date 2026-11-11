import {it,expect,vi} from 'vitest'
import {render,screen,fireEvent,act} from '@testing-library/react'
import {useState} from 'react'
import {AttachmentPicker,TaskAttachments} from '@/components/task-attachments'
import {ExecutionStatus} from '@/components/execution-status'
import type {Attachment,Task} from '@/lib/contracts'
const record:Attachment={id:'a'.repeat(64),name:'brief.md',mime:'text/plain',size:12,sha256:'b'.repeat(64)}
it('загружает файл в выбранный transport и позволяет убрать его',async()=>{
 const post=vi.fn().mockResolvedValue(record)
 function Picker(){const [files,setFiles]=useState<Attachment[]>([]);return <AttachmentPicker files={files} onChange={setFiles} onBusy={()=>{}} transport={{projectId:'project-a',get:vi.fn(),post}} csrf="csrf" disabled={false}/>}
 render(<Picker/> )
 fireEvent.change(screen.getByLabelText('Добавить вложения'),{target:{files:[new File(['requirements'],'brief.md',{type:'text/markdown'})]}})
 await screen.findByText('brief.md')
 expect(post).toHaveBeenCalledWith('attachments',{name:'brief.md',content:expect.any(String)},expect.any(String),'csrf')
 fireEvent.click(screen.getByRole('button',{name:'Убрать brief.md'}))
 expect(screen.queryByText('brief.md')).toBeNull()
})
it('не отправляет слишком большой файл',async()=>{
 const post=vi.fn()
 render(<AttachmentPicker files={[]} onChange={vi.fn()} onBusy={vi.fn()} transport={{get:vi.fn(),post}} csrf="csrf" disabled={false}/> )
 fireEvent.change(screen.getByLabelText('Добавить вложения'),{target:{files:[new File([new Uint8Array(2*1024*1024+1)],'big.png')]}})
 await screen.findByText(/превышает 2 МиБ/)
 expect(post).not.toHaveBeenCalled()
})
it('ссылка на вложение привязана к проекту и задаче',()=>{
 render(<TaskAttachments files={[record]} task={7} transport={{projectId:'abc',get:vi.fn(),post:vi.fn()}}/> )
 expect(screen.getByRole('link').getAttribute('href')).toBe('/api/v1/projects/abc/tasks/7/attachments/'+record.id)
})
it('показывает причины ожидания, попытку и следующий этап',()=>{
 const task:Task={id:1,state:'rate_limited',stage:'implement',request:'test',updated:1,artifacts:[],execution:{title:'Ожидаем восстановления лимита',detail:'Работа сохранена',next:'Автоматическое продолжение',attempt:2,started_at:null,elapsed_seconds:null,last_activity_at:100,retry_at:200,waiting:true}}
 render(<ExecutionStatus task={task}/> )
 expect(screen.getByText('Ожидаем восстановления лимита')).toBeTruthy()
 expect(screen.getByText(/Следующая попытка:/)).toBeTruthy()
 expect(screen.getByText(/Дальше: Автоматическое продолжение/)).toBeTruthy()
})
it('вставляет файл из буфера при открытой форме',async()=>{
 const post=vi.fn().mockResolvedValue(record)
 render(<AttachmentPicker files={[]} onChange={vi.fn()} onBusy={vi.fn()} transport={{get:vi.fn(),post}} csrf="csrf" disabled={false}/> )
 fireEvent.paste(document,{clipboardData:{files:[new File(['clipboard'],'brief.md')]}})
 await vi.waitFor(()=>expect(post).toHaveBeenCalledTimes(1))
})
