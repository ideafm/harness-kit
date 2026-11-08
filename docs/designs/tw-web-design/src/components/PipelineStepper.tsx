import React from 'react';
import { 
  FileText, 
  Code2, 
  CheckSquare, 
  Eye, 
  ShieldCheck, 
  Check, 
  Clock, 
  Sparkles,
  ChevronRight,
  ArrowRight
} from 'lucide-react';
import { Task, TaskStage } from '../types';

interface PipelineStepperProps {
  task: Task;
  onSelectStage?: (stage: TaskStage) => void;
  selectedStage?: TaskStage;
}

const STAGES_CONFIG: {
  id: TaskStage;
  label: string;
  icon: React.ElementType;
}[] = [
  { id: 'plan', label: 'План', icon: FileText },
  { id: 'dev', label: 'Разработка', icon: Code2 },
  { id: 'checks', label: 'Проверки', icon: CheckSquare },
  { id: 'review', label: 'Ревью', icon: Eye },
  { id: 'acceptance', label: 'Приёмка', icon: ShieldCheck }
];

export function PipelineStepper({ task, onSelectStage, selectedStage }: PipelineStepperProps) {
  const currentStageIndex = STAGES_CONFIG.findIndex(s => s.id === task.currentStage);
  const progressPercent = Math.round((currentStageIndex / (STAGES_CONFIG.length - 1)) * 100);

  return (
    <div className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 shadow-2xs space-y-4">
      {/* Top Header: Title, Progress % and Current Stage */}
      <div className="flex items-center justify-between pb-2 border-b border-zinc-100 dark:border-zinc-800 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">
            Пайплайн автономной разработки
          </span>
          <span className="text-[11px] font-mono text-zinc-400">
            (5 фаз)
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-zinc-500 dark:text-zinc-400">
            Готовность: <span className="font-semibold text-blue-600 dark:text-blue-400">{progressPercent}%</span>
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 font-medium text-[11px]">
            <ShieldCheck className="w-3 h-3 text-blue-600" />
            <span>{task.currentStageLabel}</span>
          </span>
        </div>
      </div>

      {/* Main Stepper Track with Mathematically Bound Connector Line */}
      <div className="w-full">
        {/* Row of Circles with Connector Line strictly between circle 1 center and circle 5 center */}
        <div className="relative flex items-center justify-between w-full h-9">
          {/* Dedicated Connector Track Container (from center of first 36px circle to center of last 36px circle) */}
          <div className="absolute left-[18px] right-[18px] top-1/2 -translate-y-1/2 h-[2px] z-0 pointer-events-none overflow-hidden">
            {/* Background inactive track line */}
            <div className="w-full h-full bg-zinc-200 dark:bg-zinc-800" />

            {/* Dynamic active line strictly confined within track bounds */}
            <div 
              className="absolute left-0 top-0 h-full bg-blue-600 dark:bg-blue-500 transition-all duration-300"
              style={{
                width: `${(currentStageIndex / (STAGES_CONFIG.length - 1)) * 100}%`
              }}
            />
          </div>

          {/* Stepper Circle Buttons */}
          {STAGES_CONFIG.map((stage, idx) => {
            const stageData = task.stages[stage.id];
            const isCurrent = task.currentStage === stage.id;
            const isPassed = idx < currentStageIndex || stageData?.status === 'completed';
            const isSelected = selectedStage === stage.id;
            const Icon = stage.icon;

            return (
              <button
                key={stage.id}
                onClick={() => onSelectStage?.(stage.id)}
                className={`relative z-10 w-9 h-9 rounded-full flex items-center justify-center transition-all duration-150 border-2 cursor-pointer focus:outline-none ${
                  isPassed
                    ? 'bg-emerald-500 border-emerald-500 text-white shadow-xs'
                    : isCurrent
                    ? 'bg-blue-600 border-blue-600 text-white shadow-md ring-4 ring-blue-100 dark:ring-blue-950/70 scale-105'
                    : 'bg-white dark:bg-zinc-900 border-zinc-300 dark:border-zinc-700 text-zinc-400 hover:border-zinc-400'
                } ${isSelected ? 'ring-2 ring-zinc-900 dark:ring-zinc-100' : ''}`}
                title={`Этап: ${stage.label} (${isPassed ? 'Завершён' : isCurrent ? 'Текущий' : 'В очереди'})`}
              >
                {isPassed ? (
                  <Check className="w-4 h-4 stroke-[3]" />
                ) : (
                  <Icon className="w-4 h-4" />
                )}
              </button>
            );
          })}
        </div>

        {/* Labels & Timing row underneath */}
        <div className="flex items-start justify-between w-full mt-2.5">
          {STAGES_CONFIG.map((stage, idx) => {
            const stageData = task.stages[stage.id];
            const isCurrent = task.currentStage === stage.id;
            const isPassed = idx < currentStageIndex || stageData?.status === 'completed';

            // Text alignment: first item left-aligned or centered, last item right-aligned or centered
            const alignClass = idx === 0 ? 'items-start text-left' : idx === STAGES_CONFIG.length - 1 ? 'items-end text-right' : 'items-center text-center';

            return (
              <div 
                key={stage.id} 
                className={`w-20 flex flex-col cursor-pointer ${alignClass}`}
                onClick={() => onSelectStage?.(stage.id)}
              >
                <span className={`text-xs font-semibold leading-tight ${
                  isCurrent 
                    ? 'text-blue-600 dark:text-blue-400' 
                    : isPassed 
                    ? 'text-zinc-800 dark:text-zinc-200' 
                    : 'text-zinc-400 dark:text-zinc-500'
                }`}>
                  {stage.label}
                </span>

                {stageData?.duration && (
                  <span className={`text-[10px] font-mono mt-0.5 ${
                    isCurrent ? 'text-blue-500 font-medium' : 'text-zinc-400 dark:text-zinc-500'
                  }`}>
                    {stageData.duration}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Stage Sub-description Callout */}
      <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800/80 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-zinc-600 dark:text-zinc-400">
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">Текущее действие:</span>
          <span>{task.stages[task.currentStage]?.description || task.statusLabel}</span>
        </div>

        <span className="text-[11px] text-zinc-400 font-mono">
          Кликните на этап для перехода к артефактам
        </span>
      </div>
    </div>
  );
}
