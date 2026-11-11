import { it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ProjectPreviewBar } from '@/components/project-preview-bar'
import type { ProjectViewResponse, Task, Transport } from '@/lib/contracts'

const session = { csrf_token: 'csrf', confirmation_origin: '' }
const digest = 'a'.repeat(64)
const selection = 'uuid-sel-1'

function makeData(active: number | null = 1, running = true, ready = true): ProjectViewResponse {
  return {
    task_id: active,
    available: active !== null,
    reason: active ? null : 'Версия для запуска ещё не выбрана',
    revision: 'view-rev-1',
    view: active
      ? {
          revision: ready ? `${selection}:${digest}` : 'building',
          url: 'http://127.0.0.1:40001',
          running,
          requested: { task: active, mode: 'checked', revision: selection },
          active_task: active,
          mode: 'checked',
          source_digest: digest,
          current: ready,
          building: !ready,
          message: ready ? 'Готово' : 'Подготовка'
        }
      : null,
    actions: active ? (running ? ['select', 'refresh', 'stop'] : ['select', 'refresh']) : []
  }
}

const task1: Task = {
  id: 1,
  state: 'review',
  stage: 'done',
  updated: 1,
  request: 'Первая задача',
  artifacts: [],
  preview: {
    url: 'http://127.0.0.1:40001/tasks/1',
    persistent: true,
    current: true,
    read_only: true,
    mode: 'checked',
    version: digest
  }
}

const task2: Task = {
  id: 2,
  state: 'review',
  stage: 'done',
  updated: 2,
  request: 'Вторая задача',
  artifacts: [],
  preview: {
    url: 'http://127.0.0.1:40001/tasks/2',
    persistent: true,
    current: true,
    read_only: true,
    mode: 'checked',
    version: digest
  }
}

it('запуск, остановка и открытие без выбранной карточки', async () => {
  let current = makeData(1, true, true)
  const get = vi.fn().mockImplementation(async () => current)
  const post = vi.fn().mockImplementation(async (path, body) => {
    if (body.action === 'stop') {
      current = {
        ...current,
        view: { ...current.view!, running: false, manually_stopped: true }
      }
      return { operation_id: 'op-stop', task_id: 1, status: 'succeeded' }
    }
    if (body.action === 'select') {
      current = makeData(1, true, true)
      return { operation_id: 'op-start', task_id: 1, status: 'succeeded' }
    }
    return { operation_id: 'op', task_id: 1, status: 'succeeded' }
  })

  render(
    <ProjectPreviewBar
      transport={{ get, post, projectId: 'main' }}
      session={session}
      enabled
      tasks={[task1]}
    />
  )

  // Subtitle indicates active result
  await screen.findByText('TASK-001 · проверенная версия')
  expect(screen.getByText('Запущен')).toBeTruthy()
  expect(screen.getByText('127.0.0.1:40001')).toBeTruthy()

  // Open link is ready and opens in new tab
  const link = screen.getByRole('link', { name: 'Открыть результат' })
  expect(link.getAttribute('href')).toBe('http://127.0.0.1:40001/tasks/1')
  expect(link.getAttribute('target')).toBe('_blank')

  // Stop button stops the app
  const stopBtn = screen.getByRole('button', { name: 'Остановить' })
  fireEvent.click(stopBtn)

  await screen.findByText('Остановлен')
  expect(post).toHaveBeenCalledWith(
    'view',
    { action: 'stop', mode: 'checked' },
    expect.any(String),
    'csrf',
    'view-rev-1'
  )
  expect(screen.queryByRole('link', { name: 'Открыть результат' })).toBeNull()

  // Start button starts the app again
  const startBtn = screen.getByRole('button', { name: 'Запустить' })
  fireEvent.click(startBtn)
  await screen.findByText('Запущен')
  expect(post).toHaveBeenCalledWith(
    'view',
    { action: 'select', mode: 'checked' },
    expect.any(String),
    'csrf',
    'view-rev-1'
  )
})

it('переключение результата между задачами', async () => {
  let current = makeData(1, true, true)
  const get = vi.fn().mockImplementation(async () => current)
  const post = vi.fn().mockResolvedValue({ operation_id: 'op', task_id: 2, status: 'succeeded' })

  const view = render(
    <ProjectPreviewBar
      transport={{ get, post, projectId: 'main' }}
      session={session}
      enabled
      tasks={[task1, task2]}
    />
  )

  await screen.findByText('TASK-001 · проверенная версия')
  expect(screen.getByRole('link', { name: 'Открыть результат' }).getAttribute('href')).toBe(
    'http://127.0.0.1:40001/tasks/1'
  )

  // Switch to TASK-002
  current = makeData(2, true, true)
  view.rerender(
    <ProjectPreviewBar
      transport={{ get, post, projectId: 'main' }}
      session={session}
      enabled
      tasks={[task1, task2]}
    />
  )

  await screen.findByText('TASK-002 · проверенная версия')
  expect(screen.getByRole('link', { name: 'Открыть результат' }).getAttribute('href')).toBe(
    'http://127.0.0.1:40001/tasks/2'
  )
})

it('переключение проектов во время запроса', async () => {
  let resolveFirst: (v: unknown) => void = () => {}
  const get = vi.fn().mockImplementation(async (path: string) => {
    if (path === 'operations/op-1') {
      return new Promise(done => {
        resolveFirst = done
      })
    }
    return makeData(1, true, true)
  })

  const transport1: Transport = {
    projectId: 'proj-1',
    get,
    post: vi.fn().mockResolvedValue({ operation_id: 'op-1', task_id: 1, status: 'pending' })
  }
  const transport2: Transport = {
    projectId: 'proj-2',
    get: vi.fn().mockResolvedValue(makeData(2, true, true)),
    post: vi.fn()
  }

  vi.useFakeTimers()
  const view = render(
    <ProjectPreviewBar transport={transport1} session={session} enabled tasks={[task1]} />
  )
  try {
    await act(async () => {})
    fireEvent.click(screen.getByRole('button', { name: 'Остановить' }))
    await act(async () => {})
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    // Switch project
    view.rerender(
      <ProjectPreviewBar transport={transport2} session={session} enabled tasks={[task2]} />
    )
    await act(async () => {})

    // Late resolve of project 1
    await act(async () => {
      resolveFirst({
        operation_id: 'op-1',
        task_id: 1,
        status: 'failed',
        error: { message: 'Поздняя ошибка proj-1' }
      })
    })

    // Project 2 is intact and not corrupted by late project 1 response
    expect(screen.queryByText('Поздняя ошибка proj-1')).toBeNull()
    expect(screen.getByText('TASK-002 · проверенная версия')).toBeTruthy()
  } finally {
    view.unmount()
    vi.useRealTimers()
  }
})

it('отсутствие готового результата', async () => {
  const get = vi.fn().mockResolvedValue(makeData(null, false, false))
  const post = vi.fn()

  render(
    <ProjectPreviewBar
      transport={{ get, post, projectId: 'main' }}
      session={session}
      enabled
      tasks={[]}
    />
  )

  await screen.findByText('Версия не выбрана')
  expect(screen.getByText('Остановлен')).toBeTruthy()

  const startBtn = screen.getByRole('button', { name: 'Запустить' }) as HTMLButtonElement
  expect(startBtn.disabled).toBe(true)
  expect(startBtn.getAttribute('title')).toBe('Сначала выберите результат в карточке задачи')

  const stopBtn = screen.getByRole('button', { name: 'Остановить' }) as HTMLButtonElement
  expect(stopBtn.disabled).toBe(true)

  const openBtn = screen.getByRole('button', { name: 'Открыть' }) as HTMLButtonElement
  expect(openBtn.disabled).toBe(true)

  expect(post).not.toHaveBeenCalled()
})

it('ошибка запуска и повтор', async () => {
  const errorData: ProjectViewResponse = {
    ...makeData(1, false, false),
    view: {
      ...makeData(1, false, false).view!,
      building: false,
      error: 'Ошибка компиляции'
    }
  }
  const get = vi.fn().mockResolvedValue(errorData)
  const post = vi.fn().mockResolvedValue({ operation_id: 'op', task_id: 1, status: 'succeeded' })

  render(
    <ProjectPreviewBar
      transport={{ get, post, projectId: 'main' }}
      session={session}
      enabled
      tasks={[task1]}
    />
  )

  await screen.findByText('Ошибка')
  expect(screen.getByText(/Ошибка компиляции/)).toBeTruthy()

  const startBtn = screen.getByRole('button', { name: 'Запустить' })
  expect((startBtn as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(startBtn)

  expect(post).toHaveBeenCalledWith(
    'view',
    { action: 'select', mode: 'checked' },
    expect.any(String),
    'csrf',
    'view-rev-1'
  )
})

it('режим только для чтения', async () => {
  const get = vi.fn().mockResolvedValue(makeData(1, true, true))
  const post = vi.fn()

  render(
    <ProjectPreviewBar
      transport={{ get, post, projectId: 'main' }}
      session={{ ...session, csrf_token: '' }}
      enabled
      tasks={[task1]}
    />
  )

  await screen.findByText('TASK-001 · проверенная версия')
  expect(screen.getByText('Запущен')).toBeTruthy()

  // In read only, mutating buttons are not rendered
  expect(screen.queryByRole('button')).toBeNull()

  // Verified open link is still accessible to view
  const link = screen.getByRole('link', { name: 'Открыть результат' })
  expect(link.getAttribute('href')).toBe('http://127.0.0.1:40001/tasks/1')

  expect(post).not.toHaveBeenCalled()
})
