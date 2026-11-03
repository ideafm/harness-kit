'use client'
import { useEffect,useState } from 'react'
import type { Artifact,Transport } from '@/lib/contracts'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
export function ArtifactView({task,name,transport}:{task:number;name:string;transport:Transport}){const [data,setData]=useState<Artifact>();const [error,setError]=useState('');const [attempt,retry]=useState(0);useEffect(()=>{const abort=new AbortController();setData(undefined);setError('');transport.get<Artifact>(`tasks/${task}/artifacts/${name}`,abort.signal).then(v=>{if(typeof v.text!=='string'||typeof v.truncated!=='boolean')throw Error('Некорректный артефакт');if(!abort.signal.aborted)setData(v)}).catch(e=>{if(!abort.signal.aborted)setError(e instanceof Error?e.message:'Ошибка артефакта')});return()=>abort.abort()},[task,name,transport,attempt]);return <div>{error?<div role="alert">{error} <Button variant="outline" onClick={()=>retry(n=>n+1)}>Повторить</Button></div>:!data?<Skeleton className="h-32 w-full"/>:<>{data.truncated&&<p className="notice">Артефакт усечён контроллером.</p>}<div><pre className="artifact">{data.text||'Артефакт пуст.'}</pre></div></>}</div>}
