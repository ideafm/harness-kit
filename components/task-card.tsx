import type { Task,Control,Transport,Session } from '@/lib/contracts'
import { AppIcon } from './app-icon'
import { Badge } from '@/components/ui/badge'
import { TaskActions } from './task-actions'
import { TaskProgress } from './task-progress'
import { TaskTabs } from './task-tabs'
import { taskStateLabel } from '@/lib/task-presentation'
import { loopbackUrl } from '@/lib/controller-links'
export function TaskCard({task,control,transport,session,onRefresh,events=false}:{task:Task;control?:Control;transport:Transport;session?:Session;onRefresh:()=>void;events?:boolean}){
 const actions=control?.allowed_actions||[]
 const guidance=task.state==="running"?"От вас сейчас ничего не требуется.":task.state==="awaiting_approval"?"Откройте план, утвердите его или верните замечания.":task.state==="review"||task.state==="done"||actions.includes("accept_result")?"Посмотрите результат и сверьте с исходным запросом, затем примите или оставьте замечания.":task.state==="paused"?"Задача на паузе.":task.state==="accepted"?"Результат принят.":task.state==="backlog"?"Задача в бэклоге.":"Вопроса к вам нет."
 const preview=loopbackUrl(task.preview?.url)
 const summary=task.implementation_summary?.trim()||'Сводка результата не предоставлена.'
 const reason=task.reason?.trim()||'Не предоставлена контроллером.'
 return <section tabIndex={-1} className="task-card" aria-label="Карточка задачи"><div className="section-heading"><span className="eyebrow">TASK-{task.id}</span><Badge variant="secondary"><AppIcon name={task.state==='accepted'?'check':'document'}/>{taskStateLabel(task)}</Badge></div><h2>{task.request.split('\n')[0]||'Без названия'}</h2><TaskProgress task={task}/><div className="result-summary"><h3>Текущее состояние и результат</h3><p>{summary}</p><p><strong>Причина ожидания: </strong>{reason}</p></div><div><h3>Что требуется от вас</h3><p>{task.question||guidance}</p>{!task.question&&<p className="muted">Конкретные рекомендации для человеческой проверки не предоставлены. Откройте «План», «Изменения», «Проверки» и «Ревью», чтобы изучить доказательства.</p>}</div>{control?<TaskActions key={task.id} control={control} transport={transport} session={session} onRefresh={onRefresh}/>:<p className="muted">Управление недоступно до получения актуальных полномочий контроллера.</p>}{preview&&<a href={preview.href} target="_blank" rel="noopener noreferrer">Открыть preview · только чтение</a>}<TaskTabs task={task} transport={transport} events={events}/><p className="muted">Приёмка не означает применение изменений.</p></section>
}
