import { describe,it,expect,vi } from 'vitest'
import { confirmationUrl,httpTransport,withinLimit } from '@/lib/http-transport'
describe('Граница оператора',()=>{
 it('принимает только точный origin и маршрут подтверждения',()=>{expect(confirmationUrl('http://127.0.0.1:47832/confirm?id=1')).toBeTruthy();for(const url of ['http://127.0.0.1:47831/confirm','https://evil.test/confirm','http://127.0.0.1:47832/confirm/other','http://u@127.0.0.1:47832/confirm','javascript:alert(1)'])expect(confirmationUrl(url)).toBeNull()})
 it('считает UTF-8 байты',()=>{expect(withinLimit('я'.repeat(8192),16384)).toBe(true);expect(withinLimit('я'.repeat(8193),16384)).toBe(false)})
 it('не превращает отказ в успех',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({request_id:'r',error:{code:'conflict',message:'Версия устарела'}}),{status:409})));await expect(httpTransport.get('status')).rejects.toThrow('Версия устарела')})
 it('передаёт CSRF, revision и прежний ключ',async()=>{const fetcher=vi.fn().mockResolvedValue(new Response(JSON.stringify({request_id:'r',data:{status:'pending'}})));vi.stubGlobal('fetch',fetcher);await httpTransport.post('tasks/1/actions',{action:'pause'},'same-key','csrf','rev');expect(fetcher).toHaveBeenCalledWith('/api/v1/tasks/1/actions',expect.objectContaining({headers:expect.objectContaining({'Idempotency-Key':'same-key','X-CSRF-Token':'csrf','If-Match':'rev'})}))})
})
import { projectTransport } from '@/lib/transport'
it.each(['.','..'])('не отправляет проектные GET и POST для dot segment %s',async(id)=>{
 const fetcher=vi.fn()
 vi.stubGlobal('fetch',fetcher)
 const transport=projectTransport(httpTransport,id)
 for(const path of ['status','capabilities','tasks','tasks/1/control','tasks/1/events','tasks/1/artifacts/diff','operations/op'])await expect(transport.get(path)).rejects.toThrow('Идентификатор проекта нельзя безопасно передать в URL')
 for(const path of ['tasks','tasks/1/actions'])await expect(transport.post(path,{action:'start'},'key','csrf','rev')).rejects.toThrow('Идентификатор проекта нельзя безопасно передать в URL')
 expect(fetcher).not.toHaveBeenCalled()
})
it.each(['.','..','a/b ?','%2e%2e','проект'])('сохраняет общий session для проекта %s',async(id)=>{
 const fetcher=vi.fn().mockImplementation(async()=>new Response(JSON.stringify({request_id:'r',data:{csrf_token:'csrf'}})))
 vi.stubGlobal('fetch',fetcher)
 await expect(projectTransport(httpTransport,id).get('session')).resolves.toEqual({csrf_token:'csrf'})
 expect(fetcher).toHaveBeenCalledWith('/api/v1/session',expect.anything())
})
it.each(['a/b ?','%2e%2e','проект','.name','name..'])('сохраняет проект %s в фактическом URL GET и POST',async(id)=>{
 const addresses:string[]=[]
 const fetcher=vi.fn().mockImplementation(async(input:string)=>{addresses.push(new URL(input,'http://127.0.0.1:47832').pathname);return new Response(JSON.stringify({request_id:'r',data:{}}))})
 vi.stubGlobal('fetch',fetcher)
 const transport=projectTransport(httpTransport,id)
 await transport.get('status')
 await transport.post('tasks',{request:'Запрос'},'key','csrf')
 expect(addresses).toEqual([`/api/v1/projects/${encodeURIComponent(id)}/status`,`/api/v1/projects/${encodeURIComponent(id)}/tasks`])
})
it('сохраняет заголовки HTTP и проект подтверждения',async()=>{
 const fetcher=vi.fn().mockImplementation(async()=>new Response(JSON.stringify({request_id:'r',data:{status:'pending'}})))
 vi.stubGlobal('fetch',fetcher)
 await projectTransport(httpTransport,'second').post('tasks/1/actions',{action:'pause'},'same-key','csrf','rev')
 expect(fetcher).toHaveBeenCalledWith('/api/v1/projects/second/tasks/1/actions',expect.objectContaining({headers:expect.objectContaining({'Idempotency-Key':'same-key','X-CSRF-Token':'csrf','If-Match':'rev'}),body:JSON.stringify({action:'pause'})}))
 const url='http://127.0.0.1:47832/confirm?project=second&task=1&action=accept_result'
 expect(confirmationUrl(url)).toBe(url)
})

