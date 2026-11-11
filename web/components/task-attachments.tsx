'use client'
import { useEffect,useRef,useState } from 'react'
import { Paperclip,X,FileImage,FileText } from 'lucide-react'
import type { Attachment,Transport } from '@/lib/contracts'

export const attachmentAccept='.png,.jpg,.jpeg,.webp,.txt,.md,.log,.json,.csv'
function readFile(file:File):Promise<string>{return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(Error('Не удалось прочитать файл'));reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.readAsDataURL(file)})}
export function AttachmentPicker({files,onChange,onBusy,transport,csrf,disabled}:{files:Attachment[];onChange:(files:Attachment[])=>void;onBusy:(busy:boolean)=>void;transport:Transport;csrf?:string;disabled:boolean}){
 const input=useRef<HTMLInputElement>(null)
 const lock=useRef(false)
 const [error,setError]=useState('')
 const [uploading,setUploading]=useState(false)
 async function add(selected:File[]){
  if(disabled||!csrf||lock.current||!selected.length)return
  if(files.length+selected.length>5){setError('Можно добавить до 5 файлов');return}
  if(files.reduce((sum,file)=>sum+file.size,0)+selected.reduce((sum,file)=>sum+file.size,0)>8*1024*1024){setError('Общий размер файлов — до 8 МиБ');return}
  lock.current=true;setUploading(true);onBusy(true);setError('')
  const updated=[...files]
  try{for(const file of selected){
   if(file.size>2*1024*1024)throw Error(`«${file.name}» превышает 2 МиБ`)
   if(!/\.(png|jpe?g|webp|txt|md|log|json|csv)$/i.test(file.name))throw Error(`Формат «${file.name}» не поддерживается`)
   const content=await readFile(file)
   const uploaded=await transport.post<Attachment>('attachments',{name:file.name,content},crypto.randomUUID(),csrf)
   if(!uploaded||!/^[a-f0-9]{64}$/.test(uploaded.id)||typeof uploaded.name!=='string'||typeof uploaded.size!=='number')throw Error('Некорректный ответ загрузки')
   if(!updated.some(item=>item.id===uploaded.id))updated.push(uploaded)
   onChange([...updated])
  }}catch(e){setError(e instanceof Error?e.message:'Ошибка загрузки')}finally{lock.current=false;setUploading(false);onBusy(false);if(input.current)input.current.value=''}
 }
 useEffect(()=>{const paste=(event:ClipboardEvent)=>{const selected=Array.from(event.clipboardData?.files??[]);if(selected.length&&!disabled){event.preventDefault();void add(selected)}};document.addEventListener('paste',paste);return()=>document.removeEventListener('paste',paste)},[files,disabled,csrf,transport])
 return <section aria-label="Файлы к задаче" onDragOver={event=>event.preventDefault()} onDrop={event=>{event.preventDefault();void add(Array.from(event.dataTransfer.files))}} className="space-y-2 rounded-xl border border-dashed border-zinc-300 p-3 dark:border-zinc-700">
 <div className="flex flex-wrap items-center justify-between gap-2"><span className="flex items-center gap-2 text-xs font-semibold"><Paperclip className="size-4"/>Файлы к задаче</span><button type="button" className="text-xs text-blue-600 disabled:opacity-50" disabled={disabled||uploading} onClick={()=>input.current?.click()}>{uploading?'Загружаем…':'Добавить файлы'}</button></div>
 <input ref={input} type="file" multiple accept={attachmentAccept} aria-label="Добавить вложения" className="sr-only" disabled={disabled||uploading} onChange={event=>void add(Array.from(event.target.files??[]))}/>
 <p className="text-[11px] text-zinc-500">Перетащите файлы или вставьте скриншот сюда. PNG, JPEG, WebP, TXT, MD, LOG, JSON, CSV. До 5 файлов, 2 МиБ каждый; текст — до 100 КБ. Изображения доступны Codex и Gemini CLI.</p>
 {files.map(file=><div key={file.id} className="flex items-center gap-2 rounded-lg bg-zinc-50 px-2 py-1.5 text-xs dark:bg-zinc-800">{file.mime.startsWith('image/')?<FileImage className="size-4 shrink-0 text-blue-500"/>:<FileText className="size-4 shrink-0 text-zinc-500"/>}<span className="min-w-0 flex-1 truncate">{file.name}</span><span className="text-zinc-500">{Math.ceil(file.size/1024)} КБ</span><button type="button" aria-label={`Убрать ${file.name}`} disabled={disabled||uploading} onClick={()=>onChange(files.filter(item=>item.id!==file.id))}><X className="size-3.5"/></button></div>)}
 {error&&<p role="alert" className="text-xs text-rose-600">{error}</p>}
 </section>
}
export function TaskAttachments({files,task,transport}:{files?:Attachment[];task:number;transport:Transport}){
 if(!files?.length)return null
 const prefix=transport.projectId?`projects/${encodeURIComponent(transport.projectId)}/`:''
 return <section aria-label="Вложения задачи" className="space-y-2"><h3 className="flex items-center gap-2 text-xs font-semibold"><Paperclip className="size-4"/>Вложения ({files.length})</h3><div className="flex flex-wrap gap-2">{files.map(file=><a key={file.id} href={`/api/v1/${prefix}tasks/${task}/attachments/${file.id}`} target="_blank" rel="noopener noreferrer" className="inline-flex max-w-full items-center gap-2 rounded-lg border px-3 py-2 text-xs" title="Открыть вложение в новой вкладке">{file.mime.startsWith('image/')?<FileImage className="size-4 shrink-0"/>:<FileText className="size-4 shrink-0"/>}<span className="truncate">{file.name}</span><span className="shrink-0 text-zinc-500">{Math.ceil(file.size/1024)} КБ</span></a>)}</div></section>
}
