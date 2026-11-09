import { it,expect,vi } from 'vitest'
import { act,render,screen } from '@testing-library/react'
import { AutoApplySetting } from '@/components/auto-apply-setting'
const origin='http://127.0.0.1:47832'
const session={csrf_token:'csrf',confirmation_origin:origin}
const props={policy:{enabled:false,confirmation_url:origin+'/policy/embed?project=a'},project:'a',session,disabled:false,onRefresh:vi.fn()}
it('настройка изменяется только внутри trusted iframe, сообщения проверяются по source origin project',()=>{
 const refresh=vi.fn()
 const view=render(<AutoApplySetting {...props} onRefresh={refresh}/> )
 const frame=screen.getByTitle('Настройка автоматического применения') as HTMLIFrameElement
 const send=(data:unknown,source:MessageEventSource|null,eventOrigin:string)=>act(()=>window.dispatchEvent(new MessageEvent('message',{data,source,origin:eventOrigin})))
 send({type:'tw:policy',project:'a'},null,origin)
 send({type:'tw:policy',project:'a'},frame.contentWindow,'https://example.com')
 send({type:'tw:policy',project:'b'},frame.contentWindow,origin)
 expect(refresh).not.toHaveBeenCalled()
 send({type:'tw:policy',project:'a'},frame.contentWindow,origin)
 expect(refresh).toHaveBeenCalledTimes(1)
 view.rerender(<AutoApplySetting {...props} disabled onRefresh={refresh}/> )
 expect(screen.getByTitle('Настройка автоматического применения')).toBe(frame)
 expect(frame.closest('[inert]')).toBeTruthy()
})
it('preview и чужой URL не получают формы включения',()=>{
 const view=render(<AutoApplySetting {...props} session={{confirmation_origin:origin}}/> )
 expect(screen.queryByRole('iframe')).toBeNull()
 view.rerender(<AutoApplySetting {...props} policy={{enabled:false,confirmation_url:'https://example.com/policy/embed?project=a'}}/> )
 expect(screen.queryByTitle('Настройка автоматического применения')).toBeNull()
})
