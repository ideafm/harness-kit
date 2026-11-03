export function loopbackUrl(value:unknown){
 if(typeof value!=='string')return undefined
 try{const url=new URL(value);return url.protocol==='http:'&&['127.0.0.1','[::1]','localhost'].includes(url.hostname)&&!url.username&&!url.password&&!url.hash?url:undefined}catch{return undefined}
}
export function widgetUrl(value:unknown,origin:unknown){
 const url=loopbackUrl(value);const trusted=loopbackUrl(origin)
 return url&&trusted&&trusted.origin===origin&&url.origin===origin&&url.pathname==='/confirm/embed'?url.href:undefined
}
