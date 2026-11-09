'use client'
import { useEffect, useRef } from 'react'
import type { Session } from '@/lib/contracts'

export function AutoApplySetting({policy,project,session,disabled,onRefresh}:{policy?:{enabled:boolean;confirmation_url:string};project?:string;session?:Session;disabled:boolean;onRefresh:()=>void}){
 const frame=useRef<HTMLIFrameElement>(null)
 let url:URL|undefined
 try{
  const candidate=new URL(policy?.confirmation_url||'')
  if(candidate.origin==='http://127.0.0.1:47832'&&candidate.pathname==='/policy/embed'&&!candidate.username&&!candidate.password&&!candidate.hash&&candidate.searchParams.get('project')===project)url=candidate
 }catch{}
 const source=session?.csrf_token?url?.href:undefined
 useEffect(()=>{
  const receive=(event:MessageEvent)=>{
   if(event.origin!==session?.confirmation_origin||event.source!==frame.current?.contentWindow)return
   if(event.data?.type==='tw:policy'&&event.data.project===project)onRefresh()
  }
  window.addEventListener('message',receive)
  return()=>window.removeEventListener('message',receive)
 },[project,session?.confirmation_origin,onRefresh])
 if(!policy||!source)return null
 return <details className="px-6 py-2 border-b text-xs bg-white shrink-0">
  <summary className="cursor-pointer">Автоматически применять результаты: {policy.enabled?'включено':'выключено'}</summary>
  <div inert={disabled} aria-disabled={disabled}>
   <iframe ref={frame} key={project} src={source} title="Настройка автоматического применения" sandbox="allow-forms allow-scripts allow-same-origin" className="w-full max-w-2xl border-0" style={{height:380}}/>
  </div>
 </details>
}
