import { Project, Task } from '../types';

export const mockProject: Project = {
  id: 'e6e4fe4dad2339c8',
  name: 'tw-web',
  description: 'Клиентская веб-панель автономной агентской разработки и управления задачами',
  repoPath: '~/dev/tw-platform/tw-web',
  activeBranch: 'main',
  totalTasks: 9,
  pendingTasks: 3,
  workerRunning: true,
  workerPort: 47831,
  lastSync: 'Только что'
};

export const mockProjectsList: Project[] = [
  mockProject,
  {
    id: 'f921cb4a81093',
    name: 'tw-agent-runner',
    description: 'Бэкенд воркера и песочница запуска Docker-контейнеров с LLM агентами',
    repoPath: '~/dev/tw-platform/tw-agent-runner',
    activeBranch: 'feature/stream-events',
    totalTasks: 4,
    pendingTasks: 1,
    workerRunning: false,
    workerPort: 47832,
    lastSync: '12 минут назад'
  },
  {
    id: 'b140cd552e12',
    name: 'tw-core-protocol',
    description: 'Спецификация протокола обмена событиями и артефактами harness',
    repoPath: '~/dev/tw-platform/tw-core-protocol',
    activeBranch: 'main',
    totalTasks: 2,
    pendingTasks: 0,
    workerRunning: false,
    workerPort: 47833,
    lastSync: '1 час назад'
  }
];

export const mockTasks: Task[] = [
  {
    id: '1',
    num: 1,
    key: 'TASK-1',
    title: 'Первая задача через harness: читающая панель tw-web',
    status: 'accepted_unconfirmed',
    statusLabel: 'Принято, применение не подтверждено',
    currentStage: 'acceptance',
    currentStageLabel: 'Приёмка',
    branch: 'harness/task-1-read-only-panel',
    model: 'claude-3-7-sonnet',
    createdAt: 'Сегодня, 10:24',
    updatedAt: '12 мин назад',
    needsAttention: true,
    stages: {
      plan: {
        id: 'plan',
        label: 'План',
        shortLabel: 'План',
        status: 'completed',
        duration: '14с',
        description: 'План сгенерирован и декомпозирован на 5 шагов'
      },
      dev: {
        id: 'dev',
        label: 'Разработка',
        shortLabel: 'Код',
        status: 'completed',
        duration: '2м 41с',
        description: 'Созданы компоненты панели и смонтированы маршруты'
      },
      checks: {
        id: 'checks',
        label: 'Проверки',
        shortLabel: 'Тесты',
        status: 'completed',
        duration: '38с',
        description: 'TypeScript, ESLint и сборка Next.js прошли без ошибок'
      },
      review: {
        id: 'review',
        label: 'Ревью',
        shortLabel: 'Ревью',
        status: 'completed',
        duration: '52с',
        description: 'Автоматический аудит кода: 0 уязвимостей, соблюдена архитектура'
      },
      acceptance: {
        id: 'acceptance',
        label: 'Приёмка',
        shortLabel: 'Приёмка',
        status: 'running',
        duration: 'ожидание',
        description: 'Ожидается подтверждение оператора для слияния в main'
      }
    },
    description: 'Разработать базовую читающую веб-панель для системы агентской разработки. Интерфейс должен отображать список задач текущего проекта, статус воркера, пайплайн этапов и детальный просмотр артефактов выполнения.',
    harnessPrompt: `Реализуй первую читающую панель tw-web для управления автономным процессом разработки:
- Отображение активного проекта tw-web и списка связанных задач
- Пятишаговый пайплайн задачи: План -> Разработка -> Проверки -> Ревью -> Приёмка
- Состояние воркера harness и индикатор подключения
- Вкладки подробностей: История событий, Исходная задача, План реализации, Изменения в коде (diff), Проверки CI, Ревью
- Блок "Что требуется от вас" с кнопками принятия или перезапуска`,
    resultSummary: 'Результат работы автономного агента полностью сформирован. Все 4 этапа пайплайна (План, Разработка, Проверки, Ревью) успешно пройдены. Код откомпилирован, линтер и статический анализ не выявили дефектов. Результат принят системой, но требует подтверждения человеком для применения патча.',
    planItems: [
      { id: 'p1', title: 'Исследовать структуру репозитория tw-web и существующие конфиги', completed: true, notes: 'Обнаружен Next.js 15 App Router и настроенный tailwindcss' },
      { id: 'p2', title: 'Спроектировать стейт-машину пайплайна этапов (5 шагов)', completed: true, notes: 'Реализованы типы TaskStage и связка с событиями воркера' },
      { id: 'p3', title: 'Создать левую панель со списком задач и фильтрацией', completed: true, notes: 'Фильтры: Все, Нужно вам, Бэклог + поиск по названию' },
      { id: 'p4', title: 'Разработать экран деталей с табами истории и diff-вьюера', completed: true, notes: 'Добавлены вкладки: История, Спека, План, Diff, Проверки' },
      { id: 'p5', title: 'Запустить проверку типов tsc и валидацию сборки', completed: true, notes: '0 ошибок в TypeScript, бандл оптимизирован' }
    ],
    logs: [
      {
        id: 'l1',
        timestamp: '10:24:02',
        type: 'human',
        title: 'Задача принята в очередь',
        content: 'Оператор запустил выполнение задачи TASK-1 через harness-клиент.',
        status: 'success'
      },
      {
        id: 'l2',
        timestamp: '10:24:05',
        type: 'thought',
        title: 'Анализ контекста и планирование',
        content: 'Изучаю файлы проекта `src/` и `package.json`. Проект использует Next.js 15, React 19 и Tailwind CSS. Необходима панель задач с пятью этапами пайплайна.',
        duration: '3.2с'
      },
      {
        id: 'l3',
        timestamp: '10:24:19',
        type: 'bash',
        title: 'Выполнение команды в контейнере',
        content: '$ git status --short && ls -la src/',
        details: '## main...origin/main\n M src/app/page.tsx\n?? src/components/PipelineStepper.tsx',
        status: 'success',
        duration: '180мс'
      },
      {
        id: 'l4',
        timestamp: '10:25:30',
        type: 'file',
        title: 'Генерация компонентов интерфейса',
        content: 'Создан файл `src/components/TaskPipeline.tsx` и обновлен `src/app/page.tsx` с разметкой master-detail и карточками действий.',
        status: 'success'
      },
      {
        id: 'l5',
        timestamp: '10:26:45',
        type: 'check',
        title: 'Запуск верификационного набора',
        content: 'Прогон `pnpm lint` и `pnpm typecheck`. Все проверки завершены со статусом 0.',
        status: 'success',
        duration: '38с'
      },
      {
        id: 'l6',
        timestamp: '10:27:40',
        type: 'thought',
        title: 'Финальное ревью и подготовка артефактов',
        content: 'Все критерии приёмки выполнены. Код готов к демонстрации. Перевожу задачу в этап Приёмка с запросом подтверждения применения.',
        status: 'success'
      }
    ],
    diffs: [
      {
        filename: 'src/components/PipelineStepper.tsx',
        status: 'added',
        additions: 114,
        deletions: 0,
        diffHunks: [
          {
            header: '@@ -0,0 +1,114 @@',
            lines: [
              { type: 'add', newLineNo: 1, text: "import React from 'react';" },
              { type: 'add', newLineNo: 2, text: "import { CheckCircle2, Clock, AlertCircle } from 'lucide-react';" },
              { type: 'add', newLineNo: 3, text: "import { TaskStage, StageInfo } from '@/types';" },
              { type: 'add', newLineNo: 4, text: "" },
              { type: 'add', newLineNo: 5, text: "export function PipelineStepper({ stages, currentStage }: Props) {" },
              { type: 'add', newLineNo: 6, text: "  return (" },
              { type: 'add', newLineNo: 7, text: "    <div className=\"flex items-center gap-3 w-full py-3\">" },
              { type: 'add', newLineNo: 8, text: "      {stages.map((stage, idx) => (" },
              { type: 'add', newLineNo: 9, text: "        <StageNode key={stage.id} stage={stage} isActive={stage.id === currentStage} />" },
              { type: 'add', newLineNo: 10, text: "      ))}" },
              { type: 'add', newLineNo: 11, text: "    </div>" },
              { type: 'add', newLineNo: 12, text: "  );" },
              { type: 'add', newLineNo: 13, text: "}" }
            ]
          }
        ]
      },
      {
        filename: 'src/app/page.tsx',
        status: 'modified',
        additions: 48,
        deletions: 12,
        diffHunks: [
          {
            header: '@@ -14,12 +14,48 @@',
            lines: [
              { type: 'context', oldLineNo: 14, newLineNo: 14, text: "export default function ProjectPage() {" },
              { type: 'delete', oldLineNo: 15, text: "  return <div className=\"p-4\">Старая заглушка панели</div>;" },
              { type: 'add', newLineNo: 15, text: "  const [activeTask, setActiveTask] = useState<Task>(mockTasks[0]);" },
              { type: 'add', newLineNo: 16, text: "  return (" },
              { type: 'add', newLineNo: 17, text: "    <div className=\"flex h-screen bg-background text-foreground\">" },
              { type: 'add', newLineNo: 18, text: "      <Sidebar currentProject={currentProject} />" },
              { type: 'add', newLineNo: 19, text: "      <main className=\"flex-1 flex flex-col min-w-0 overflow-hidden\">" },
              { type: 'add', newLineNo: 20, text: "        <TopNavbar project={currentProject} />" },
              { type: 'add', newLineNo: 21, text: "        <div className=\"flex flex-1 overflow-hidden\">" },
              { type: 'add', newLineNo: 22, text: "          <TaskList tasks={tasks} selected={activeTask} onSelect={setActiveTask} />" },
              { type: 'add', newLineNo: 23, text: "          <TaskDetailPane task={activeTask} />" },
              { type: 'add', newLineNo: 24, text: "        </div>" },
              { type: 'add', newLineNo: 25, text: "      </main>" },
              { type: 'add', newLineNo: 26, text: "    </div>" },
              { type: 'add', newLineNo: 27, text: "  );" }
            ]
          }
        ]
      }
    ],
    checks: [
      {
        id: 'c1',
        name: 'TypeScript Compilation (tsc)',
        command: 'pnpm exec tsc --noEmit',
        status: 'passed',
        duration: '1.4s',
        summary: '0 ошибок типов, строгий режим включен'
      },
      {
        id: 'c2',
        name: 'ESLint Code Style & Rules',
        command: 'pnpm exec eslint src/ --max-warnings=0',
        status: 'passed',
        duration: '2.1s',
        summary: 'Все файлы удовлетворяют правилам линтера'
      },
      {
        id: 'c3',
        name: 'Unit Tests (Vitest)',
        command: 'pnpm test --run',
        status: 'passed',
        duration: '4.8s',
        summary: '12 из 12 тестов успешно пройдены'
      },
      {
        id: 'c4',
        name: 'Production Build Dry-run',
        command: 'pnpm exec next build',
        status: 'passed',
        duration: '18.2s',
        summary: 'Статическая генерация страниц успешна (First Load JS: 84 kB)'
      }
    ],
    reviewNotes: {
      reviewer: 'Autonomous Agent Reviewer (Safety & Style)',
      passed: true,
      score: 98,
      feedback: [
        'Архитектура компонентов декомпозирована корректно, нет избыточных ре-рендеров',
        'Соблюдены правила accessibility: добавлены aria-лейблы для кнопок шагов',
        'Интерфейс поддерживает адаптивность и темную тему'
      ]
    },
    runtimeInfo: {
      configured: true,
      port: 3000,
      url: 'http://localhost:3000',
      status: 'idle',
      verifiedVersionHash: 'c4b890f',
      workingVersionHash: 'e6e4fe4'
    },
    agentRole: {
      title: 'Senior Frontend Engineer',
      role: 'Autonomous Coding Agent',
      level: 'L3 Autonomy (Approval Gate)',
      avatar: 'bg-blue-600'
    },
    heartbeat: {
      lastSeen: '4 сек назад',
      threadId: '#12 (harness-worker)',
      active: true
    },
    costTracking: {
      tokensUsed: 48250,
      estimatedCost: 0.38,
      budgetLimit: 2.00
    },
    sandboxTools: ['git:branch', 'fs:scoped-write', 'bash:isolated', 'pnpm:test']
  },
  {
    id: '2',
    num: 2,
    key: 'TASK-2',
    title: 'Редизайн tw-web на Next.js и shadcn/ui',
    status: 'accepted_unconfirmed',
    statusLabel: 'Принято, применение не подтверждено',
    currentStage: 'acceptance',
    currentStageLabel: 'Приёмка',
    branch: 'design/shadcn-overhaul',
    model: 'claude-3-7-sonnet',
    createdAt: 'Сегодня, 11:05',
    updatedAt: '34 мин назад',
    needsAttention: true,
    stages: {
      plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'completed', duration: '12с' },
      dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'completed', duration: '4м 10с' },
      checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'completed', duration: '42с' },
      review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'completed', duration: '48с' },
      acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Приёмка', status: 'running', duration: 'ожидание' }
    },
    description: 'Полный редизайн интерфейса с внедрением стандартов дизайн-системы shadcn: чистая типографика, двухцветная гамма, информационная плотность.',
    harnessPrompt: 'Переработай интерфейс tw-web с нуля, используя дизайн-систему shadcn/ui. Устрани вложенность карточек, добавь поддержку тёмной темы, компактные таблицы и диффы.',
    resultSummary: 'Создана новая дизайн-система с токенами zinc, кастомными компонентами пайплайна и адаптивной сеткой.',
    planItems: [
      { id: 'p2-1', title: 'Настроить CSS-переменные темы и Tailwind v4', completed: true },
      { id: 'p2-2', title: 'Сверстать компонент Stepper с индикаторами этапов', completed: true },
      { id: 'p2-3', title: 'Создать карточку принятия решения для оператора', completed: true }
    ],
    logs: [
      { id: 'l2-1', timestamp: '11:05:12', type: 'human', title: 'Задача создана', content: 'Инициализирован редизайн интерфейса' },
      { id: 'l2-2', timestamp: '11:07:30', type: 'file', title: 'Создание темы', content: 'Настроен index.css с поддержкой темной и светлой темы' }
    ],
    diffs: [
      {
        filename: 'src/index.css',
        status: 'modified',
        additions: 34,
        deletions: 2,
        diffHunks: []
      }
    ],
    checks: [],
    reviewNotes: { reviewer: 'Critic Agent', passed: true, score: 95, feedback: ['Визуальная иерархия улучшена'] },
    runtimeInfo: { configured: true, port: 3000, url: 'http://localhost:3000', status: 'running', verifiedVersionHash: '8b22a0', workingVersionHash: 'f412d1' }
  },
  {
    id: '3',
    num: 3,
    key: 'TASK-3',
    title: 'Проекты и небольшая полировка существующей Next/shadcn панели',
    status: 'accepted_unconfirmed',
    statusLabel: 'Принято, применение не подтверждено',
    currentStage: 'acceptance',
    currentStageLabel: 'Приёмка',
    branch: 'feature/project-switcher',
    model: 'gpt-4o',
    createdAt: 'Вчера, 18:30',
    updatedAt: 'Вчера, 19:15',
    needsAttention: true,
    stages: {
      plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'completed' },
      dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'completed' },
      checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'completed' },
      review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'completed' },
      acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Приёмка', status: 'running' }
    },
    description: 'Добавление выпадающего списка проектов и бокового сайдбара с переключением репозиториев.',
    harnessPrompt: 'Реализуй переключение проектов в сайдбаре и сохранение активного репозитория в localStorage.',
    resultSummary: 'Переключатель проектов интегрирован, сохраняет стейт между сессиями.',
    planItems: [],
    logs: [],
    diffs: [],
    checks: [],
    reviewNotes: { reviewer: 'Human Operator', passed: true, score: 90, feedback: [] },
    runtimeInfo: { configured: false, status: 'idle', verifiedVersionHash: 'a1b2c3', workingVersionHash: 'd4e5f6' }
  },
  {
    id: '4',
    num: 4,
    key: 'TASK-4',
    title: 'Отдельная проработка и улучшение UI панели tw-web',
    status: 'accepted_applied',
    statusLabel: 'Принято и применено',
    currentStage: 'acceptance',
    currentStageLabel: 'Принято',
    branch: 'release/v0.4.0',
    model: 'claude-3-7-sonnet',
    createdAt: '2 дня назад',
    updatedAt: '1 день назад',
    needsAttention: false,
    stages: {
      plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'completed' },
      dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'completed' },
      checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'completed' },
      review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'completed' },
      acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Завершено', status: 'completed' }
    },
    description: 'Интеграция горячих клавиш и оптимизация загрузки списка задач при большом количестве записей.',
    harnessPrompt: 'Оптимизируй рендер списков задач и добавь шорткаты ⌘K для поиска.',
    resultSummary: 'Изменения смерджены в основную ветку main, коммит #834f19b.',
    planItems: [],
    logs: [],
    diffs: [],
    checks: [],
    reviewNotes: { reviewer: 'Lead', passed: true, score: 100, feedback: ['Отличная оптимизация'] },
    runtimeInfo: { configured: true, port: 3000, url: 'http://localhost:3000', status: 'idle', verifiedVersionHash: '834f19b', workingVersionHash: '834f19b' }
  },
  {
    id: '5',
    num: 5,
    key: 'TASK-5',
    title: 'Автоматический запуск unit-тестов в изолированном sandbox',
    status: 'in_progress',
    statusLabel: 'В процессе разработки',
    currentStage: 'dev',
    currentStageLabel: 'Разработка',
    branch: 'agent/docker-sandbox-runner',
    model: 'claude-3-7-sonnet',
    createdAt: '25 мин назад',
    updatedAt: 'Только что',
    needsAttention: false,
    stages: {
      plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'completed', duration: '9с' },
      dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'running', duration: '1м 20с...' },
      checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'pending' },
      review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'pending' },
      acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Приёмка', status: 'pending' }
    },
    description: 'Настройка изоляции тестов в эфемерном контейнере с монтированием рабочей директории в режиме copy-on-write.',
    harnessPrompt: 'Создай модуль `src/server/sandbox.ts`, который поднимает docker контейнер с node:22-alpine и выполняет pnpm test.',
    resultSummary: 'Агент пишет код сервиса контейнеризации и формирует Dockerfile.test.',
    planItems: [
      { id: 'p5-1', title: 'Подготовить базовый Dockerfile для тестового рантайма', completed: true },
      { id: 'p5-2', title: 'Написать wrapper с потоковым считыванием stdout/stderr', completed: false },
      { id: 'p5-3', title: 'Добавить timeout и лимиты памяти (1GB)', completed: false }
    ],
    logs: [
      { id: 'l5-1', timestamp: '11:20:00', type: 'thought', title: 'Анализ зависимостей Docker', content: 'Пишу скрипт спавна контейнера через node child_process' }
    ],
    diffs: [],
    checks: [],
    reviewNotes: { reviewer: 'AI Monitor', passed: false, score: 0, feedback: [] },
    runtimeInfo: { configured: true, port: 3001, status: 'running', verifiedVersionHash: '000000', workingVersionHash: 'current' }
  },
  {
    id: '6',
    num: 6,
    key: 'TASK-6',
    title: 'Интеграция AST-анализатора и пре-коммит проверок',
    status: 'backlog',
    statusLabel: 'В бэклоге',
    currentStage: 'plan',
    currentStageLabel: 'План',
    branch: 'backlog/ast-lint',
    model: 'gemini-2.0-flash',
    createdAt: '3 часа назад',
    updatedAt: '3 часа назад',
    needsAttention: false,
    stages: {
      plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'pending' },
      dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'pending' },
      checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'pending' },
      review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'pending' },
      acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Приёмка', status: 'pending' }
    },
    description: 'Внедрение статического анализатора синтаксического дерева для блокировки опасных вызовов eval и неограниченного чтения fs.',
    harnessPrompt: 'Используй oxc или babel-parser для проверки генерируемого кода на соответствие правилам безопасности.',
    resultSummary: 'Ожидает запуска воркером.',
    planItems: [],
    logs: [],
    diffs: [],
    checks: [],
    reviewNotes: { reviewer: 'None', passed: false, score: 0, feedback: [] },
    runtimeInfo: { configured: false, status: 'idle', verifiedVersionHash: '', workingVersionHash: '' }
  },
  {
    id: '7',
    num: 7,
    key: 'TASK-7',
    title: 'Реализация стриминга логов автономного воркера через WebSocket',
    status: 'needs_review',
    statusLabel: 'Требуется проверка',
    currentStage: 'review',
    currentStageLabel: 'Ревью',
    branch: 'feature/ws-telemetry',
    model: 'claude-3-7-sonnet',
    createdAt: '4 часа назад',
    updatedAt: '1 час назад',
    needsAttention: true,
    stages: {
      plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'completed' },
      dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'completed' },
      checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'completed' },
      review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'running' },
      acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Приёмка', status: 'pending' }
    },
    description: 'Обеспечение живого отображения вывода консоли агента без перезагрузки страницы.',
    harnessPrompt: 'Добавь ws-сервер на порт воркера и react хук useWorkerStream.',
    resultSummary: 'Разработка завершена, запущена автоматическая процедура ревью архитектуры.',
    planItems: [],
    logs: [],
    diffs: [],
    checks: [],
    reviewNotes: { reviewer: 'Code Review Agent', passed: true, score: 92, feedback: ['Рекомендуется добавить reconnection backoff'] },
    runtimeInfo: { configured: true, port: 47831, status: 'running', verifiedVersionHash: '43ea2b', workingVersionHash: '91f0c2' }
  },
  {
    id: '8',
    num: 8,
    key: 'TASK-8',
    title: 'Улучшение diff-вьюера с поддержкой side-by-side и подсветки синтаксиса',
    status: 'backlog',
    statusLabel: 'В бэклоге',
    currentStage: 'plan',
    currentStageLabel: 'План',
    branch: 'backlog/side-by-side-diff',
    model: 'gpt-4o',
    createdAt: 'Вчера',
    updatedAt: 'Вчера',
    needsAttention: false,
    stages: {
      plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'pending' },
      dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'pending' },
      checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'pending' },
      review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'pending' },
      acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Приёмка', status: 'pending' }
    },
    description: 'Интеграция двухколоночного просмотра изменений для удобной проверки масштабных патчей.',
    harnessPrompt: 'Добавь переключатель Unified / Split в просмотрщик diff.',
    resultSummary: 'В очереди бэклога.',
    planItems: [],
    logs: [],
    diffs: [],
    checks: [],
    reviewNotes: { reviewer: 'None', passed: false, score: 0, feedback: [] },
    runtimeInfo: { configured: false, status: 'idle', verifiedVersionHash: '', workingVersionHash: '' }
  },
  {
    id: '9',
    num: 9,
    key: 'TASK-9',
    title: 'Шаблоны задач и гибкий выбор модели рассуждений (Reasoning Effort)',
    status: 'backlog',
    statusLabel: 'В бэклоге',
    currentStage: 'plan',
    currentStageLabel: 'План',
    branch: 'backlog/reasoning-presets',
    model: 'claude-3-7-sonnet',
    createdAt: '2 дня назад',
    updatedAt: '2 дня назад',
    needsAttention: false,
    stages: {
      plan: { id: 'plan', label: 'План', shortLabel: 'План', status: 'pending' },
      dev: { id: 'dev', label: 'Разработка', shortLabel: 'Код', status: 'pending' },
      checks: { id: 'checks', label: 'Проверки', shortLabel: 'Тесты', status: 'pending' },
      review: { id: 'review', label: 'Ревью', shortLabel: 'Ревью', status: 'pending' },
      acceptance: { id: 'acceptance', label: 'Приёмка', shortLabel: 'Приёмка', status: 'pending' }
    },
    description: 'Возможность быстро выбирать пресеты: "Быстрый багфикс", "Глубокий рефакторинг", "Написание тестов".',
    harnessPrompt: 'Реализуй выпадающий список промпт-шаблонов при создании задачи.',
    resultSummary: 'В очереди бэклога.',
    planItems: [],
    logs: [],
    diffs: [],
    checks: [],
    reviewNotes: { reviewer: 'None', passed: false, score: 0, feedback: [] },
    runtimeInfo: { configured: false, status: 'idle', verifiedVersionHash: '', workingVersionHash: '' }
  }
];
