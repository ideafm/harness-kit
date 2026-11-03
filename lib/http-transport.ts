import type { Transport } from './contracts'
export class ApiError extends Error { constructor(public code:string,message:string,public status?:number) { super(message) } }
async function decode<T>(response:Response):Promise<T> {
 const value:unknown=await response.json()
 if(!value||typeof value!=='object'||!('request_id' in value))throw new ApiError('protocol','Некорректный ответ контроллера')
 if('error' in value){const e=value.error as {code:string;message:string};throw new ApiError(e.code,e.message,response.status)}
 if(!response.ok||!('data' in value))throw new ApiError('protocol','Некорректный ответ контроллера')
 return value.data as T
}
export const httpTransport:Transport={
 async get<T>(path:string,signal?:AbortSignal){return decode<T>(await fetch('/api/v1/'+path,{signal,credentials:'same-origin',cache:'no-store'}))},
 async post<T>(path:string,body:unknown,key:string,csrf:string,revision?:string){return decode<T>(await fetch('/api/v1/'+path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key,...(revision?{'If-Match':revision}:{})},body:JSON.stringify(body)}))}
}
export function confirmationUrl(value:string|undefined):string|null {if(!value)return null;try{const u=new URL(value);return u.origin==='http://127.0.0.1:47832'&&u.pathname==='/confirm'&&!u.username&&!u.password&&!u.hash?u.href:null}catch{return null}}
export function withinLimit(value:string,limit:number){return new TextEncoder().encode(value).length<=limit}
