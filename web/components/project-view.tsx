'use client'
import type { Session,Task,Transport } from '@/lib/contracts'
import { loopbackUrl } from '@/lib/controller-links'
import { useProjectView } from '@/hooks/use-project-view'
import { Button } from './ui/button'
import { AppIcon } from './app-icon'
export function ProjectView({task,transport,session,enabled=false}:{task:Task;transport:Transport;session?:Session;enabled?:boolean}){
 const state=useProjectView(transport,task.id,enabled,session?.csrf_token)
 const v=state.data?.view
 const preview=task.preview
 const url=loopbackUrl(preview?.url)
 const modern=preview&&['persistent','current','mode','version'].some(key=>key in preview)
 const validPreview=url&&(!modern||(preview?.persistent===true&&preview.current===true&&preview.read_only===true&&state.ready&&preview.mode===v?.mode&&typeof preview.version==='string'&&preview.version===v?.source_digest))
 const mode=v?.requested?.task===task.id?v.requested.mode:v?.active_task===task.id?v.mode:undefined
 const error=v?.error&&(typeof v.error==='string'?v.error:v.error.message)
 const address=loopbackUrl(v?.url)
 const fallback=!preview&&state.ready&&address?new URL(address.href):undefined
 if(fallback){fallback.searchParams.set('__tw_task',String(task.id));fallback.searchParams.set('__tw_version',v!.source_digest!)}
 const openUrl=validPreview?url:fallback
 const writable=enabled&&Boolean(session?.csrf_token?.trim())
 const stopping=state.pending?.body.action==='stop'
 const running=Boolean(v?.running)
 const preparing=!stopping&&(state.busy||Boolean(v?.building)||Boolean(state.waiting&&!state.ready))
 const runtimeLabel=state.stale&&v?'Обновляем статус':stopping?'Останавливаем':preparing?'Запускается':running?'Запущен':state.data?'Остановлен':enabled?'Проверяем статус':'Просмотр результата'
 const indicator=state.stale||preparing||stopping?'bg-amber-400':running?'bg-emerald-500':'bg-zinc-400'
 const helpClass='text-xs leading-relaxed text-zinc-500 dark:text-zinc-400'

 const status=!state.data?'Загрузка состояния':!state.data.available?'Просмотр отсутствует':error?'Ошибка подготовки':v?.building?'Подготовка':!v?.running?'Просмотр остановлен':state.pending||state.waiting&&!state.ready?'Подготовка':state.ready?'Готово':'Сохранена предыдущая версия'
 return <section className="result-summary overflow-hidden rounded-xl border border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900" aria-label="Просмотр приложения">
 <div className="flex flex-wrap items-center justify-between gap-3 bg-gradient-to-r from-blue-50/80 to-white px-4 py-3.5 dark:from-blue-950/20 dark:to-zinc-900">
  <div className="flex min-w-0 items-center gap-3">
   <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-blue-100 bg-white text-blue-600 shadow-sm dark:border-blue-900/40 dark:bg-zinc-900 dark:text-blue-400"><AppIcon name="application" width="21" height="21" /></span>
   <div className="min-w-0"><h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Просмотр проекта</h3><div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"><span className="inline-flex items-center gap-1.5 text-zinc-600 dark:text-zinc-400" role="status"><span className={`size-1.5 rounded-full ${indicator}`} />{runtimeLabel}</span>{address&&<span className="font-mono text-zinc-400 dark:text-zinc-500">{address.host}</span>}</div></div>
  </div>
  <div className="flex flex-wrap items-center gap-2">
   {writable&&(!running||v?.active_task!==task.id)&&<Button size="sm" variant={openUrl?'outline':'default'} className="gap-1.5 rounded-lg" disabled={!state.canSend||!state.data?.available} onClick={()=>void state.send('select','checked')}><AppIcon name="play" width="15" height="15" />{preparing?'Запускаем…':running?'Показать эту задачу':'Запустить'}</Button>}
   {writable&&running&&state.data?.actions?.includes('stop')&&<Button size="sm" variant="outline" className="gap-1.5 rounded-lg" title="Остановить просмотр проекта. Выполнение задач продолжится." disabled={!state.canSend} onClick={()=>void state.send('stop',mode??'checked')}><AppIcon name="stop" width="15" height="15" />{stopping?'Останавливаем…':'Остановить'}</Button>}
   {openUrl?<a className="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 text-xs font-medium text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500" style={{color:"white"}} aria-label="Открыть результат" title="Открыть результат в новой вкладке" href={openUrl.href} target="_blank" rel="noopener noreferrer">Открыть<AppIcon name="external" width="15" height="15" /></a>:writable&&<Button size="sm" variant="outline" className="gap-1.5 rounded-lg" disabled title="Открытие станет доступно после подготовки результата">Открыть<AppIcon name="external" width="15" height="15" /></Button>}
  </div>
 </div>
 <div className="space-y-2 px-4 pb-3 pt-2">
 {state.ready?<p className={helpClass}>TASK-{String(task.id).padStart(3,'0')} · {v?.mode==='working'?'Текущие правки, ещё не подтверждены проверками':'Проверенная версия'}{task.state==='review'?' · Можно посмотреть до приёмки':''}</p>:running&&v?.active_task&&v.active_task!==task.id?<p className={helpClass}>Сейчас запущена TASK-{String(v.active_task).padStart(3,'0')}. Можно переключить просмотр на выбранную задачу.</p>:v?.manually_stopped?<p className={helpClass}>Остановлен вручную. Нажмите «Запустить», чтобы снова показывать готовые результаты.</p>:!validPreview&&enabled&&v?.active_task!==task.id?<p className={helpClass}>Просмотр результата этой задачи ещё не подготовлен.</p>:null}
 {(state.error||error)&&<p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">{state.error||error}</p>}
 <details><summary className="text-xs cursor-pointer">Другие варианты просмотра и подробности</summary>{enabled?<><p>{status}</p>{state.data?.reason&&<p>{state.data.reason}</p>}{v&&<><p>Активная задача: {v.active_task??'нет'}. Версия: {v.mode==='working'?'рабочая, неподтверждённая':v.mode==='checked'?'проверенная':'не указана'}.</p>{v.requested&&<p>Запрошена задача: {v.requested.task}, режим: {v.requested.mode==='working'?'рабочая, неподтверждённая':'проверенная'}. </p>}{v.source_digest&&<p>Версия исходников: {v.source_digest.slice(0,12)}</p>}<details><summary>Подробности версии</summary><p className="break-all">Ревизия просмотра: {v.revision??'не указана'}</p><p className="break-all">Ревизия выбора: {v.requested?.revision??'не указана'}</p><p className="break-all">Полная версия исходников: {v.source_digest??'не указана'}</p>{preview?.version!==undefined&&<p className="break-all">Полная версия результата: {preview.version}</p>}</details>{v.url&&<p className="break-all">Постоянный адрес: {v.url}</p>}{v.message&&<p>{v.message}</p>}{v.active_task!==null&&v.active_task!==task.id&&<p>Сохранена предыдущая версия задачи {v.active_task}. Выбор версии переключит просмотр на задачу {task.id}.</p>}</>}{state.stale&&state.data&&<p>Данные просмотра устарели. Ожидается актуальное обновление.</p>}{!session?.csrf_token?.trim()?<p>Просмотр доступен только для чтения: нет полномочий на отправку команд.</p>:<>{state.data?.revision===null&&<p>Команды недоступны: контроллер не предоставил ревизию просмотра.</p>}<div className="space-y-3 py-2">
 <div className="space-y-1"><Button variant="outline" size="sm" aria-describedby={`checked-help-${task.id}`} disabled={!state.canSend} onClick={()=>void state.send('select','checked')}>Показать проверенную версию</Button><p id={`checked-help-${task.id}`} className="text-xs text-zinc-500 dark:text-zinc-400">Сохранённый результат последних успешных проверок этой задачи. Более новые правки могут в него не входить.</p></div>
 <div className="space-y-1"><Button variant="outline" size="sm" aria-describedby={`working-help-${task.id}`} disabled={!state.canSend} onClick={()=>void state.send('select','working')}>Показать рабочую версию</Button><p id={`working-help-${task.id}`} className="text-xs text-zinc-500 dark:text-zinc-400">Сборка из текущих файлов задачи. Может содержать изменения, которые ещё не прошли проверки.</p></div>
 <div className="space-y-1"><Button variant="outline" size="sm" aria-describedby={`refresh-help-${task.id}`} disabled={!state.canSend||!mode} onClick={()=>mode&&void state.send('refresh',mode)}>Повторить подготовку</Button><p id={`refresh-help-${task.id}`} className="text-xs text-zinc-500 dark:text-zinc-400">Заново подготовить просмотр в выбранном режиме. Полезно, если подготовка завершилась ошибкой.</p></div>
 {state.pending&&<div className="space-y-1"><Button variant="outline" size="sm" aria-describedby={`retry-help-${task.id}`} disabled={state.busy} onClick={()=>void state.retry()}>Повторить прежнюю операцию</Button><p id={`retry-help-${task.id}`} className="text-xs text-zinc-500 dark:text-zinc-400">Уточнить исход запроса после потери связи и при необходимости повторить его с теми же параметрами.</p></div>}
 </div></>}</>:<p>Управление постоянным просмотром недоступно: контроллер не предоставил полномочия на управление просмотром.</p>}{!openUrl&&<p>Предпросмотр недоступен: {!preview?.url?'адрес результата не предоставлен':!url?'адрес результата не является поддерживаемым локальным HTTP-адресом':'соответствие задачи и версии ещё не подтверждено'}.</p>}{preview?.version!==undefined&&<p>Версия результата: {String(preview.version).slice(0,12)}</p>}{preview?.mode==='working'&&<p>Результат: рабочая, неподтверждённая версия.</p>}</details></div></section>
}
