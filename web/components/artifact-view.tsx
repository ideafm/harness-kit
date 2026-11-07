'use client'
import React, { useEffect, useState } from 'react'
import type { Artifact, Transport } from '@/lib/contracts'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { 
  FileCode, 
  CheckSquare, 
  Copy, 
  Check, 
  ShieldCheck, 
  AlertCircle 
} from 'lucide-react'

export function ArtifactView({
  task,
  name,
  transport
}: {
  task: number
  name: string
  transport: Transport
}) {
  const [data, setData] = useState<Artifact>()
  const [error, setError] = useState('')
  const [attempt, retry] = useState(0)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const abort = new AbortController()
    setData(undefined)
    setError('')
    transport.get<Artifact>(`tasks/${task}/artifacts/${name}`, abort.signal)
      .then(v => {
        if (typeof v.text !== 'string' || typeof v.truncated !== 'boolean') {
          throw Error('Некорректный артефакт')
        }
        if (!abort.signal.aborted) setData(v)
      })
      .catch(e => {
        if (!abort.signal.aborted) {
          setError(e instanceof Error ? e.message : 'Ошибка артефакта')
        }
      })
    return () => abort.abort()
  }, [task, name, transport, attempt])

  if (error) {
    return (
      <div role="alert" className="p-4 rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-xs flex items-center justify-between gap-3">
        <span>{error}</span>
        <Button variant="outline" size="sm" onClick={() => retry(n => n + 1)}>
          Повторить
        </Button>
      </div>
    )
  }

  if (!data) {
    return <Skeleton className="h-32 w-full rounded-xl" />
  }

  const rawText = data.text || ''
  const lines = rawText.split('\n')

  const handleCopy = () => {
    if (!rawText) return
    navigator.clipboard.writeText(rawText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Specialized view for Git Diff
  if (name === 'diff') {
    const additions = lines.filter(l => !l.startsWith('+++') && l.startsWith('+')).length
    const deletions = lines.filter(l => !l.startsWith('---') && l.startsWith('-')).length
    const isGitDiff = rawText.includes('diff --git') || rawText.includes('@@') || additions > 0 || deletions > 0

    return (
      <div className="space-y-2">
        {data.truncated && <p className="notice">Артефакт усечён контроллером.</p>}

        {isGitDiff && (
          <div className="flex items-center justify-between px-3 py-2 bg-zinc-100 dark:bg-zinc-800/70 border border-zinc-200 dark:border-zinc-700/80 rounded-lg text-xs">
            <div className="flex items-center gap-2">
              <FileCode className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              <span className="font-semibold text-zinc-900 dark:text-zinc-100 font-mono text-[11px]">
                Изменения файлов (Unified Diff)
              </span>
              <div className="flex items-center gap-1 font-mono text-[11px] ml-1">
                {additions > 0 && (
                  <span className="px-1.5 py-0.2 rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 font-semibold">
                    +{additions}
                  </span>
                )}
                {deletions > 0 && (
                  <span className="px-1.5 py-0.2 rounded bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 font-semibold">
                    -{deletions}
                  </span>
                )}
              </div>
            </div>

            <button
              onClick={handleCopy}
              className="px-2 py-1 rounded hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 text-[11px] font-mono flex items-center gap-1 transition-colors cursor-pointer"
              title="Скопировать дифф"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Скопировано' : 'Copy diff'}</span>
            </button>
          </div>
        )}

        <pre className="artifact font-mono text-xs overflow-x-auto rounded-lg bg-zinc-50/70 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 divide-y divide-zinc-100/60 dark:divide-zinc-900/60 leading-5">
          {lines.map((line, idx) => {
            const isHeader = line.startsWith('diff --git') || line.startsWith('index ') || line.startsWith('---') || line.startsWith('+++') || line.startsWith('@@')
            const isAdd = !isHeader && line.startsWith('+')
            const isDel = !isHeader && line.startsWith('-')

            return (
              <div
                key={idx}
                className={`px-3 py-0.5 whitespace-pre ${
                  isHeader
                    ? 'bg-blue-50/60 dark:bg-blue-950/40 text-blue-800 dark:text-blue-300 font-semibold'
                    : isAdd
                    ? 'bg-emerald-50/80 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200'
                    : isDel
                    ? 'bg-rose-50/80 dark:bg-rose-950/40 text-rose-800 dark:text-rose-300'
                    : 'text-zinc-800 dark:text-zinc-200'
                }`}
              >
                {line}
              </div>
            )
          })}
        </pre>
      </div>
    )
  }

  // Specialized view for Checks
  if (name === 'checks') {
    const isError = /(FAIL|FAILED|error:|exit code [1-9])/i.test(rawText)
    const isSuccess = /(PASS|ok|passed|success)/i.test(rawText) && !isError

    return (
      <div className="space-y-2">
        {data.truncated && <p className="notice">Артефакт усечён контроллером.</p>}

        <div className="flex items-center justify-between px-3.5 py-2.5 bg-zinc-100 dark:bg-zinc-800/70 border border-zinc-200 dark:border-zinc-700/80 rounded-lg text-xs">
          <div className="flex items-center gap-2">
            <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <div>
              <div className="font-semibold text-zinc-900 dark:text-zinc-100">
                Результаты автоматических проверок
              </div>
              <div className="text-[11px] text-zinc-500">
                Верификация типов, сборки и тестов
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
              isError
                ? 'bg-rose-100 dark:bg-rose-950/70 text-rose-700 dark:text-rose-300'
                : isSuccess
                ? 'bg-emerald-100 dark:bg-emerald-950/70 text-emerald-700 dark:text-emerald-300'
                : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-700 dark:text-zinc-300'
            }`}>
              {isError ? (
                <>
                  <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
                  <span>Найдены ошибки</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Checks Passed</span>
                </>
              )}
            </span>

            <button
              onClick={handleCopy}
              className="p-1 rounded hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors cursor-pointer"
              title="Скопировать отчёт"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5 text-zinc-400" />}
            </button>
          </div>
        </div>

        <pre className="artifact font-mono text-xs overflow-x-auto rounded-lg bg-zinc-50/70 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 divide-y divide-zinc-100/60 dark:divide-zinc-900/60 leading-5">
          {lines.map((line, idx) => {
            const lineIsErr = /(FAIL|FAILED|error|exit code [1-9])/i.test(line)
            const lineIsOk = /(PASS|ok|passed|success)/i.test(line)
            const lineIsCmd = line.startsWith('$') || line.startsWith('>') || line.startsWith('pnpm ') || line.startsWith('npm ') || line.startsWith('python')

            return (
              <div
                key={idx}
                className={`px-3 py-0.5 whitespace-pre ${
                  lineIsErr
                    ? 'bg-rose-50/80 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 font-medium'
                    : lineIsOk
                    ? 'bg-emerald-50/60 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 font-medium'
                    : lineIsCmd
                    ? 'text-blue-600 dark:text-blue-400 font-semibold bg-zinc-100/50 dark:bg-zinc-900/50'
                    : 'text-zinc-800 dark:text-zinc-200'
                }`}
              >
                {line}
              </div>
            )
          })}
        </pre>
      </div>
    )
  }

  // Default artifact view for plan, specification, review, etc.
  return (
    <div className="space-y-2">
      {data.truncated && <p className="notice">Артефакт усечён контроллером.</p>}
      <div className="flex justify-end pb-1">
        <button
          onClick={handleCopy}
          className="px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400 text-xs flex items-center gap-1 transition-colors cursor-pointer"
          title="Скопировать содержимое"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? 'Скопировано' : 'Копировать'}</span>
        </button>
      </div>
      <div>
        <pre className="artifact font-mono text-xs p-4 rounded-xl bg-zinc-50/70 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 whitespace-pre-wrap overflow-x-auto leading-relaxed my-0 text-zinc-900 dark:text-zinc-100">
          {rawText || 'Артефакт пуст.'}
        </pre>
      </div>
    </div>
  )
}
