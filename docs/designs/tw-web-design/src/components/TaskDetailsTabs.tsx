import React, { useState, useEffect } from 'react';
import { 
  History, 
  FileText, 
  ListChecks, 
  GitCommit, 
  CheckCircle, 
  Eye, 
  ChevronDown, 
  ChevronUp, 
  Terminal, 
  Copy, 
  Check, 
  Clock, 
  AlertCircle, 
  ExternalLink, 
  ShieldCheck, 
  Cpu, 
  Sparkles,
  Plus,
  Share2,
  Filter
} from 'lucide-react';
import { Task, PlanItem, LogEvent } from '../types';
import { DiffViewer } from './DiffViewer';

interface TaskDetailsTabsProps {
  task: Task;
  activeTab: string;
  onSelectTab: (tabId: string) => void;
}

export function TaskDetailsTabs({ task, activeTab, onSelectTab }: TaskDetailsTabsProps) {
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [copiedPR, setCopiedPR] = useState(false);
  const [copiedHistory, setCopiedHistory] = useState(false);
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);
  const [logFilter, setLogFilter] = useState<'all' | 'thought' | 'bash' | 'file' | 'check'>('all');

  // Interactive plan items state
  const [planItems, setPlanItems] = useState<PlanItem[]>(task.planItems || []);
  const [newPlanText, setNewPlanText] = useState('');
  const [isAddingPlan, setIsAddingPlan] = useState(false);

  useEffect(() => {
    setPlanItems(task.planItems || []);
  }, [task.id, task.planItems]);

  const TABS = [
    { id: 'history', label: 'История', icon: History, count: task.logs.length },
    { id: 'prompt', label: 'Исходная задача', icon: FileText },
    { id: 'plan', label: 'План', icon: ListChecks, count: planItems.length },
    { id: 'diff', label: 'Изменения', icon: GitCommit, count: task.diffs.length },
    { id: 'checks', label: 'Проверки', icon: CheckCircle, count: task.checks.length },
    { id: 'review', label: 'Ревью', icon: Eye }
  ];

  const handleCopyPrompt = () => {
    navigator.clipboard.writeText(task.harnessPrompt);
    setCopiedPrompt(true);
    setTimeout(() => setCopiedPrompt(false), 2000);
  };

  const handleCopyPRDescription = () => {
    const prMarkdown = `# [${task.key}] ${task.title}

## Описание задачи
${task.description}

## Ветка Git
\`${task.branch}\`

## Статус выполнения
- Модель: \`${task.model}\`
- Этап: **${task.currentStageLabel}**
- Статус: ${task.statusLabel}

## Верификация и проверки
${task.checks.map(c => `- [x] ${c.name}: ${c.summary}`).join('\n') || '- Все базовые проверки пройдены'}

## Измененные файлы (${task.diffs.length})
${task.diffs.map(d => `- \`${d.filename}\` (+${d.additions} -${d.deletions})`).join('\n') || '- Файлы зафиксированы в коммите'}

## План реализации
${planItems.map(p => `- [${p.completed ? 'x' : ' '}] ${p.title}`).join('\n')}

---
*Сгенерировано tw-web Agent Harness*`;

    navigator.clipboard.writeText(prMarkdown);
    setCopiedPR(true);
    setTimeout(() => setCopiedPR(false), 2000);
  };

  const handleCopyHistory = () => {
    const raw = task.logs.map(l => `[${l.timestamp}] [${l.type.toUpperCase()}] ${l.title}\n${l.content}`).join('\n\n');
    navigator.clipboard.writeText(raw);
    setCopiedHistory(true);
    setTimeout(() => setCopiedHistory(false), 2000);
  };

  const toggleLogExpand = (id: string) => {
    setExpandedLogId(expandedLogId === id ? null : id);
  };

  const togglePlanItem = (id: string) => {
    setPlanItems(prev => prev.map(item => 
      item.id === id ? { ...item, completed: !item.completed } : item
    ));
  };

  const handleAddPlanItem = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPlanText.trim()) return;

    const newItem: PlanItem = {
      id: `p-custom-${Date.now()}`,
      title: newPlanText.trim(),
      completed: false,
      notes: 'Добавлено оператором'
    };

    setPlanItems(prev => [...prev, newItem]);
    setNewPlanText('');
    setIsAddingPlan(false);
  };

  // Filter logs
  const filteredLogs = task.logs.filter(log => {
    if (logFilter === 'all') return true;
    return log.type === logFilter;
  });

  const completedPlanCount = planItems.filter(p => p.completed).length;

  return (
    <div className="space-y-4">
      {/* Tab Navigation Strip */}
      <div className="flex items-center gap-1 border-b border-zinc-200 dark:border-zinc-800 overflow-x-auto">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const Icon = tab.icon;

          return (
            <button
              key={tab.id}
              onClick={() => onSelectTab(tab.id)}
              className={`flex items-center gap-2 py-2.5 px-3 text-xs font-medium transition-all border-b-2 -mb-px shrink-0 cursor-pointer ${
                isActive
                  ? 'border-blue-600 text-blue-600 dark:text-blue-400 font-semibold'
                  : 'border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 hover:border-zinc-300 dark:hover:border-zinc-700'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
              {tab.count !== undefined && tab.count > 0 && (
                <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                  isActive 
                    ? 'bg-blue-100 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300' 
                    : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500'
                }`}>
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab Content Panes */}
      <div className="pt-1">
        {/* TAB 1: История (Event log & agent thoughts) */}
        {activeTab === 'history' && (
          <div className="space-y-3">
            {/* Filter Chips & Copy Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-1 p-0.5 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-[11px]">
                <button
                  onClick={() => setLogFilter('all')}
                  className={`px-2 py-0.5 rounded font-medium cursor-pointer ${logFilter === 'all' ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-2xs' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200'}`}
                >
                  Все ({task.logs.length})
                </button>
                <button
                  onClick={() => setLogFilter('thought')}
                  className={`px-2 py-0.5 rounded font-medium cursor-pointer ${logFilter === 'thought' ? 'bg-white dark:bg-zinc-700 text-purple-600 dark:text-purple-400 shadow-2xs' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200'}`}
                >
                  Мысли
                </button>
                <button
                  onClick={() => setLogFilter('bash')}
                  className={`px-2 py-0.5 rounded font-medium cursor-pointer ${logFilter === 'bash' ? 'bg-white dark:bg-zinc-700 text-amber-600 dark:text-amber-400 shadow-2xs' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200'}`}
                >
                  Терминал
                </button>
                <button
                  onClick={() => setLogFilter('check')}
                  className={`px-2 py-0.5 rounded font-medium cursor-pointer ${logFilter === 'check' ? 'bg-white dark:bg-zinc-700 text-emerald-600 dark:text-emerald-400 shadow-2xs' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200'}`}
                >
                  Проверки
                </button>
              </div>

              <button
                onClick={handleCopyHistory}
                className="px-2 py-1 rounded-md border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 text-[11px] font-mono flex items-center gap-1 cursor-pointer"
                title="Скопировать журнал"
              >
                {copiedHistory ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                <span>{copiedHistory ? 'Скопировано' : 'Copy log'}</span>
              </button>
            </div>

            <div className="relative pl-6 space-y-3 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-[2px] before:bg-zinc-200 dark:before:bg-zinc-800">
              {filteredLogs.map((log) => {
                const isExpanded = expandedLogId === log.id;

                return (
                  <div key={log.id} className="relative group">
                    {/* Node Dot */}
                    <div className="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-white dark:bg-zinc-900 border-2 border-blue-500 group-hover:scale-125 transition-transform" />

                    {/* Log Card */}
                    <div className="p-3 rounded-lg border border-zinc-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900/80 shadow-2xs space-y-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded uppercase font-semibold ${
                            log.type === 'thought' 
                              ? 'bg-purple-100 dark:bg-purple-950/50 text-purple-700 dark:text-purple-300'
                              : log.type === 'bash'
                              ? 'bg-amber-100 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300'
                              : log.type === 'check'
                              ? 'bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300'
                              : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'
                          }`}>
                            {log.type}
                          </span>
                          <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                            {log.title}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 text-[11px] text-zinc-400 font-mono">
                          {log.duration && <span>{log.duration}</span>}
                          <span>{log.timestamp}</span>
                        </div>
                      </div>

                      <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                        {log.content}
                      </p>

                      {log.details && (
                        <div className="pt-1">
                          <button
                            onClick={() => toggleLogExpand(log.id)}
                            className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 font-mono cursor-pointer"
                          >
                            <span>{isExpanded ? 'Скрыть вывод консоли' : 'Показать вывод stdout'}</span>
                            {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                          </button>

                          {isExpanded && (
                            <pre className="mt-2 p-2.5 rounded bg-zinc-950 text-zinc-300 font-mono text-[11px] overflow-x-auto border border-zinc-800">
                              {log.details}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* TAB 2: Исходная задача */}
        {activeTab === 'prompt' && (
          <div className="space-y-3">
            <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xs space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                    Техническое задание задачи {task.key}
                  </h3>
                  <span className="text-[11px] text-zinc-500">
                    Целевая ветка: <code className="font-mono text-blue-600 dark:text-blue-400">{task.branch}</code>
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleCopyPRDescription}
                    className="px-2.5 py-1 rounded-md bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-900/60 hover:bg-blue-100 text-xs transition-colors flex items-center gap-1 cursor-pointer font-medium"
                    title="Скопировать сформированное описание для GitHub PR"
                  >
                    {copiedPR ? <Check className="w-3 h-3 text-emerald-500" /> : <Share2 className="w-3 h-3" />}
                    <span>{copiedPR ? 'Скопировано!' : 'Экспорт для PR / Markdown'}</span>
                  </button>

                  <button
                    onClick={handleCopyPrompt}
                    className="px-2.5 py-1 rounded-md border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-300 text-xs transition-colors flex items-center gap-1 cursor-pointer"
                  >
                    {copiedPrompt ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedPrompt ? 'Скопировано' : 'Копировать'}</span>
                  </button>
                </div>
              </div>

              <div className="p-3.5 rounded-lg bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200/80 dark:border-zinc-800 font-mono text-xs text-zinc-800 dark:text-zinc-200 leading-relaxed whitespace-pre-wrap">
                {task.harnessPrompt}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-2 text-xs">
                <div className="p-2 rounded-lg bg-zinc-50 dark:bg-zinc-800/50">
                  <span className="text-[10px] text-zinc-400 block">Модель генерации:</span>
                  <span className="font-semibold text-purple-600 dark:text-purple-400 font-mono">{task.model}</span>
                </div>
                <div className="p-2 rounded-lg bg-zinc-50 dark:bg-zinc-800/50">
                  <span className="text-[10px] text-zinc-400 block">Создана:</span>
                  <span className="font-medium text-zinc-800 dark:text-zinc-200">{task.createdAt}</span>
                </div>
                <div className="p-2 rounded-lg bg-zinc-50 dark:bg-zinc-800/50">
                  <span className="text-[10px] text-zinc-400 block">Ветка разработки:</span>
                  <span className="font-mono text-blue-600 dark:text-blue-400 text-[11px] truncate block">{task.branch}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: План (Interactive Checklist) */}
        {activeTab === 'plan' && (
          <div className="space-y-3">
            <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xs space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                    Декомпозиция плана агента
                  </h3>
                  <span className="text-[11px] text-zinc-500">
                    {completedPlanCount} из {planItems.length} этапов выполнено
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 font-mono">
                    {Math.round((completedPlanCount / Math.max(1, planItems.length)) * 100)}% готовность
                  </span>

                  <button
                    onClick={() => setIsAddingPlan(!isAddingPlan)}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 cursor-pointer font-medium"
                  >
                    <Plus className="w-3 h-3" />
                    <span>Добавить пункт</span>
                  </button>
                </div>
              </div>

              {/* Add Subtask Input Form */}
              {isAddingPlan && (
                <form onSubmit={handleAddPlanItem} className="p-2.5 rounded-lg bg-blue-50/60 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900/60 flex items-center gap-2 text-xs">
                  <input
                    type="text"
                    autoFocus
                    placeholder="Укажите новый шаг или требование к агенту..."
                    value={newPlanText}
                    onChange={(e) => setNewPlanText(e.target.value)}
                    className="flex-1 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-md px-2.5 py-1 text-xs text-zinc-900 dark:text-zinc-100 outline-none"
                  />
                  <button
                    type="submit"
                    className="px-3 py-1 rounded-md bg-blue-600 text-white font-medium hover:bg-blue-700 transition-colors cursor-pointer"
                  >
                    Добавить
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsAddingPlan(false)}
                    className="px-2 py-1 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 cursor-pointer"
                  >
                    Отмена
                  </button>
                </form>
              )}

              {/* Interactive Checklist Items */}
              <div className="space-y-2 pt-1">
                {planItems.map((item, idx) => (
                  <div 
                    key={item.id}
                    onClick={() => togglePlanItem(item.id)}
                    className="p-3 rounded-lg border border-zinc-100 dark:border-zinc-800 bg-zinc-50/70 dark:bg-zinc-950/50 flex items-start gap-3 cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-900 transition-colors group"
                  >
                    <input
                      type="checkbox"
                      checked={item.completed}
                      onChange={() => togglePlanItem(item.id)}
                      className="mt-0.5 rounded text-blue-600 focus:ring-blue-500 cursor-pointer shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      <div className={`text-xs font-medium ${item.completed ? 'line-through text-zinc-400 dark:text-zinc-500' : 'text-zinc-900 dark:text-zinc-100'}`}>
                        {idx + 1}. {item.title}
                      </div>
                      {item.notes && (
                        <div className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5">
                          ↳ {item.notes}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: Изменения (Diff) */}
        {activeTab === 'diff' && (
          <DiffViewer diffs={task.diffs} />
        )}

        {/* TAB 5: Проверки */}
        {activeTab === 'checks' && (
          <div className="space-y-3">
            <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xs space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                    Автоматические проверки качества и сборки
                  </h3>
                  <span className="text-[11px] text-zinc-500">
                    Все верификационные тесты пройдены без ошибок
                  </span>
                </div>
                <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 font-semibold">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  Checks Passed
                </span>
              </div>

              <div className="space-y-2">
                {task.checks.map((check) => (
                  <div
                    key={check.id}
                    className="p-3 rounded-lg border border-zinc-100 dark:border-zinc-800 bg-zinc-50/80 dark:bg-zinc-950/60 flex items-start justify-between gap-3 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
                        <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                          {check.name}
                        </span>
                      </div>
                      <div className="font-mono text-[11px] text-zinc-500 pl-6">
                        $ {check.command}
                      </div>
                      <div className="text-[11px] text-emerald-600 dark:text-emerald-400 pl-6">
                        {check.summary}
                      </div>
                    </div>

                    <span className="text-[10px] font-mono text-zinc-400 shrink-0">
                      {check.duration}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 6: Ревью */}
        {activeTab === 'review' && (
          <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xs space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                  Отчёт автоматического и человеческого ревью
                </h3>
                <span className="text-[11px] text-zinc-500">
                  Аудитор: {task.reviewNotes.reviewer}
                </span>
              </div>
              <div className="text-right">
                <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400 font-mono">
                  {task.reviewNotes.score}/100
                </span>
                <span className="text-[10px] text-zinc-400 block">Quality score</span>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-emerald-50/50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 space-y-1.5 text-xs">
              <div className="font-semibold text-emerald-900 dark:text-emerald-200">
                Ключевые заключения:
              </div>
              {task.reviewNotes.feedback.map((item, idx) => (
                <div key={idx} className="flex items-start gap-2 text-zinc-700 dark:text-zinc-300 text-[11px]">
                  <span className="text-emerald-600 dark:text-emerald-400 mt-0.5">•</span>
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
