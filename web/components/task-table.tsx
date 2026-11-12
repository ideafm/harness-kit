'use client'
import { useEffect, useRef, useState } from 'react'
import type { Task, Transport } from '@/lib/contracts'
import { httpTransport } from '@/lib/http-transport'
import { useTaskData } from '@/hooks/use-task-data'
import { Skeleton } from '@/components/ui/skeleton'
import { ProjectSidebar } from './project-sidebar'
import { AutoApplySetting } from './auto-apply-setting'
import { ProjectSettingsDialog } from './project-settings-dialog'
import { BatchActions } from './batch-actions'
import { TaskCard } from './task-card'
import { CreateTaskSheet } from './create-task-sheet'
import { TopHeader } from './top-header'
import { ProjectPreviewBar } from './project-preview-bar'
import { CommandPalette } from './command-palette'
import { InteractiveTerminal } from './interactive-terminal'
import { taskProgress } from '@/lib/task-presentation'
import { STAGES_CONFIG } from './pipeline-stepper'
import { 
  Rows, 
  List, 
  RefreshCw, 
  Search, 
  CheckCircle2, 
  Check, 
  Clock, 
  Trash2,
  Pause,
  AlertCircle
} from 'lucide-react'

export function TaskPanel({ transport = httpTransport }: { transport?: Transport }) {
  const data = useTaskData(transport)
  const rawTasks = data.status?.tasks || []
  const tasks = [...rawTasks].sort((a, b) => b.id - a.id)
  const task = data.control?.task || tasks.find(t => t.id === data.selected)
  const projectName = data.projects?.items.find(p => p.id === data.projectId)?.name || 'tw-web'
  const projectBackend = (typeof data.status?.project === 'object' && data.status.project?.backend) || data.projects?.items.find(p => p.id === data.projectId)?.backend || 'codex'

  const [deleteRequestedTask, setDeleteRequestedTask] = useState<number>()
  const [checked,setChecked] = useState<number[]>([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [density, setDensity] = useState<'compact' | 'normal'>('compact')
  const [mobileCard, setMobileCard] = useState(false)
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false)
  const [isTerminalOpen, setIsTerminalOpen] = useState(false)
  const [isNewTaskOpen, setIsNewTaskOpen] = useState(false)
  const [collapsedSidebar, setCollapsedSidebar] = useState(false)
  const [isProjectSettingsOpen, setIsProjectSettingsOpen] = useState(false)

  // Global keyboard shortcuts: ⌘K and Ctrl+`
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setIsCommandPaletteOpen(prev => !prev)
      } else if ((e.metaKey || e.ctrlKey) && (e.key === '`' || e.key === '~' || e.key === 'ё' || e.key === 'Ё')) {
        e.preventDefault()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    setSearch('')
    setFilter('all')
    setDeleteRequestedTask(undefined)
    setMobileCard(false)
  }, [data.projectId])

  useEffect(() => {
    if (mobileCard && task && window.innerWidth < 768) {
      document.querySelector<HTMLElement>('.task-card')?.focus()
    }
  }, [mobileCard, task?.id])

  const isAttentionRequired = (t: Task) =>
    t.state === 'paused' ||
    Boolean(t.question) ||
    ['needs_permission', 'needs_input', 'awaiting_approval'].includes(t.state) ||
    (t.state === 'review' && t.stage === 'done')

  const activeTasks = tasks.filter(t => t.state !== 'trashed')
  const deletedCount = tasks.length - activeTasks.length
  const attentionCount = activeTasks.filter(isAttentionRequired).length

  const filtered = tasks.filter(t => {
    const matchesFilter = filter === 'deleted'
      ? t.state === 'trashed'
      : t.state === 'trashed'
      ? false
      : filter === 'all'
      ? true
      : filter === 'backlog'
      ? t.state === 'backlog'
      : isAttentionRequired(t)

    const matchesSearch = (`#${t.id} ${t.request.split('\n')[0]}`)
      .toLocaleLowerCase('ru')
      .includes(search.toLocaleLowerCase('ru'))

    return matchesFilter && matchesSearch
  })

  useEffect(()=>setChecked([]),[data.projectId,filter,search])
  const selectable = filtered.filter(t=>!['running','trashed'].includes(t.state))
  const checkedTasks = tasks.filter(t=>checked.includes(t.id))
  const toggleChecked = (id:number)=>setChecked(ids=>ids.includes(id)?ids.filter(n=>n!==id):[...ids,id])

  const select = (id: number) => {
    data.select(id)
    setMobileCard(true)
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#f8fafc] dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 font-sans antialiased">
      {/* 1. Left Aside Sidebar with Projects & tw logo */}
      <ProjectSidebar
        project={projectName}
        count={activeTasks.length}
        running={data.status?.worker.running ?? false}
        projects={data.projects}
        selected={data.projectId}
        onSelect={data.selectProject}
        onRemove={data.removeProject}
        policy={data.status?.auto_apply}
        session={data.session}
        commandsDisabled={data.commandsDisabled}
        onRefresh={() => void data.refresh()}
        onOpenWorkerModal={() => setIsTerminalOpen(true)}
        collapsed={collapsedSidebar}
        onToggleCollapse={() => setCollapsedSidebar(prev => !prev)}
      />

      {/* 2. Main Workspace Layout */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* Top Header Bar matching reference */}
        <TopHeader
          projectName={projectName}
          selectedProjectId={data.projectId}
          projects={data.projects}
          onSelectProject={data.selectProject}
          selectedTask={task}
          status={data.status}
          onRefresh={() => void data.refresh()}
          isRefreshing={data.loading}
          onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
          onOpenNewTaskModal={() => setIsNewTaskOpen(true)}
          onToggleTerminal={() => setIsTerminalOpen(prev => !prev)}
          isTerminalOpen={isTerminalOpen}
          onToggleSidebar={() => setCollapsedSidebar(prev => !prev)}
          onOpenSettings={() => setIsProjectSettingsOpen(true)}
          transport={data.transport}
          session={data.session}
          enabled={!data.commandsDisabled}
        />

      {/* 2. Page Banner Title matching reference */}
      <div className="px-6 py-3.5 border-b border-zinc-200/90 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/50 flex flex-wrap items-center justify-between gap-4 shrink-0">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            Работа над проектом
          </h1>
          <p className="text-xs sm:text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">
            Результат, следующее действие и детали — в одном месте.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {data.transport && (
            <ProjectPreviewBar
              transport={data.transport}
              session={data.session}
              enabled={!data.commandsDisabled}
              tasks={data.status?.tasks}
            />
          )}

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled
              className="hidden lg:flex px-3 py-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-900/60 text-zinc-400 dark:text-zinc-500 text-xs font-mono shadow-2xs items-center gap-1.5 cursor-not-allowed opacity-60"
              title="Интерактивный терминал пока не поддерживается в Harness Kit"
            >
              <span className="font-bold opacity-70">&gt;_</span>
              <span>Терминал воркера</span>
              <span className="text-[10px] font-sans px-1.5 py-0.2 rounded bg-zinc-200/60 dark:bg-zinc-800 text-zinc-500">
                скоро
              </span>
            </button>

            <CreateTaskSheet 
              key={data.projectId} 
              transport={data.transport} 
              session={data.session} 
              enabled={Boolean(data.capabilities?.actions.some(a => a === 'create' || a === 'create_task'))} 
              onCreated={select}
              open={isNewTaskOpen}
              onOpenChange={setIsNewTaskOpen}
              defaultBackend={projectBackend}
              defaultExecutionProfile={data.status?.execution_profile??'manual'}
            />
          </div>
        </div>
      </div>

      <ProjectSettingsDialog
        open={isProjectSettingsOpen}
        onOpenChange={setIsProjectSettingsOpen}
        project={data.projects?.items.find(p => p.id === data.projectId) || (data.projectId ? { id: data.projectId, name: projectName } : null)}
        policy={data.status?.auto_apply}
        session={data.session}
        disabled={data.commandsDisabled}
        onRefresh={() => void data.refresh()}
        onRemove={data.removeProject}
        canRemove={Boolean(data.projects?.can_remove)}
        tasksCount={activeTasks.length}
      />
      {data.error && (
        <div role="alert" className="mx-6 mt-4 p-3.5 rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-xs shrink-0">
          {data.error}. Последние полученные данные могут быть устаревшими.
        </div>
      )}

      {/* 3. Main Master-Detail Split Workspace */}
      <div className="flex-1 flex min-h-0 overflow-hidden relative w-full">
        {data.loading && !data.status ? (
          <div className="flex-1 p-6">
            <Skeleton aria-label="Загрузка задач" className="h-72 w-full rounded-xl" />
          </div>
        ) : (
          <div className="flex-1 flex min-h-0 overflow-hidden w-full">
            {/* Left Column: Tasks Queue Panel */}
            <section 
              className={`queue w-full md:w-[440px] xl:w-[480px] border-r border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-950/60 flex flex-col h-full shrink-0 min-w-0 select-none ${mobileCard && task ? 'hidden md:flex' : 'flex'}`} 
              aria-label="Задачи проекта"
            >
              {/* Header: Title, Count, Density Toggles, Refresh Icon */}
              <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0 bg-white/70 dark:bg-zinc-900/70">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
                    Задачи проекта
                  </h2>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 font-mono text-zinc-600 dark:text-zinc-400 font-semibold">
                    {tasks.length}
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {/* Density toggle buttons */}
                  <div className="flex items-center p-0.5 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-500">
                    <button
                      onClick={() => setDensity('compact')}
                      className={`p-1 rounded transition-colors cursor-pointer ${density === 'compact' ? 'bg-white dark:bg-zinc-700 text-blue-600 dark:text-blue-400 shadow-2xs' : 'hover:text-zinc-900'}`}
                      title="Компактный вид (узкие полоски)"
                    >
                      <Rows className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setDensity('normal')}
                      className={`p-1 rounded transition-colors cursor-pointer ${density === 'normal' ? 'bg-white dark:bg-zinc-700 text-blue-600 dark:text-blue-400 shadow-2xs' : 'hover:text-zinc-900'}`}
                      title="Развёрнутый вид (карточки)"
                    >
                      <List className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <button
                    onClick={() => void data.refresh()}
                    aria-label="Синхронизировать задачи"
                    className="p-1 rounded-md text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200 transition-colors cursor-pointer"
                    title="Синхронизировать"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${data.loading ? 'animate-spin text-blue-600' : ''}`} />
                  </button>
                </div>
              </div>

              {/* Segmented Filter Control & Search Bar */}
              <div className="p-3 border-b border-zinc-200 dark:border-zinc-800 space-y-2.5 shrink-0 bg-white/70 dark:bg-zinc-900/70">
                {/* Segmented Filter Control */}
                <div className="flex items-center p-1 rounded-lg bg-zinc-100 dark:bg-zinc-800/80 text-xs font-medium" aria-label="Фильтры задач">
                  {[
                    ['all', 'Все'],
                    ['attention', 'Нужно вам'],
                    ['backlog', 'Бэклог'],
                    ['deleted', 'Удалённые']
                  ].map(([value, testTitle]) => (
                    <button
                      key={value}
                      aria-pressed={filter === value}
                      onClick={() => setFilter(value as string)}
                      className={`flex-1 py-1 px-2 rounded-md transition-all text-center cursor-pointer flex items-center justify-center gap-1 ${
                        filter === value
                          ? 'bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 shadow-2xs font-semibold'
                          : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100'
                      }`}
                    >
                      <span>{testTitle}</span>
                      {value === 'all' && <span className="opacity-70 text-[11px]">({activeTasks.length})</span>}
                      {value === 'deleted' && <span>({deletedCount})</span>}
                      {value === 'attention' && attentionCount > 0 && (
                        <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-blue-100 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300 font-bold">
                          {attentionCount}
                        </span>
                      )}
                    </button>
                  ))}
                </div>

                {/* Search Input */}
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none" />
                  <input
                    aria-label="Поиск задач"
                    placeholder="Найти задачу по названию, ключу или статусу..."
                    value={search}
                    onChange={event => setSearch(event.target.value)}
                    className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-xs rounded-lg pl-10 pr-8 py-2 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all shadow-2xs search-input"
                    style={{ paddingLeft: '2.5rem' }}
                  />
                  {search && (
                    <button
                      onClick={() => setSearch('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 cursor-pointer px-1 py-0.5 rounded"
                    >
                      Очистить
                    </button>
                  )}
                </div>

                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" aria-label="Выбрать видимые задачи" disabled={data.commandsDisabled||!selectable.length}
                    checked={selectable.length>0&&selectable.every(t=>checked.includes(t.id))}
                    ref={node=>{if(node)node.indeterminate=selectable.some(t=>checked.includes(t.id))&&!selectable.every(t=>checked.includes(t.id))}}
                    onChange={event=>setChecked(event.target.checked?selectable.map(t=>t.id):[])}/>
                  Выбрать видимые задачи
                </label>
                <BatchActions key={data.projectId} tasks={checkedTasks} transport={data.transport} session={data.session} disabled={data.commandsDisabled}
                  onDone={()=>{setChecked([]);void data.refresh()}}/>

              </div>

              {/* Task Cards List: continuous scrollable list */}
              <div className="p-2 flex-1 overflow-y-auto min-h-0">
                {filtered.length ? (
                  <TaskTable 
                    checked={checked}
                    onToggleChecked={data.commandsDisabled ? undefined : toggleChecked}
                    tasks={filtered} 
                    selected={data.selected} 
                    onSelect={select}
                    density={density}
                    onDelete={data.commandsDisabled ? undefined : id => { setDeleteRequestedTask(id); if (data.selected !== id) select(id) }}
                  />
                ) : (
                  <p className="empty p-10 text-center text-xs text-zinc-500 dark:text-zinc-400">
                    {tasks.length ? 'Нет результатов поиска.' : 'Задач пока нет.'}
                  </p>
                )}
              </div>
            </section>

            {/* Right Column: Active Task Card / Detail Pane */}
            <div className={`card-column flex-1 h-full overflow-y-auto bg-white dark:bg-zinc-950 min-w-0 ${mobileCard && task ? 'flex flex-col' : 'hidden md:flex md:flex-col'}`}>
              {task ? (
                <>
                  <div className="p-4 md:hidden border-b border-zinc-200 dark:border-zinc-800 shrink-0">
                    <button 
                      className="mobile-back detail-button inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 text-xs font-medium cursor-pointer" 
                      onClick={() => {
                        setMobileCard(false)
                        requestAnimationFrame(() => 
                          document.querySelector<HTMLButtonElement>('.task-select[aria-pressed=true]')?.focus()
                        )
                      }}
                    >
                      Назад к задачам
                    </button>
                  </div>
                  <TaskCard 
                    key={data.projectId} 
                    task={task} 
                    requestDelete={deleteRequestedTask === task.id}
                    onDeleteRequestHandled={() => setDeleteRequestedTask(undefined)}
                    commandsDisabled={data.commandsDisabled}
                    control={data.control} 
                    transport={data.transport} 
                    session={data.session} 
                    events={data.capabilities?.events ?? false} 
                    projectView={data.capabilities?.project_view === true} 
                    onRefresh={() => void data.refresh()} 
                    onOpenTerminal={() => setIsTerminalOpen(true)}
                  />
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center p-16 text-center text-xs text-zinc-400">
                  Выберите задачу в списке.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      </div>

      {/* Floating Worker Terminal Drawer */}
      {isTerminalOpen && (
        <div className="fixed bottom-0 left-0 right-0 z-40 p-4 pt-0 animate-in slide-in-from-bottom-4 duration-200">
          <div className="max-w-5xl mx-auto shadow-2xl">
            <InteractiveTerminal
              status={data.status}
              selectedTask={task}
              projectName={projectName}
              onClose={() => setIsTerminalOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Command Palette Modal */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        tasks={activeTasks}
        projects={data.projects}
        currentProjectId={data.projectId}
        currentProjectName={projectName}
        onSelectProject={data.selectProject}
        onSelectTask={select}
        onOpenNewTaskModal={() => setIsNewTaskOpen(true)}
        onToggleTerminal={() => setIsTerminalOpen(true)}
        onRefresh={() => void data.refresh()}
      />
    </div>
  )
}

export function TaskTable({
  tasks,
  selected,
  onSelect,
  onDelete,
  checked = [],
  onToggleChecked,
  density = 'compact'
}: {
  tasks: Task[]
  selected?: number
  onSelect: (id: number) => void
  checked?: number[]
  onToggleChecked?: (id:number) => void
  onDelete?: (id: number) => void
  density?: 'compact' | 'normal'
}) {
  return (
    <div className={`task-rows ${density === 'compact' ? 'space-y-1' : 'space-y-2'}`}>
      {tasks.map(t => {
        const isSelected = selected === t.id
        const title = t.request.split('\n')[0].replace(/^\s*#{1,6}\s+/, '') || 'Без названия'
        const progress = taskProgress(t)
        const currentStageIdx = progress.index ?? 0
        const isAccepted = t.state === 'accepted'
        const isReviewDone = t.state === 'review' && t.stage === 'done'
        const isRunning = t.state === 'running'
        const isPaused = t.state === 'paused'
        const hasQuestion = Boolean(t.question) || t.state === 'needs_input'
        const needsPermission = t.state === 'needs_permission'
        const awaitingApproval = t.state === 'awaiting_approval'
        const isActionRequired = isPaused || hasQuestion || needsPermission || awaitingApproval || isReviewDone

        let badgeLabel = 'План'
        let badgeClass = 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700'
        let BadgeIcon = Clock

        if (isPaused) {
          badgeLabel = 'Пауза'
          badgeClass = 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-700/80'
          BadgeIcon = Pause
        } else if (hasQuestion) {
          badgeLabel = 'Нужен ответ'
          badgeClass = 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-700/80'
          BadgeIcon = AlertCircle
        } else if (needsPermission) {
          badgeLabel = 'Разрешение'
          badgeClass = 'bg-orange-100 dark:bg-orange-950/60 text-orange-800 dark:text-orange-200 border border-orange-300 dark:border-orange-700/80'
          BadgeIcon = AlertCircle
        } else if (awaitingApproval) {
          badgeLabel = 'Утверждение'
          badgeClass = 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-700/80'
          BadgeIcon = Clock
        } else if (isReviewDone) {
          badgeLabel = 'Приёмка'
          badgeClass = 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200/60 dark:border-amber-900/40'
          BadgeIcon = Check
        } else if (isAccepted) {
          badgeLabel = 'Принято'
          badgeClass = 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200/60 dark:border-emerald-900/40'
          BadgeIcon = CheckCircle2
        } else if (isRunning) {
          badgeLabel = 'В работе'
          badgeClass = 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200/60 dark:border-blue-900/40'
          BadgeIcon = Clock
        }

        if (t.state !== 'running' && t.dependency_wait?.length) {
          badgeLabel = 'Ждёт зависимости'
          BadgeIcon = Clock
        }
        if (t.state === 'trashed') {
          badgeLabel = 'Удалена'
          BadgeIcon = Trash2
        }

        const deleteButton = t.state !== 'trashed' && (
          <button type="button" aria-label={`Удалить задачу #${t.id}`} disabled={!onDelete || isRunning}
            title={isRunning ? 'Работающую задачу удалить нельзя' : 'Переместить в удалённые'}
            className="p-1 rounded text-zinc-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
            onClick={event => { event.stopPropagation(); onDelete?.(t.id) }}>
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )

        if (density === 'compact') {
          return (
            <div
              key={t.id}
              onClick={() => onSelect(t.id)}
              className={`task-row px-2.5 py-2 rounded-lg border text-left cursor-pointer transition-all duration-150 group flex items-center justify-between gap-2.5 ${
                isSelected
                  ? `selected bg-blue-50/80 dark:bg-blue-950/40 border-blue-500 dark:border-blue-500 shadow-2xs ring-1 ring-blue-500/30 ${isActionRequired ? 'border-l-4 border-l-amber-500 dark:border-l-amber-400' : ''}`
                  : isActionRequired
                  ? 'bg-amber-50/50 dark:bg-amber-950/20 border-amber-300 dark:border-amber-700/80 hover:border-amber-400 dark:hover:border-amber-600 border-l-4 border-l-amber-500 dark:border-l-amber-400'
                  : 'bg-white dark:bg-zinc-900/70 border-zinc-200/80 dark:border-zinc-800/80 hover:border-zinc-300 dark:hover:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-900'
              }`}
              title={`#${t.id}: ${title} (${badgeLabel})`}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <input
                  type="checkbox"
                  disabled={!onToggleChecked || isRunning || t.state === 'trashed'}
                  checked={checked.includes(t.id)}
                  aria-label={`Выбрать задачу #${t.id}`}
                  className="rounded shrink-0 disabled:opacity-30"
                  onClick={event=>event.stopPropagation()}
                  onChange={()=>onToggleChecked?.(t.id)}
                />

                {isActionRequired && (
                  <span className="relative flex h-2 w-2 shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                  </span>
                )}

                <span className="font-mono text-[11px] font-bold text-zinc-600 dark:text-zinc-400 px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 border border-zinc-200/80 dark:border-zinc-700/80 shrink-0">
                  #{t.id}
                </span>

                {t.backend && (
                  <span className={`text-[10px] font-mono font-medium px-1.5 py-0.5 rounded border shrink-0 ${
                    t.backend === 'gemini'
                      ? 'bg-purple-50 dark:purple-950/40 text-purple-700 dark:text-purple-300 border-purple-200/60 dark:border-purple-800'
                      : 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200/60 dark:border-emerald-800'
                  }`}>
                    {t.backend === 'gemini' ? 'Gemini' : 'Codex'}
                  </span>
                )}

                <button
                  className="task-select text-left truncate flex-1 bg-transparent border-0 p-0 cursor-pointer focus:outline-none"
                  aria-label={`#${t.id} ${title}`}
                  aria-pressed={isSelected}
                  onClick={() => onSelect(t.id)}
                >
                  <span className={`text-xs font-medium truncate leading-tight block ${
                    isSelected 
                      ? 'text-blue-950 dark:text-blue-100 font-semibold' 
                      : 'text-zinc-800 dark:text-zinc-200 group-hover:text-blue-600 dark:group-hover:text-blue-400'
                  }`}>
                    {title}
                  </span>
                </button>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <div className="hidden sm:flex items-center gap-1 bg-zinc-100/80 dark:bg-zinc-800/60 px-1.5 py-0.5 rounded">
                  {STAGES_CONFIG.map((s, idx) => {
                    const isStagePassed = isAccepted || idx < currentStageIdx
                    const isStageActive = !isAccepted && idx === currentStageIdx

                    return (
                      <div
                        key={s.id}
                        className={`w-1.5 h-1.5 rounded-full transition-transform ${
                          isStageActive
                            ? isActionRequired
                              ? 'bg-amber-500 dark:bg-amber-400 ring-2 ring-amber-300 dark:ring-amber-900 scale-125'
                              : 'bg-blue-600 dark:bg-blue-400 ring-2 ring-blue-300 dark:ring-blue-900 scale-125'
                            : isStagePassed
                            ? 'bg-emerald-500 dark:bg-emerald-400'
                            : 'bg-zinc-300 dark:bg-zinc-700'
                        }`}
                        title={`Этап: ${s.label}`}
                      />
                    )
                  })}
                </div>

                <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap ${badgeClass}`}>
                  <BadgeIcon className="w-2.5 h-2.5 shrink-0" />
                  <span className="truncate max-w-[80px]">{badgeLabel}</span>
                </span>
                {deleteButton}

              </div>
            </div>
          )
        }

        return (
          <div
            key={t.id}
            onClick={() => onSelect(t.id)}
            className={`task-row p-3 rounded-xl border text-left cursor-pointer transition-all duration-150 group relative ${
              isSelected
                ? `selected bg-white dark:bg-zinc-900 border-blue-500 dark:border-blue-500 shadow-sm ring-1 ring-blue-500/30 ${isActionRequired ? 'border-l-4 border-l-amber-500 dark:border-l-amber-400' : ''}`
                : isActionRequired
                ? 'bg-amber-50/50 dark:bg-amber-950/20 border-amber-300 dark:border-amber-700/80 hover:border-amber-400 dark:hover:border-amber-600 border-l-4 border-l-amber-500 dark:border-l-amber-400 shadow-2xs'
                : 'bg-white/80 dark:bg-zinc-900/60 border-zinc-200/90 dark:border-zinc-800/80 hover:border-zinc-300 dark:hover:border-zinc-700 hover:shadow-2xs'
            }`}
          >
            <div className="flex items-center justify-between text-xs mb-1.5">
              <div className="flex items-center gap-2 font-mono text-[11px] font-semibold text-zinc-500 dark:text-zinc-400">
                <input
                  type="checkbox"
                  disabled={!onToggleChecked || isRunning || t.state === 'trashed'}
                  checked={checked.includes(t.id)}
                  aria-label={`Выбрать задачу #${t.id}`}
                  className="rounded shrink-0 disabled:opacity-30"
                  onClick={event=>event.stopPropagation()}
                  onChange={()=>onToggleChecked?.(t.id)}
                />
                {isActionRequired && (
                  <span className="relative flex h-2 w-2 shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                  </span>
                )}
                <span className="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 border border-zinc-200/80 dark:border-zinc-700/80 font-bold text-zinc-600 dark:text-zinc-300">
                  #{t.id}
                </span>
                <span className="text-zinc-300 dark:text-zinc-600">·</span>
                <span className="text-zinc-700 dark:text-zinc-300">TASK-{t.id}</span>
                {t.backend && (
                  <>
                    <span className="text-zinc-300 dark:text-zinc-600">·</span>
                    <span className={`text-[10px] font-mono font-medium px-1.5 py-0.2 rounded border ${
                      t.backend === 'gemini'
                        ? 'bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border-purple-200/60 dark:border-purple-800'
                        : 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200/60 dark:border-emerald-800'
                    }`}>
                      {t.backend === 'gemini' ? 'Gemini' : 'Codex'}
                    </span>
                  </>
                )}
              </div>

              <div className="flex items-center gap-1.5">
                <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap ${badgeClass}`}>
                  <BadgeIcon className="w-2.5 h-2.5 shrink-0" />
                  <span>{badgeLabel}</span>
                </span>
                {deleteButton}
              </div>
            </div>

            <button
              className="task-select text-left w-full bg-transparent border-0 p-0 cursor-pointer focus:outline-none mb-2"
              aria-label={`#${t.id} ${title}`}
              aria-pressed={isSelected}
              onClick={() => onSelect(t.id)}
            >
              <h3 className={`text-xs font-semibold leading-snug line-clamp-2 transition-colors ${
                isSelected
                  ? 'text-blue-950 dark:text-blue-100 font-bold'
                  : 'text-zinc-900 dark:text-zinc-100 group-hover:text-blue-600 dark:group-hover:text-blue-400'
              }`}>
                {title}
              </h3>
            </button>

            <div className="flex items-center justify-between pt-2 border-t border-zinc-100 dark:border-zinc-800/80">
              <div className="flex items-center gap-1">
                {STAGES_CONFIG.map((s, idx) => {
                  const Icon = s.icon
                  const isStagePassed = isAccepted || idx < currentStageIdx
                  const isStageActive = !isAccepted && idx === currentStageIdx

                  return (
                    <div
                      key={s.id}
                      className={`w-5 h-5 rounded flex items-center justify-center text-[10px] transition-colors ${
                        isStageActive
                          ? isActionRequired
                            ? 'bg-amber-500 text-white shadow-2xs font-bold ring-2 ring-amber-300 dark:ring-amber-900'
                            : 'bg-blue-600 text-white shadow-2xs font-bold ring-2 ring-blue-300 dark:ring-blue-900'
                          : isStagePassed
                          ? 'bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300'
                          : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-400'
                      }`}
                      title={`Этап: ${s.label}`}
                    >
                      <Icon className="w-3 h-3" />
                    </div>
                  )
                })}
              </div>

              <span className="text-[10px] font-medium text-zinc-500 dark:text-zinc-400">
                {badgeLabel}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
