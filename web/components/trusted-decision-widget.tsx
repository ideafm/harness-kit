'use client'
import { useEffect,useRef,useState } from 'react'
import type { Control,Session } from '@/lib/contracts'
import { widgetUrl } from '@/lib/controller-links'
import { label } from '@/lib/task-presentation'
export function TrustedDecisionWidget({control,session,project,action,onRefresh,disabled=false}:{disabled?:boolean;control:Control;session?:Session;project?:string;action:string;onRefresh:()=>void}){
 const frame=useRef<HTMLIFrameElement>(null);const [height,setHeight]=useState(120);const [oversized,setOversized]=useState(false)
 const url=session?.csrf_token&&control.allowed_actions.includes(action)?widgetUrl(control.confirmation_widgets?.[action],session.confirmation_origin):undefined
 useEffect(()=>{
  setHeight(120);setOversized(false)
  if(!url||!project)return
  const receive=(event:MessageEvent)=>{
   if(event.origin!==session?.confirmation_origin||event.source!==frame.current?.contentWindow)return
   const data=event.data
   if(!data||typeof data!=='object')return
   if(data.type==='tw:widget-size'&&typeof data.height==='number'&&Number.isFinite(data.height)){setHeight(Math.max(40,Math.min(420,data.height)));setOversized(data.height>420)}
   if(data.type==='tw:decision'&&data.task===control.task.id&&data.project===project&&data.action===action&&data.status==='succeeded')onRefresh()
  }
  window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive)
 },[url,project,control.task.id,control.revision,action,session?.confirmation_origin,onRefresh])
 return url&&project?<div className="trusted-widget" inert={disabled} aria-disabled={disabled}><iframe ref={frame} key={`${project}:${control.task.id}:${control.revision}:${action}:${url}`} src={url} title={label(action)} sandbox="allow-forms allow-scripts allow-same-origin" style={{height,width:'100%',border:0}}/>{oversized&&<p role="status">Контроллер сообщил высоту формы больше 420 px. Проверьте доступность всех полей и подтверждения при прокрутке формы.</p>}</div>:<p className="muted">{label(action)} недоступно: нет доверенной формы или полномочий управления.</p>
}
