'use client'
import type { Task, Transport } from '@/lib/contracts'
import { ArtifactView } from './artifact-view'
import { EventList } from './event-list'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs'
import { 
  History, 
  FileText, 
  ListChecks, 
  GitCommit, 
  CheckCircle, 
  Eye 
} from 'lucide-react'

export function TaskTabs({
  task,
  transport,
  events,
  value,
  onValueChange
}: {
  task: Task
  transport: Transport
  events: boolean
  value?: string
  onValueChange?: (value: string) => void
}) {
  const has = (name: string) => 
    Array.isArray(task.artifacts) 
      ? task.artifacts.includes(name) 
      : Boolean(task.artifacts && name in task.artifacts)

  const artifact = (name: string) => 
    has(name) 
      ? <ArtifactView key={task.id + name} task={task.id} name={name} transport={transport} /> 
      : <p className="text-xs text-zinc-500 py-3">Документ ещё не предоставлен.</p>

  const defaultTab = task.state === 'review' && task.stage === 'done' 
    ? (has('checks') ? 'checks' : has('review') ? 'review' : 'events') 
    : 'events'

  return (
    <Tabs 
      key={task.id} 
      {...(value !== undefined ? { value, onValueChange } : { defaultValue: defaultTab })}
      className="task-materials border-t border-zinc-200 dark:border-zinc-800 pt-4"
    >
      <TabsList variant="line" aria-label="Материалы задачи" className="w-full justify-start border-b border-zinc-200 dark:border-zinc-800 gap-6 px-1 h-auto pb-0">
        <TabsTrigger 
          value="events" 
          className={`flex items-center gap-1.5 py-2 text-xs ${events ? '' : 'opacity-50'}`}
          title={events ? 'История событий' : 'События недоступны'}
        >
          <History className="w-3.5 h-3.5 text-zinc-400" />
          <span>История</span>
        </TabsTrigger>

        <TabsTrigger value="request" className="flex items-center gap-1.5 py-2 text-xs">
          <FileText className="w-3.5 h-3.5 text-zinc-400" />
          <span>Исходная задача</span>
        </TabsTrigger>

        <TabsTrigger 
          value="plan" 
          className={`flex items-center gap-1.5 py-2 text-xs ${(has('plan') || has('specification')) ? '' : 'opacity-50'}`}
          title={(has('plan') || has('specification')) ? 'План реализации' : 'План ещё не сформирован'}
        >
          <ListChecks className="w-3.5 h-3.5 text-zinc-400" />
          <span>План</span>
          {(has('plan') || has('specification')) && (
            <span className="w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400" />
          )}
        </TabsTrigger>

        {[
          ['diff', 'Изменения', GitCommit],
          ['checks', 'Проверки', CheckCircle],
          ['review', 'Ревью', Eye]
        ].map(([name, title, Icon]) => {
          const TabIcon = Icon as React.ElementType
          const exists = has(name as string)
          return (
            <TabsTrigger 
              key={name as string} 
              value={name as string} 
              className={`flex items-center gap-1.5 py-2 text-xs ${exists ? '' : 'opacity-50'}`}
              title={exists ? (title as string) : `Артефакт «${title}» ещё не предоставлен`}
            >
              <TabIcon className="w-3.5 h-3.5 text-zinc-400" />
              <span>{title as string}</span>
              {exists && (
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400" />
              )}
            </TabsTrigger>
          )
        })}
      </TabsList>

      <TabsContent value="events" className="pt-4 text-xs">
        {events ? (
          <details className="space-y-2">
            <summary className="font-semibold text-zinc-700 dark:text-zinc-300 cursor-pointer py-1">
              Полная история событий
            </summary>
            <div className="pt-2">
              <EventList task={task.id} transport={transport} />
            </div>
          </details>
        ) : (
          <p className="text-zinc-500 py-2">События недоступны.</p>
        )}
      </TabsContent>

      <TabsContent value="request">
        <pre className="artifact font-mono text-xs p-4 rounded-xl bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 whitespace-pre-wrap overflow-x-auto leading-relaxed my-0">
          {task.request}
        </pre>
      </TabsContent>

      <TabsContent value="plan" className="pt-4 space-y-4">
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
            Спецификация
          </h3>
          <div className="p-3 bg-zinc-50 dark:bg-zinc-950 rounded-xl border border-zinc-200 dark:border-zinc-800">
            {artifact('specification')}
          </div>
        </div>

        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
            План
          </h3>
          <div className="p-3 bg-zinc-50 dark:bg-zinc-950 rounded-xl border border-zinc-200 dark:border-zinc-800">
            {artifact('plan')}
          </div>
        </div>
      </TabsContent>

      {['diff', 'checks', 'review'].map(name => (
        <TabsContent key={name} value={name} className="pt-4">
          <div className="p-3 bg-zinc-50 dark:bg-zinc-950 rounded-xl border border-zinc-200 dark:border-zinc-800">
            {artifact(name)}
          </div>
        </TabsContent>
      ))}
    </Tabs>
  )
}
