'use client'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Button } from './ui/button'

export function DecisionDialog({title,children,disabled=false}:{title:string;children:ReactNode;disabled?:boolean}){
 const [open,setOpen]=useState(false)
 const dialog=useRef<HTMLDialogElement>(null)
 const titleId=useId()
 useEffect(()=>{
  const node=dialog.current
  if(!node)return
  if(open&&!node.open)node.showModal()
  if(!open&&node.open)node.close()
 },[open])
 useEffect(()=>{const node=dialog.current;return()=>{if(node?.open)node.close()}},[])
 return <>
  <Button variant="outline" disabled={disabled} onClick={()=>setOpen(true)}>{title}</Button>
  <dialog ref={dialog} className="details-dialog decision-dialog" aria-labelledby={titleId} style={{display:open?'flex':'none'}}
   onCancel={event=>{event.preventDefault();setOpen(false)}} onClose={()=>setOpen(false)}>
   <header><h2 id={titleId}>{title}</h2><button type="button" aria-label="Закрыть" onClick={()=>setOpen(false)}>×</button></header>
   <div className="dialog-body">{children}</div>
  </dialog>
 </>
}
