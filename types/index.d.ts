export type Snapshot = {
  root: string
  isRunning: boolean
  queue: string[]
  current: string
  startedAt: string
  plan: string
  counts: string
  runLog: string[]
  actions: string[]
  stages: string[]
  error: string
}

declare module 'claude-code' {
  interface PluginState {
    tw: { snapshot: Shaped<Snapshot> }
  }
}
