import React, { useState, useEffect } from 'react';
import { 
  Monitor, 
  Smartphone, 
  Tablet, 
  RotateCw, 
  ExternalLink, 
  Play, 
  Square, 
  CheckCircle2, 
  Terminal, 
  Maximize2,
  Minimize2,
  Code2,
  AlertCircle,
  Sparkles,
  Columns,
  X,
  Laptop
} from 'lucide-react';
import { Task } from '../types';

interface RuntimePreviewProps {
  task: Task;
}

export function RuntimePreview({ task }: RuntimePreviewProps) {
  const [activeVersion, setActiveVersion] = useState<'verified' | 'working' | 'split'>('working');
  const [viewportMode, setViewportMode] = useState<'fluid' | 'desktop' | 'tablet' | 'mobile'>('fluid');
  const [isRunning, setIsRunning] = useState<boolean>(task.runtimeInfo.configured);
  const [isReloading, setIsReloading] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showConsole, setShowConsole] = useState(false);

  const handleToggleRuntime = () => {
    setIsRunning(!isRunning);
  };

  const handleReload = () => {
    setIsReloading(true);
    setTimeout(() => setIsReloading(false), 600);
  };

  // Keyboard shortcut ESC to exit fullscreen
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  // Width calculation based on viewport mode
  const getViewportWidthClass = () => {
    if (viewportMode === 'mobile') return 'max-w-[390px]';
    if (viewportMode === 'tablet') return 'max-w-[768px]';
    if (viewportMode === 'desktop') return 'max-w-[1200px]';
    return 'w-full';
  };

  return (
    <>
      {/* Standard In-Page Preview Card */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 shadow-2xs space-y-3">
        {/* Header and Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-zinc-100 dark:border-zinc-800">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                Просмотр приложения
              </span>
              <span className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium ${
                isRunning 
                  ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300'
                  : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-400'}`} />
                {isRunning ? 'Runtime активен' : 'Runtime остановлен'}
              </span>
            </div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              {isRunning 
                ? `Next.js 15 dev-сервер запущен на порту ${task.runtimeInfo.port || 3000}`
                : 'Задача может быть запущена в изолированном контейнере для проверки UI.'
              }
            </p>
          </div>

          {/* Version Switcher & Fullscreen Action */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <button
              onClick={() => setActiveVersion('verified')}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeVersion === 'verified'
                  ? 'bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 shadow-2xs'
                  : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200'
              }`}
            >
              Показать проверенную версию
            </button>

            <button
              onClick={() => setActiveVersion('working')}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeVersion === 'working'
                  ? 'bg-blue-600 text-white shadow-2xs'
                  : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200'
              }`}
            >
              Показать рабочую версию
            </button>

            <button
              onClick={handleReload}
              className="px-2.5 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-300 text-xs transition-colors flex items-center gap-1"
              title="Перезапустить окружение"
            >
              <RotateCw className={`w-3 h-3 ${isReloading ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">Повторить</span>
            </button>

            {/* FULLSCREEN TRIGGER BUTTON */}
            <button
              onClick={() => setIsFullscreen(true)}
              className="px-2.5 py-1.5 rounded-lg bg-zinc-100 dark:bg-zinc-800 hover:bg-blue-50 dark:hover:bg-blue-950/40 text-zinc-700 dark:text-zinc-300 hover:text-blue-600 dark:hover:text-blue-400 text-xs font-medium border border-zinc-200 dark:border-zinc-700/80 transition-colors flex items-center gap-1.5"
              title="Открыть предпросмотр на весь экран"
            >
              <Maximize2 className="w-3.5 h-3.5" />
              <span>Full Screen</span>
            </button>
          </div>
        </div>

        {/* In-Page Interactive Screen Simulation */}
        {isRunning ? (
          <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden bg-zinc-50 dark:bg-zinc-950">
            {/* Mock Browser Topbar */}
            <div className="px-3 py-2 bg-zinc-100/90 dark:bg-zinc-900/90 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                </div>

                {/* URL Address Pill */}
                <div className="flex-1 max-w-md mx-2 px-2.5 py-1 rounded-md bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-[11px] font-mono text-zinc-600 dark:text-zinc-300 flex items-center justify-between truncate">
                  <span className="truncate">
                    http://localhost:{task.runtimeInfo.port || 3000}/?version={activeVersion}
                  </span>
                  <span className="text-[10px] text-zinc-400 ml-1">
                    {activeVersion === 'working' ? 'HEAD' : 'BASE'}
                  </span>
                </div>
              </div>

              {/* Viewport size toggles & fullview */}
              <div className="flex items-center gap-1 text-zinc-500">
                <button
                  onClick={() => setViewportMode('desktop')}
                  className={`p-1 rounded ${viewportMode === 'desktop' ? 'bg-zinc-200 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100' : 'hover:text-zinc-800'}`}
                  title="Десктоп"
                >
                  <Monitor className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setViewportMode('mobile')}
                  className={`p-1 rounded ${viewportMode === 'mobile' ? 'bg-zinc-200 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100' : 'hover:text-zinc-800'}`}
                  title="Мобильный"
                >
                  <Smartphone className="w-3.5 h-3.5" />
                </button>
                <button 
                  onClick={handleReload}
                  className="p-1 hover:text-zinc-800 dark:hover:text-zinc-200"
                  title="Перезагрузить страницу"
                >
                  <RotateCw className={`w-3.5 h-3.5 ${isReloading ? 'animate-spin text-blue-500' : ''}`} />
                </button>
                <button
                  onClick={() => setIsFullscreen(true)}
                  className="p-1 hover:text-blue-600 dark:hover:text-blue-400 transition-colors ml-1"
                  title="Развернуть на весь экран"
                >
                  <Maximize2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Sample Rendered UI Body */}
            <div className={`p-4 flex justify-center bg-zinc-100/50 dark:bg-zinc-950/70 transition-all ${viewportMode === 'mobile' ? 'max-w-sm mx-auto' : 'w-full'}`}>
              <div className="w-full bg-white dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-800 p-4 shadow-sm space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-zinc-100 dark:border-zinc-800">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded bg-blue-600 text-white font-bold text-[10px] flex items-center justify-center">
                      tw
                    </div>
                    <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">
                      tw-web preview ({activeVersion === 'working' ? 'рабочая версия' : 'проверенная версия'})
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-1.5 py-0.5 rounded">
                    200 OK
                  </span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="h-6 bg-zinc-100 dark:bg-zinc-800 rounded flex items-center px-2 text-[11px] text-zinc-600 dark:text-zinc-400 justify-between">
                    <span>Компонент PipelineStepper.tsx</span>
                    <span className="text-blue-500 font-mono">mounted</span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div className="p-2 rounded bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-100 dark:border-zinc-800">
                      <span className="text-zinc-400 block text-[10px]">Статус сборки:</span>
                      <span className="font-semibold text-zinc-800 dark:text-zinc-200">Next.js Ready</span>
                    </div>
                    <div className="p-2 rounded bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-100 dark:border-zinc-800">
                      <span className="text-zinc-400 block text-[10px]">Hot Reload:</span>
                      <span className="font-semibold text-emerald-600 dark:text-emerald-400">Слушает порт :3000</span>
                    </div>
                  </div>

                  <div className="p-2.5 rounded bg-blue-50/60 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/40 text-[11px] text-blue-900 dark:text-blue-200">
                    {activeVersion === 'working' ? (
                      <span>★ Отображается рабочая версия агента (ветка <b>{task.branch}</b>). Добавлены новые стили shadcn и переработана сетка.</span>
                    ) : (
                      <span>Отображается исходная базовая версия (ветка <b>main</b>).</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="p-6 rounded-lg border border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-950/40 text-center space-y-2">
            <Monitor className="w-8 h-8 mx-auto text-zinc-400" />
            <div className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">
              Просмотр отсутствует
            </div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-md mx-auto">
              Задача не использует настроенный runtime по умолчанию. Вы можете запустить изолированное окружение в один клик.
            </p>
            <div className="pt-2">
              <button
                onClick={handleToggleRuntime}
                className="px-3.5 py-1.5 rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 hover:bg-zinc-800 dark:hover:bg-zinc-200 text-xs font-medium transition-colors inline-flex items-center gap-1.5"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Запустить локальный preview рантайм</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ================= FULLSCREEN OVERLAY MODAL ================= */}
      {isFullscreen && (
        <div className="fixed inset-0 z-50 bg-zinc-950/95 backdrop-blur-md flex flex-col animate-in fade-in-50">
          {/* Fullscreen Navigation Bar */}
          <div className="h-14 border-b border-zinc-800 px-4 flex items-center justify-between text-zinc-100 shrink-0 bg-zinc-900">
            {/* Left: Task identifier & live status */}
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-blue-600 text-white font-bold text-xs flex items-center justify-center">
                tw
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-blue-400">{task.key}</span>
                  <span className="text-xs font-semibold text-zinc-200 truncate max-w-sm sm:max-w-md">
                    {task.title}
                  </span>
                </div>
                <div className="text-[11px] text-zinc-400 flex items-center gap-2">
                  <span>Runtime: Next.js :3000</span>
                  <span>·</span>
                  <span className="text-emerald-400 font-medium">● 200 OK</span>
                </div>
              </div>
            </div>

            {/* Center: Version switcher (Working vs Verified vs Split-View!) */}
            <div className="hidden md:flex items-center p-1 rounded-lg bg-zinc-800 border border-zinc-700/60 text-xs">
              <button
                onClick={() => setActiveVersion('verified')}
                className={`px-3 py-1 rounded-md transition-all ${activeVersion === 'verified' ? 'bg-zinc-700 text-white font-medium shadow-xs' : 'text-zinc-400 hover:text-zinc-200'}`}
              >
                Проверенная версия (main)
              </button>
              <button
                onClick={() => setActiveVersion('working')}
                className={`px-3 py-1 rounded-md transition-all ${activeVersion === 'working' ? 'bg-blue-600 text-white font-medium shadow-xs' : 'text-zinc-400 hover:text-zinc-200'}`}
              >
                Рабочая версия ({task.branch})
              </button>
              <button
                onClick={() => setActiveVersion('split')}
                className={`px-3 py-1 rounded-md transition-all flex items-center gap-1.5 ${activeVersion === 'split' ? 'bg-purple-600 text-white font-medium shadow-xs' : 'text-zinc-400 hover:text-zinc-200'}`}
              >
                <Columns className="w-3.5 h-3.5" />
                <span>Split View (Сравнение)</span>
              </button>
            </div>

            {/* Right: Viewport mode, Console toggle, Close */}
            <div className="flex items-center gap-2">
              {/* Viewport size selectors */}
              <div className="flex items-center p-1 rounded-lg bg-zinc-800 border border-zinc-700/60 text-zinc-400">
                <button
                  onClick={() => setViewportMode('fluid')}
                  className={`p-1.5 rounded ${viewportMode === 'fluid' ? 'bg-zinc-700 text-white' : 'hover:text-zinc-200'}`}
                  title="Во всю ширину экрана"
                >
                  <Monitor className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewportMode('desktop')}
                  className={`p-1.5 rounded ${viewportMode === 'desktop' ? 'bg-zinc-700 text-white' : 'hover:text-zinc-200'}`}
                  title="Десктоп (1200px)"
                >
                  <Laptop className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewportMode('tablet')}
                  className={`p-1.5 rounded ${viewportMode === 'tablet' ? 'bg-zinc-700 text-white' : 'hover:text-zinc-200'}`}
                  title="Планшет (768px)"
                >
                  <Tablet className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewportMode('mobile')}
                  className={`p-1.5 rounded ${viewportMode === 'mobile' ? 'bg-zinc-700 text-white' : 'hover:text-zinc-200'}`}
                  title="Мобильный (390px)"
                >
                  <Smartphone className="w-4 h-4" />
                </button>
              </div>

              {/* Console Toggle */}
              <button
                onClick={() => setShowConsole(!showConsole)}
                className={`p-2 rounded-lg border text-xs flex items-center gap-1.5 transition-colors ${
                  showConsole 
                    ? 'bg-zinc-800 border-zinc-600 text-white' 
                    : 'border-zinc-700 text-zinc-400 hover:text-zinc-200'
                }`}
                title="Логи терминала runtime"
              >
                <Terminal className="w-4 h-4" />
                <span className="hidden sm:inline">Логи</span>
              </button>

              {/* Close / Minimize */}
              <button
                onClick={() => setIsFullscreen(false)}
                className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white transition-colors"
                title="Выйти из полноэкранного режима (Esc)"
              >
                <Minimize2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Fullscreen Body Canvas */}
          <div className="flex-1 overflow-auto p-4 md:p-6 flex flex-col items-center justify-start bg-zinc-950">
            {activeVersion === 'split' ? (
              /* SPLIT VIEW MODE: COMPARE BASELINE VS WORKING SIDE-BY-SIDE */
              <div className="w-full h-full grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Left: Verified Version */}
                <div className="flex flex-col h-full rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden shadow-xl">
                  <div className="px-4 py-2 bg-zinc-800/80 border-b border-zinc-700 flex items-center justify-between text-xs text-zinc-300">
                    <span className="font-semibold text-zinc-100 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-zinc-400" />
                      Проверенная версия (main)
                    </span>
                    <span className="font-mono text-[11px] text-zinc-400">hash: c4b890f</span>
                  </div>
                  <div className="flex-1 p-6 bg-zinc-900 overflow-auto space-y-4">
                    <div className="p-4 rounded-lg bg-zinc-800/60 border border-zinc-700 text-xs text-zinc-300">
                      <h4 className="font-bold text-zinc-100 mb-2">tw-web (До правок агента)</h4>
                      <p className="text-zinc-400 mb-3">Старая монолитная структура без shadcn токенов и разделения на 5 фаз.</p>
                      <div className="h-8 bg-zinc-700/60 rounded flex items-center px-3 text-zinc-400">
                        Старый интерфейс панели
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right: Working Version (Agent modified) */}
                <div className="flex flex-col h-full rounded-xl border border-blue-600/40 bg-zinc-900 overflow-hidden shadow-xl ring-1 ring-blue-500/30">
                  <div className="px-4 py-2 bg-blue-950/60 border-b border-blue-900/60 flex items-center justify-between text-xs text-blue-200">
                    <span className="font-semibold text-white flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                      Рабочая версия ({task.branch})
                    </span>
                    <span className="font-mono text-[11px] text-blue-300">hash: e6e4fe4 (HEAD)</span>
                  </div>
                  <div className="flex-1 p-6 bg-zinc-900 overflow-auto space-y-4">
                    <div className="p-4 rounded-lg bg-blue-950/30 border border-blue-900/50 text-xs text-zinc-200 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="font-bold text-white">tw-web (Результат автономного агента)</h4>
                        <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono text-[10px]">
                          +162 / -12 строк
                        </span>
                      </div>
                      <p className="text-zinc-300">
                        Внедрена система shadcn/ui, компактные полоски задач, 5-этапный интерактивный PipelineStepper и консоль рантайма.
                      </p>
                      <div className="p-3 bg-zinc-800/80 rounded-lg border border-zinc-700 space-y-2">
                        <div className="text-[11px] text-blue-400 font-semibold">Новый компонент PipelineStepper:</div>
                        <div className="grid grid-cols-5 gap-1 text-[10px] text-center">
                          <span className="p-1 rounded bg-emerald-900/50 text-emerald-300">План</span>
                          <span className="p-1 rounded bg-emerald-900/50 text-emerald-300">Код</span>
                          <span className="p-1 rounded bg-emerald-900/50 text-emerald-300">Тесты</span>
                          <span className="p-1 rounded bg-emerald-900/50 text-emerald-300">Ревью</span>
                          <span className="p-1 rounded bg-blue-900/60 text-blue-300 font-bold">Приёмка</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              /* SINGLE VIEW MODE: RESPONSIVE CANVAS */
              <div className={`h-full flex flex-col rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden shadow-2xl transition-all ${getViewportWidthClass()}`}>
                {/* Browser Address Bar */}
                <div className="px-4 py-2 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-full bg-red-500/80" />
                      <span className="w-3 h-3 rounded-full bg-amber-500/80" />
                      <span className="w-3 h-3 rounded-full bg-emerald-500/80" />
                    </div>
                    <div className="flex-1 max-w-xl mx-3 px-3 py-1 rounded-md bg-zinc-950 border border-zinc-800 text-zinc-300 font-mono text-[11px] flex items-center justify-between">
                      <span>http://localhost:3000/?version={activeVersion}</span>
                      <span className="text-[10px] text-zinc-500 font-sans">
                        {viewportMode.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  <button
                    onClick={handleReload}
                    className="p-1 text-zinc-400 hover:text-white transition-colors"
                    title="Перезагрузить"
                  >
                    <RotateCw className={`w-3.5 h-3.5 ${isReloading ? 'animate-spin text-blue-500' : ''}`} />
                  </button>
                </div>

                {/* Simulated Screen Body */}
                <div className="flex-1 p-6 overflow-auto bg-zinc-950 space-y-4 text-zinc-100">
                  <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/80 max-w-4xl mx-auto space-y-4">
                    <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-blue-600 text-white font-bold text-xs flex items-center justify-center">
                          tw
                        </div>
                        <div>
                          <h3 className="text-sm font-bold text-white">tw-web: Полноэкранный предпросмотр</h3>
                          <span className="text-[11px] text-zinc-400">
                            Ветка: {activeVersion === 'working' ? task.branch : 'main'}
                          </span>
                        </div>
                      </div>
                      <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono">
                        Active Sandbox :3000
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                      <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800">
                        <span className="text-zinc-500 block text-[10px]">Кодовая база:</span>
                        <span className="font-semibold text-zinc-200">Next.js 15 App Router</span>
                      </div>
                      <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800">
                        <span className="text-zinc-500 block text-[10px]">Дизайн-система:</span>
                        <span className="font-semibold text-zinc-200">shadcn/ui + Tailwind v4</span>
                      </div>
                      <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800">
                        <span className="text-zinc-500 block text-[10px]">Статус компиляции:</span>
                        <span className="font-semibold text-emerald-400">Compiled in 1.4s</span>
                      </div>
                    </div>

                    <div className="p-4 rounded-lg bg-zinc-950 border border-zinc-800 font-mono text-xs text-zinc-300 leading-relaxed">
                      <div className="text-blue-400 mb-2 font-bold font-sans">Смонтированные компоненты страницы:</div>
                      <div>• &lt;Sidebar /&gt; — боковое меню и док с переключением воркера</div>
                      <div>• &lt;TaskList density=&quot;compact&quot; /&gt; — узкие полоски задач</div>
                      <div>• &lt;PipelineStepper stages=&quot;5&quot; /&gt; — 5-этапный стейт-трекер</div>
                      <div>• &lt;ActionBanner /&gt; — кнопки подтверждения и слияния</div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Collapsible Console Drawer */}
          {showConsole && (
            <div className="h-44 border-t border-zinc-800 bg-zinc-950 p-3 shrink-0 flex flex-col font-mono text-[11px]">
              <div className="flex items-center justify-between pb-1.5 border-b border-zinc-900 text-zinc-400 text-xs">
                <span className="flex items-center gap-1.5 text-zinc-200">
                  <Terminal className="w-3.5 h-3.5 text-blue-400" />
                  <span>Next.js dev-server terminal stdout</span>
                </span>
                <span className="text-[10px] text-zinc-500">Ctrl+C to stop</span>
              </div>
              <div className="flex-1 overflow-y-auto pt-2 space-y-1 text-zinc-300">
                <div className="text-zinc-500">▲ Next.js 15.1.0 - Local: http://localhost:3000</div>
                <div className="text-emerald-400">✓ Ready in 1120ms</div>
                <div className="text-zinc-400">GET / 200 in 48ms</div>
                <div className="text-zinc-400">GET /src/components/PipelineStepper.tsx 200 in 12ms</div>
                <div className="text-blue-400">ℹ [Fast Refresh] rebuilding client chunks for task view...</div>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
