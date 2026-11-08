export type TaskStage = 'plan' | 'dev' | 'checks' | 'review' | 'acceptance';

export type TaskStatus = 
  | 'accepted_unconfirmed' // Принято, применение не подтверждено
  | 'in_progress'          // В процессе разработки
  | 'needs_review'         // Требуется проверка
  | 'accepted_applied'     // Принято и применено
  | 'failed'               // Ошибка выполнения
  | 'backlog';             // В бэклоге

export interface StageInfo {
  id: TaskStage;
  label: string;
  shortLabel: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  duration?: string;
  description?: string;
}

export interface LogEvent {
  id: string;
  timestamp: string;
  type: 'thought' | 'tool' | 'bash' | 'file' | 'check' | 'human';
  title: string;
  content: string;
  details?: string;
  status?: 'success' | 'warning' | 'error';
  duration?: string;
}

export interface DiffFile {
  filename: string;
  status: 'modified' | 'added' | 'deleted';
  additions: number;
  deletions: number;
  oldPath?: string;
  newPath?: string;
  diffHunks: {
    header: string;
    lines: {
      type: 'add' | 'delete' | 'context';
      oldLineNo?: number;
      newLineNo?: number;
      text: string;
    }[];
  }[];
}

export interface VerificationCheck {
  id: string;
  name: string;
  command: string;
  status: 'passed' | 'failed' | 'running' | 'skipped';
  duration: string;
  summary: string;
  details?: string;
}

export interface PlanItem {
  id: string;
  title: string;
  completed: boolean;
  notes?: string;
}

export interface Task {
  id: string;
  projectId?: string;
  num: number;
  title: string;
  key: string; // e.g. "TASK-1"
  status: TaskStatus;
  statusLabel: string;
  currentStage: TaskStage;
  currentStageLabel: string;
  branch: string;
  model: string;
  createdAt: string;
  updatedAt: string;
  needsAttention: boolean;
  stages: Record<TaskStage, StageInfo>;
  description: string;
  harnessPrompt: string;
  resultSummary: string;
  planItems: PlanItem[];
  logs: LogEvent[];
  diffs: DiffFile[];
  checks: VerificationCheck[];
  reviewNotes: {
    reviewer: string;
    passed: boolean;
    score: number;
    feedback: string[];
  };
  runtimeInfo: {
    configured: boolean;
    url?: string;
    port?: number;
    status: 'idle' | 'running' | 'stopped';
    verifiedVersionHash: string;
    workingVersionHash: string;
  };
  agentRole?: {
    title: string;
    role: string;
    level: string;
    avatar: string;
  };
  heartbeat?: {
    lastSeen: string;
    threadId: string;
    active: boolean;
  };
  costTracking?: {
    tokensUsed: number;
    estimatedCost: number;
    budgetLimit: number;
  };
  sandboxTools?: string[];
}

export interface Project {
  id: string;
  name: string;
  description: string;
  repoPath: string;
  activeBranch: string;
  totalTasks: number;
  pendingTasks: number;
  workerRunning: boolean;
  workerPort: number;
  lastSync: string;
}
