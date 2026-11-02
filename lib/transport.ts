export type { Transport } from './contracts'
export { httpTransport } from './http-transport'
import type { Transport } from './contracts'

export function projectTransport(base:Transport,id:string):Transport {
 const prefix=`projects/${encodeURIComponent(id)}/`
 const validate=()=>{if(id==='.'||id==='..')throw Error('Идентификатор проекта нельзя безопасно передать в URL')}
 return {projectId:id,get:async<T>(path:string,signal?:AbortSignal)=>{if(path==='session')return base.get<T>(path,signal);validate();return base.get<T>(prefix+path,signal)},post:async<T>(path:string,body:unknown,key:string,csrf:string,revision?:string)=>{validate();return base.post<T>(prefix+path,body,key,csrf,revision)}}
}
export const pendingSlot=(transport:Transport,slot:string)=>transport.projectId===undefined?slot:`project:${encodeURIComponent(transport.projectId)}:${slot}`

export type PendingCommand = {action:string;taskId:number;body:Record<string,unknown>;revision:string;key:string;operation?:string}
export type PendingCreation = {body:{request:string;approval_mode:string};key:string}

export function readPending<T>(slot:string):T|undefined {
 if(typeof window==='undefined')return undefined
 const value=window.sessionStorage.getItem(`tw-web:pending:${slot}`)
 return value===null?undefined:JSON.parse(value) as T
}

export function writePending(slot:string,value:unknown|undefined){
 if(value===undefined)window.sessionStorage.removeItem(`tw-web:pending:${slot}`)
 else window.sessionStorage.setItem(`tw-web:pending:${slot}`,JSON.stringify(value))
}
