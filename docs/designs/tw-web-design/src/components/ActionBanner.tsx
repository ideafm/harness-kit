import React, { useState } from 'react';
import { 
  CheckCircle2, 
  AlertCircle, 
  RotateCcw, 
  GitPullRequest, 
  ChevronDown, 
  ChevronUp, 
  ExternalLink, 
  Terminal, 
  Copy, 
  Check, 
  Sparkles,
  ArrowRight,
  Send
} from 'lucide-react';
import { Task } from '../types';

interface ActionBannerProps {
  task: Task;
  onApplyTask: (taskId: string) => void;
  onRequestChanges: (taskId: string, feedback: string) => void;
  onSelectTab: (tabId: string) => void;
}

export function ActionBanner({
  task,
  onApplyTask,
  onRequestChanges,
  onSelectTab
}: ActionBannerProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [copiedGit, setCopiedGit] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [appliedSuccess, setAppliedSuccess] = useState(task.status === 'accepted_applied');

  const handleApply = () => {
    setIsApplying(true);
    setTimeout(() => {
      setIsApplying(false);
      setAppliedSuccess(true);
      onApplyTask(task.id);
    }, 700);
  };

  const handleCopyGit = () => {
    navigator.clipboard.writeText(`git checkout -b ${task.branch} && git pull origin ${task.branch}`);
    setCopiedGit(true);
    setTimeout(() => setCopiedGit(false), 2000);
  };

  const handleSubmitFeedback = (e: React.FormEvent) => {
    e.preventDefault();
    if (!feedbackText.trim()) return;
    onRequestChanges(task.id, feedbackText);
    setFeedbackText('');
    setShowFeedbackModal(false);
  };

  return (
    <div className="space-y-3">
      {/* Primary Action Card: Что требуется от вас */}
      <div className={`rounded-xl border p-4.5 transition-all shadow-xs ${
        appliedSuccess 
          ? 'bg-emerald-50/60 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/60'
          : 'bg-zinc-50/80 dark:bg-zinc-900/60 border-zinc-200 dark:border-zinc-800'
      }`}>
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-1.5 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                Что требуется от вас
              </span>
              <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${
                appliedSuccess 
                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-300'
                  : task.status === 'in_progress'
                  ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-300 animate-pulse'
                  : 'bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-300'
              }`}>
                {appliedSuccess 
                  ? 'Применение подтверждено' 
                  : task.status === 'in_progress'
                  ? 'Выполняется агентом'
                  : 'Требуется подтверждение'
                }
              </span>
            </div>

            <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {appliedSuccess 
                ? 'Изменения успешно применены к рабочей ветке'
                : task.status === 'in_progress'
                ? `Агент ${task.model} выполняет этап «${task.currentStageLabel}»...`
                : 'Результат задачи принят. Подтвердите применение в git или запросите доработку.'
              }
            </div>

            <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
              {appliedSuccess
                ? `Ветка ${task.branch} смерджена в main. Все артефакты синхронизированы.`
                : task.status === 'in_progress'
                ? 'Изолированный контейнер воркера запущен. Агент вносит изменения в кодовую базу и запускает верификационные тесты.'
                : 'Автономный агент успешно выполнил все этапы пайплайна. Все проверки типов tsc и ESLint пройдены без ошибок.'
              }
            </p>

            {/* Toggle Details Disclosure */}
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline pt-1 font-medium cursor-pointer"
            >
              <span>{showDetails ? 'Скрыть подробности результата' : 'Подробности результата'}</span>
              {showDetails ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>

          {/* Action Button Strip */}
          <div className="flex flex-wrap sm:flex-col items-stretch gap-2 shrink-0">
            {!appliedSuccess ? (
              <>
                <button
                  onClick={handleApply}
                  disabled={isApplying}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs hover:shadow transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {isApplying ? (
                    <>
                      <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                      <span>Применение...</span>
                    </>
                  ) : (
                    <>
                      <Check className="w-3.5 h-3.5" />
                      <span>Подтвердить и применить</span>
                    </>
                  )}
                </button>

                <button
                  onClick={() => setShowFeedbackModal(true)}
                  className="px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
                >
                  <RotateCcw className="w-3.5 h-3.5 text-zinc-500" />
                  <span>Запросить доработку</span>
                </button>
              </>
            ) : (
              <div className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                <CheckCircle2 className="w-4 h-4" />
                <span>Применено в Git</span>
              </div>
            )}

            <button
              onClick={handleCopyGit}
              className="px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-800/80 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-400 text-xs font-mono transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
              title="Скопировать команду git checkout"
            >
              {copiedGit ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copiedGit ? 'Скопировано!' : 'git branch'}</span>
            </button>
          </div>
        </div>

        {/* Collapsible Details Body */}
        {showDetails && (
          <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-800 text-xs space-y-2">
            <div className="p-3 rounded-lg bg-white dark:bg-zinc-950/60 border border-zinc-200/80 dark:border-zinc-800 text-zinc-700 dark:text-zinc-300 font-mono text-[11px] leading-relaxed">
              <div className="font-semibold text-zinc-900 dark:text-zinc-100 mb-1 font-sans">
                Сводка выполнения задачи {task.key}:
              </div>
              <div>• Ветка: <span className="text-blue-600 dark:text-blue-400">{task.branch}</span></div>
              <div>• LLM Модель: <span className="text-purple-600 dark:text-purple-400">{task.model}</span></div>
              <div>• Пройденные проверки: tsc (0 errors), eslint (0 warnings), vitest (12 passed)</div>
              <div>• Созданные / измененные файлы: 2 файла (+162 -12 строк)</div>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button 
                onClick={() => onSelectTab('diff')} 
                className="text-xs text-blue-600 dark:text-blue-400 font-medium hover:underline flex items-center gap-1"
              >
                <span>Смотреть git diff (+162)</span>
                <ArrowRight className="w-3 h-3" />
              </button>
              <button 
                onClick={() => onSelectTab('history')} 
                className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 hover:underline flex items-center gap-1"
              >
                <span>История логов воркера</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal for Requesting Changes / Agent Redo */}
      {showFeedbackModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4">
          <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl max-w-lg w-full p-5 shadow-xl animate-in fade-in-50 zoom-in-95">
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
              <RotateCcw className="w-4 h-4 text-blue-600" />
              <span>Запросить доработку у агента</span>
            </h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
              Укажите, что именно нужно исправить или дополнить. Агент перезапустит этап разработки с сохранением контекста.
            </p>

            <form onSubmit={handleSubmitFeedback} className="mt-4 space-y-3">
              <textarea
                value={feedbackText}
                onChange={(e) => setFeedbackText(e.target.value)}
                placeholder="Например: добавь валидацию пустых полей и измени цвет кнопки на синий..."
                rows={4}
                autoFocus
                className="w-full text-xs p-3 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />

              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowFeedbackModal(false)}
                  className="px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={!feedbackText.trim()}
                  className="px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Отправить агенту</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
