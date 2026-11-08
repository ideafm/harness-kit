import React, { useState } from 'react';
import { 
  X, 
  Sparkles, 
  Bot, 
  GitBranch, 
  Send, 
  Layers, 
  FileCode, 
  Cpu, 
  Check 
} from 'lucide-react';
import { Task } from '../types';

interface NewTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateTask: (newTask: Partial<Task>) => void;
  activeBranch: string;
}

export function NewTaskModal({ isOpen, onClose, onCreateTask, activeBranch }: NewTaskModalProps) {
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('claude-3-7-sonnet');
  const [branch, setBranch] = useState(activeBranch);
  const [autoStart, setAutoStart] = useState(true);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !prompt.trim()) return;

    onCreateTask({
      title,
      harnessPrompt: prompt,
      model,
      branch: branch || 'feature/new-agent-task',
      description: prompt.slice(0, 160) + '...'
    });

    onClose();
  };

  const handleApplyPreset = (presetTitle: string, presetPrompt: string) => {
    setTitle(presetTitle);
    setPrompt(presetPrompt);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in-50">
      <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl max-w-xl w-full p-5 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 p-1 rounded-lg"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 mb-1">
          <div className="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center">
            <Sparkles className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
            Создать задачу для автономного агента
          </h2>
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-4">
          Агент выполнит полный цикл разработки: спланирует изменения, напишет код, прогонит тесты и подготовит патч.
        </p>

        {/* Quick Prompt Presets */}
        <div className="mb-4">
          <span className="text-[11px] font-medium text-zinc-400 block mb-1.5">
            Быстрые шаблоны:
          </span>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => handleApplyPreset(
                'Редизайн шапки и хлебных крошек',
                'Переработай шапку tw-web: добавь статус воркера, быстрый переключатель веток git и кнопку синхронизации.'
              )}
              className="text-[11px] px-2.5 py-1 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors"
            >
              UI Редизайн
            </button>
            <button
              type="button"
              onClick={() => handleApplyPreset(
                'Покрытие unit-тестами для модуля stepper',
                'Напиши тесты Vitest для src/components/PipelineStepper.tsx с проверкой всех 5 этапов пайплайна и рендера иконок.'
              )}
              className="text-[11px] px-2.5 py-1 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors"
            >
              Написание тестов
            </button>
            <button
              type="button"
              onClick={() => handleApplyPreset(
                'Фикс утечки памяти при поллинге статуса воркера',
                'Оберни вызовы таймеров в useEffect с функцией очистки clearInterval и добавь abortController для сетевых запросов.'
              )}
              className="text-[11px] px-2.5 py-1 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors"
            >
              Быстрый багфикс
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5">
          {/* Title */}
          <div>
            <label className="block text-xs font-semibold text-zinc-800 dark:text-zinc-200 mb-1">
              Название задачи
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Например: Добавление фильтрации задач по тегам..."
              className="w-full text-xs px-3 py-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Prompt */}
          <div>
            <label className="block text-xs font-semibold text-zinc-800 dark:text-zinc-200 mb-1">
              Инструкция для агента (Prompt)
            </label>
            <textarea
              required
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Подробно опишите, что должен сделать агент, какие файлы затронуть, какие проверки запустить..."
              className="w-full text-xs p-3 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
            />
          </div>

          {/* Model & Branch selectors */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                Модель рассуждений
              </label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="claude-3-7-sonnet">Claude 3.7 Sonnet (High Reasoning)</option>
                <option value="gemini-2.0-flash">Gemini 2.0 Flash (Fast Execution)</option>
                <option value="gpt-4o">GPT-4o (Standard Code)</option>
                <option value="local-qwen-2.5-coder">Local Qwen 2.5 Coder (Offline)</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                Целевая ветка Git
              </label>
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="feature/branch-name"
                className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Auto Start Checkbox */}
          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="autoStart"
              checked={autoStart}
              onChange={(e) => setAutoStart(e.target.checked)}
              className="rounded text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="autoStart" className="text-xs text-zinc-700 dark:text-zinc-300 select-none cursor-pointer">
              Запустить выполнение сразу через воркер harness
            </label>
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-100 dark:border-zinc-800">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              Отмена
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs hover:shadow transition-all flex items-center gap-1.5"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Создать и отправить</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
