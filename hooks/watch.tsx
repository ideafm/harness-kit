import { atom, read, update } from 'claude-code'
import type { EngineInterface as Engine, Register } from 'claude-code'

import type { Snapshot } from '../types'

const PANE = 'tw-watch'
const TITLE = 'tw · исполнитель'
const empty: Snapshot = {
  root: '',
  isRunning: false,
  queue: [],
  current: '',
  startedAt: '',
  plan: '',
  counts: '',
  runLog: [],
  actions: [],
  stages: [],
  error: '',
}
const snapshot = atom({ plugin: 'tw', key: 'snapshot' } as const, empty, {
  shape: 'snapshot-2',
})

function oneLine(text: string, max = 160) {
  const line = text.replace(/\s+/g, ' ').trim()
  return line.length > max ? `${line.slice(0, max - 1)}…` : line
}

async function exists($: Engine, path: string) {
  try {
    await $.fs.stat(path)
    return true
  } catch {
    return false
  }
}

async function readText($: Engine, path: string) {
  try {
    return await $.fs.read(path)
  } catch {
    return ''
  }
}

async function findRoot($: Engine, start: string) {
  let dir = start.replace(/\/+$/, '')
  while (dir) {
    if (await exists($, `${dir}/.claude/tw.json`)) return dir
    dir = dir.slice(0, dir.lastIndexOf('/'))
  }
  return ''
}

async function expand($: Engine, path: string) {
  if (!path.startsWith('~')) return path
  return ((await $.env.get('HOME')) ?? '') + path.slice(1)
}

async function resolveRoot($: Engine) {
  const saved = await $.store.get('root')
  if (typeof saved === 'string' && saved) {
    const root = await findRoot($, saved)
    if (root) return root
  }
  return findRoot($, await $.session.cwd())
}

async function tail($: Engine, path: string, lines: number) {
  try {
    const { exitCode, stdout } = await $.process.run(['tail', '-n', String(lines), path])
    return exitCode === 0 ? stdout : ''
  } catch {
    return ''
  }
}

function parseStream(text: string) {
  const actions: string[] = []
  for (const raw of text.split('\n')) {
    if (!raw.startsWith('{')) continue
    let row: { type?: string; message?: { content?: unknown } }
    try {
      row = JSON.parse(raw)
    } catch {
      continue
    }
    if (row.type !== 'assistant' || !Array.isArray(row.message?.content)) continue
    for (const part of row.message.content as {
      type: string
      text?: string
      name?: string
      input?: Record<string, unknown>
    }[]) {
      if (part.type === 'text' && part.text?.trim()) actions.push(`· ${oneLine(part.text)}`)
      if (part.type === 'tool_use') {
        const input = part.input ?? {}
        const arg = input.command ?? input.file_path ?? input.pattern ?? input.description ?? ''
        actions.push(`→ ${part.name} ${oneLine(String(arg), 120)}`)
      }
    }
  }
  const stages = (text.match(/tw ▸[^"\\]*/g) ?? []).filter(s => !s.includes('`'))
  return { actions, stages }
}

async function planProgress($: Engine, root: string, id: string) {
  const config = await readText($, `${root}/.claude/tw.json`)
  let wt = '.claude/worktrees/tw-run'
  try {
    const value = JSON.parse(config).runWorktree
    if (typeof value === 'string' && value) wt = value
  } catch {}
  if (!wt.startsWith('/')) wt = `${root}/${wt}`
  const task = await readText($, `${root}/docs/backlog/${id}.md`)
  const path = task.match(/\*\*План:\*\* ([^·\n]+)/)?.[1]?.trim()
  if (!path) return ''
  const plan = await readText($, `${wt}/${path}`)
  const total = plan.match(/^- \[[ x]\] \d+\./gm)?.length ?? 0
  const done = plan.match(/^- \[x\] \d+\./gm)?.length ?? 0
  const next = plan.match(/^- \[ \] (\d+\..*)$/m)?.[1] ?? ''
  return total ? `план ${done}/${total}${next ? ` · сейчас: ${next}` : ''}` : ''
}

let streamKey = ''
let streamParsed: { actions: string[]; stages: string[] } = { actions: [], stages: [] }

async function countStatuses($: Engine, root: string) {
  const dir = `${root}/docs/backlog`
  let entries: { name: string }[] = []
  try {
    entries = await $.fs.list(dir)
  } catch {
    return ''
  }
  const tally = new Map<string, number>()
  for (const { name } of entries) {
    if (!/^B-\d+\.md$/.test(name)) continue
    const status = (await readText($, `${dir}/${name}`)).match(/\*\*Статус:\*\* ([^·\n]*)/)?.[1]
    const key = (status ?? '?').trim().replace(/:.*/, '')
    tally.set(key, (tally.get(key) ?? 0) + 1)
  }
  return [...tally].map(([k, n]) => `${k} ${n}`).join(' · ')
}

async function collect($: Engine): Promise<Snapshot> {
  const root = await resolveRoot($)
  if (!root) return { ...empty, error: 'tw-проект не найден — /tw-watch <путь к проекту>' }
  const state = `${root}/.claude/tw-state`
  const pid = (await readText($, `${state}/run.pid`)).trim()
  const isRunning =
    /^\d+$/.test(pid) &&
    (await $.process.run(['ps', '-p', pid, '-o', 'command='])).stdout.includes('scripts/run.sh')
  const queue = (await readText($, `${state}/queue`)).split('\n').filter(Boolean)
  const runLog = (await tail($, `${state}/run.log`, 40)).split('\n').filter(Boolean)

  let current = ''
  let startedAt = ''
  for (const line of runLog) {
    const start = line.match(/^(\S+ \S+) · (B-\d+) · старт в /)
    if (start) {
      current = start[2] ?? ''
      startedAt = start[1] ?? ''
    } else if (current && line.includes(` · ${current} · `)) {
      current = ''
    }
  }
  if (!isRunning) current = ''

  let actions: string[] = []
  let stages: string[] = []
  try {
    const files = (await $.fs.list(`${state}/run`)).filter(f => f.name.endsWith('.jsonl'))
    const latest = files.sort((a, b) => b.mtimeMs - a.mtimeMs)[0]
    if (latest) {
      const key = `${latest.name}:${latest.size}`
      if (key !== streamKey) {
        streamParsed = parseStream(await readText($, `${state}/run/${latest.name}`))
        streamKey = key
      }
      ;({ actions, stages } = streamParsed)
    }
  } catch {}

  return {
    root,
    isRunning,
    queue,
    current,
    startedAt,
    plan: current ? await planProgress($, root, current) : '',
    counts: await countStatuses($, root),
    runLog: runLog.slice(-8),
    actions: actions.slice(-500),
    stages: stages.slice(-6),
    error: '',
  }
}

let timer: { cancel: () => void } | undefined
let last = ''
let wasRunning = false
let follow = true

async function refresh($: Engine) {
  const next = await collect($)
  if (next.isRunning && !wasRunning) void $.ui.open({ id: PANE, title: TITLE })
  wasRunning = next.isRunning
  const key = JSON.stringify(next)
  if (key === last) return
  last = key
  await update($, snapshot, () => next)
  if (follow) void $.ui.scroll({ in: PANE, to: 'end' }).catch(() => {})
}

async function start($: Engine) {
  await refresh($)
  timer ??= $.clock.every(2000, () => {
    void refresh($)
  })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    if (!e.isInteractive) return next(e)
    await $.command.register({
      name: 'tw-watch',
      description: 'Панель хода исполнителя бэклога tw',
      argumentHint: '[путь к проекту | close]',
    })
    if (await resolveRoot($)) await start($)
    return next(e)
  })

  on('command.run', { command: 'tw-watch' }, async ($, e) => {
    const arg = e.args.trim()
    if (arg === 'close') {
      await $.ui.close({ id: PANE })
      return { text: 'Панель tw закрыта. Откроется сама при следующем прогоне.' }
    }
    if (arg) {
      const root = await findRoot($, await expand($, arg))
      if (!root) return { text: `В ${arg} нет .claude/tw.json` }
      await $.store.set('root', root)
    }
    await start($)
    await $.ui.open({ id: PANE, title: TITLE })
    return { text: `Панель tw открыта${arg ? ` для ${arg}` : ''}.` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const s = await read($, snapshot)
    const width = Math.max(30, (e.viewport?.columns ?? 80) - 2)
    const fit = (text: string) => oneLine(text, width)

    if (s.error) return <Text dimColor>{s.error}</Text>

    const head = [
      `${s.root.replace(/^\/Users\/[^/]+/, '~')} · исполнитель ${s.isRunning ? 'идёт' : 'не идёт'}`,
      `сейчас: ${s.current ? `${s.current} с ${s.startedAt.slice(11, 16)}` : '—'} · очередь: ${s.queue.join(' ') || 'пусто'}`,
      `бэклог: ${s.counts || '—'}`,
    ]

    return (
      <Box flexDirection="column">
        <Text bold color={s.isRunning ? 'green' : undefined}>
          {fit(head[0] ?? '')}
        </Text>
        <Text>{fit(head[1] ?? '')}</Text>
        {s.plan && <Text>{fit(s.plan)}</Text>}
        <Text dimColor>{fit(head[2] ?? '')}</Text>
        <Text> </Text>
        <Text bold>run.log</Text>
        {s.runLog.map(line => (
          <Text color={line.includes('застряла') ? 'red' : line.includes('на приёмке') ? 'green' : undefined}>
            {fit(line.slice(11))}
          </Text>
        ))}
        <Text> </Text>
        <Text bold>Stop</Text>
        {s.stages.length === 0 && <Text dimColor>проверок ещё не было</Text>}
        {s.stages.map(line => (
          <Text color={/fail|красн|блок|нужен человек/.test(line) ? 'red' : undefined}>{fit(line)}</Text>
        ))}
        <Text> </Text>
        <Text bold>Агент · колесо или стрелки — история, End — к последнему</Text>
        {s.actions.length === 0 && <Text dimColor>потока ещё нет</Text>}
        {s.actions.map(line => (
          <Text dimColor={!line.startsWith('·')}>{fit(line)}</Text>
        ))}
      </Box>
    )
  })

  on('ui.scroll', { requestId: PANE }, async ($, e, next) => {
    if (e.origin.kind === 'person') follow = e.offset >= e.contentRows - e.bodyRows
    return next(e)
  })

  on('session.end', async ($, e, next) => {
    timer?.cancel()
    return next(e)
  })
}
