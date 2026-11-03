import { it,expect,vi } from 'vitest'
import { act,render,screen } from '@testing-library/react'
import type { Control } from '@/lib/contracts'
import { TrustedDecisionWidget } from '@/components/trusted-decision-widget'
const origin='http://127.0.0.1:47832'
const session={csrf_token:'csrf',confirmation_origin:origin}
const control:Control={task:{id:1,state:'review',stage:'done',updated:1,request:'Запрос',artifacts:[]},revision:'r1',allowed_actions:['accept_result'],plan:null,result:null,confirmation_urls:{},confirmation_widgets:{accept_result:origin+'/confirm/embed?id=1'}}
it('проверяет origin, source и весь контекст, только запрашивая реальные данные',()=>{
 const refresh=vi.fn();const props={control,session,project:'a',action:'accept_result',onRefresh:refresh}
 const view=render(<TrustedDecisionWidget {...props}/>)
 const frame=screen.getByTitle('Принять результат') as HTMLIFrameElement
 const decision={type:'tw:decision',task:1,project:'a',action:'accept_result',status:'succeeded'}
 const send=(data:unknown,source:MessageEventSource|null=frame.contentWindow,eventOrigin=origin)=>act(()=>window.dispatchEvent(new MessageEvent('message',{data,source,origin:eventOrigin})))
 send(decision,null);send(decision,frame.contentWindow,'http://localhost:47832')
 for(const patch of [{task:2},{project:'b'},{action:'approve_plan'},{status:'pending'}])send({...decision,...patch})
 expect(refresh).not.toHaveBeenCalled()
 send({type:'tw:widget-size',height:1000});expect(frame.style.height).toBe('420px')
 send({type:'tw:widget-size',height:NaN});expect(frame.style.height).toBe('420px')
 send({type:'tw:widget-size',height:-1});expect(frame.style.height).toBe('40px')
 send(decision);expect(refresh).toHaveBeenCalledTimes(1)
 const source=frame.contentWindow
 view.rerender(<TrustedDecisionWidget {...props} control={{...control,revision:'r2'}}/>)
 send(decision,source);expect(refresh).toHaveBeenCalledTimes(1)
 view.rerender(<TrustedDecisionWidget {...props} control={{...control,allowed_actions:[]}}/>)
 expect(screen.queryByTitle('Принять результат')).toBeNull()
 send(decision,source);expect(refresh).toHaveBeenCalledTimes(1)
})
it('не восстанавливает widgets в preview и не использует старую страницу',()=>{
 const view=render(<TrustedDecisionWidget control={control} session={{confirmation_origin:origin}} project="a" action="accept_result" onRefresh={vi.fn()}/>)
 expect(screen.queryByTitle('Принять результат')).toBeNull()
 view.rerender(<TrustedDecisionWidget control={{...control,confirmation_widgets:undefined,confirmation_urls:{accept_result:origin+'/confirm'}}} session={session} project="a" action="accept_result" onRefresh={vi.fn()}/>)
 expect(screen.queryByRole('link')).toBeNull()
 expect(screen.queryByTitle('Принять результат')).toBeNull()
})
