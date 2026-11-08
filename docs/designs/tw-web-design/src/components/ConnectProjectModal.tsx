import React, { useState } from 'react';
import { 
  X, 
  FolderGit2, 
  GitBranch, 
  Check, 
  Plus, 
  Terminal,
  FolderOpen
} from 'lucide-react';
import { Project } from '../types';

interface ConnectProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConnectProject: (newProject: Project) => void;
}

export function ConnectProjectModal({ isOpen, onClose, onConnectProject }: ConnectProjectModalProps) {
  const [name, setName] = useState('');
  const [repoPath, setRepoPath] = useState('');
  const [branch, setBranch] = useState('main');
  const [description, setDescription] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !repoPath.trim()) return;

    const newProject: Project = {
      id: Math.random().toString(36).substring(2, 10),
      name,
      description: description || 'Локальный репозиторий проекта',
      repoPath,
      activeBranch: branch || 'main',
      totalTasks: 0,
      pendingTasks: 0,
      workerRunning: true,
      workerPort: 47834,
      lastSync: 'Только что'
    };

    onConnectProject(newProject);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in-50">
      <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl max-w-lg w-full p-5 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 p-1 rounded-lg"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 mb-1">
          <div className="w-7 h-7 rounded-lg bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 flex items-center justify-center">
            <FolderGit2 className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
            Подключить локальный проект
          </h2>
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-4">
          Укажите путь к локальному git-репозиторию для интеграции с агентским harness.
        </p>

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="block text-xs font-semibold text-zinc-800 dark:text-zinc-200 mb-1">
              Название проекта
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="tw-mobile, api-gateway..."
              className="w-full text-xs px-3 py-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-zinc-800 dark:text-zinc-200 mb-1">
              Абсолютный путь к репозиторию
            </label>
            <div className="relative">
              <FolderOpen className="w-3.5 h-3.5 absolute left-3 top-2.5 text-zinc-400" />
              <input
                type="text"
                required
                value={repoPath}
                onChange={(e) => setRepoPath(e.target.value)}
                placeholder="~/dev/my-project или /Users/dev/repos/tw-web"
                className="w-full text-xs pl-8 pr-3 py-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                Основная ветка
              </label>
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main или master"
                className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                Описание (опционально)
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Микросервис авторизации..."
                className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-100 dark:border-zinc-800">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              Отмена
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs hover:shadow transition-all"
            >
              Подключить
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
