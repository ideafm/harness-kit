import React from 'react';
import { 
  Bot, 
  Coins, 
  Activity, 
  Shield, 
  Terminal, 
  Wrench, 
  AlertTriangle, 
  CheckCircle2, 
  Lock,
  Cpu
} from 'lucide-react';
import { Task } from '../types';

interface AgentGovernanceCardProps {
  task: Task;
}

export function AgentGovernanceCard({ task }: AgentGovernanceCardProps) {
  // Paperclip-inspired governance metrics
  const cost = task.costTracking || {
    tokensUsed: 48250,
    estimatedCost: 0.38,
    budgetLimit: 2.00
  };

  const agentRole = task.agentRole || {
    title: 'Senior Frontend Engineer',
    role: 'Autonomous Coding Agent',
    level: 'L3 Autonomy (Approval Gate)',
    avatar: 'bg-blue-600'
  };

  const heartbeat = task.heartbeat || {
    lastSeen: '4 сек назад',
    threadId: '#12 (harness-worker)',
    active: true
  };

  const tools = task.sandboxTools || ['git:branch', 'fs:scoped-write', 'bash:isolated', 'pnpm:test'];

  const budgetPercent = Math.min(100, Math.round((cost.estimatedCost / cost.budgetLimit) * 100));

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 shadow-2xs space-y-3.5">
      {/* Top Header: Agent Role & Live Heartbeat */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-zinc-100 dark:border-zinc-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-xs shadow-xs">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-zinc-900 dark:text-zinc-100">
                {agentRole.title}
              </span>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-100 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 font-mono">
                {task.model}
              </span>
            </div>
            <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
              {agentRole.level} · {agentRole.role}
            </div>
          </div>
        </div>

        {/* Live Heartbeat Status */}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-lg bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200/80 dark:border-zinc-700/60 text-xs">
          <Activity className="w-3.5 h-3.5 text-emerald-500 animate-pulse" />
          <div className="text-[11px]">
            <span className="text-zinc-400">Пульс:</span>{' '}
            <span className="font-medium text-zinc-700 dark:text-zinc-300 font-mono">{heartbeat.lastSeen}</span>
          </div>
        </div>
      </div>

      {/* Grid: Budget Spend Governance & Sandbox Tools (Key Paperclip features) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        {/* Metric 1: Token & Budget Limit (Cost Governance) */}
        <div className="p-3 rounded-lg bg-zinc-50/80 dark:bg-zinc-950/60 border border-zinc-200/80 dark:border-zinc-800 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-zinc-700 dark:text-zinc-300 font-semibold">
              <Coins className="w-3.5 h-3.5 text-amber-500" />
              <span>Лимит затрат (Budget Guard)</span>
            </div>
            <span className="font-mono text-[11px] font-bold text-zinc-800 dark:text-zinc-200">
              ${cost.estimatedCost.toFixed(2)} / ${cost.budgetLimit.toFixed(2)}
            </span>
          </div>

          {/* Visual Budget Progress Bar */}
          <div className="w-full bg-zinc-200 dark:bg-zinc-800 h-1.5 rounded-full overflow-hidden">
            <div 
              className={`h-full transition-all duration-300 ${
                budgetPercent > 80 ? 'bg-rose-500' : budgetPercent > 50 ? 'bg-amber-500' : 'bg-emerald-500'
              }`}
              style={{ width: `${budgetPercent}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[10px] text-zinc-500 font-mono">
            <span>{cost.tokensUsed.toLocaleString()} токенов</span>
            <span>Использовано {budgetPercent}% лимита</span>
          </div>
        </div>

        {/* Metric 2: Sandbox Permissions & Tools */}
        <div className="p-3 rounded-lg bg-zinc-50/80 dark:bg-zinc-950/60 border border-zinc-200/80 dark:border-zinc-800 space-y-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-zinc-700 dark:text-zinc-300 font-semibold">
              <Shield className="w-3.5 h-3.5 text-blue-500" />
              <span>Песочница и разрешения</span>
            </div>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 font-medium">
              Изолировано
            </span>
          </div>

          {/* Badges for authorized tools */}
          <div className="flex flex-wrap gap-1 pt-0.5">
            {tools.map((tool) => (
              <span
                key={tool}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700"
              >
                {tool}
              </span>
            ))}
          </div>

          <div className="text-[10px] text-zinc-400 pt-0.5">
            Docker jail · landlock strict · сеть: localhost only
          </div>
        </div>
      </div>
    </div>
  );
}
