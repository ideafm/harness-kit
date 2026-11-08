import React, { useState } from 'react';
import { 
  FileCode, 
  Copy, 
  Check, 
  ChevronRight, 
  Folder, 
  ExternalLink,
  Plus,
  Minus
} from 'lucide-react';
import { DiffFile } from '../types';

interface DiffViewerProps {
  diffs: DiffFile[];
}

export function DiffViewer({ diffs }: DiffViewerProps) {
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);
  const [copiedPatch, setCopiedPatch] = useState(false);
  const [viewMode, setViewMode] = useState<'unified' | 'split'>('unified');

  if (!diffs || diffs.length === 0) {
    return (
      <div className="p-8 text-center border border-dashed border-zinc-200 dark:border-zinc-800 rounded-xl text-xs text-zinc-500">
        Нет зафиксированных изменений в коде для этой задачи.
      </div>
    );
  }

  const currentFile = diffs[selectedFileIndex] || diffs[0];

  const handleCopy = () => {
    const rawDiff = currentFile.diffHunks.map(h => 
      `${h.header}\n` + h.lines.map(l => `${l.type === 'add' ? '+' : l.type === 'delete' ? '-' : ' '} ${l.text}`).join('\n')
    ).join('\n\n');

    navigator.clipboard.writeText(rawDiff);
    setCopiedPatch(true);
    setTimeout(() => setCopiedPatch(false), 2000);
  };

  return (
    <div className="border border-zinc-200 dark:border-zinc-800 rounded-xl overflow-hidden bg-white dark:bg-zinc-900 shadow-2xs">
      {/* Diff Toolbar */}
      <div className="p-2.5 bg-zinc-50 dark:bg-zinc-900/90 border-b border-zinc-200 dark:border-zinc-800 flex flex-wrap items-center justify-between gap-2 text-xs">
        {/* File Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto max-w-full">
          {diffs.map((file, idx) => (
            <button
              key={file.filename}
              onClick={() => setSelectedFileIndex(idx)}
              className={`flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-mono transition-colors shrink-0 ${
                idx === selectedFileIndex
                  ? 'bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 shadow-2xs border border-zinc-200 dark:border-zinc-700'
                  : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800/50'
              }`}
            >
              <FileCode className="w-3.5 h-3.5 text-blue-500" />
              <span className="truncate max-w-[200px]">{file.filename}</span>
              <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold">
                +{file.additions}
              </span>
              {file.deletions > 0 && (
                <span className="text-[10px] text-red-500 font-semibold">
                  -{file.deletions}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* View Mode & Copy Button */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center p-0.5 rounded-md bg-zinc-200/70 dark:bg-zinc-800 text-[11px]">
            <button
              onClick={() => setViewMode('unified')}
              className={`px-2 py-0.5 rounded font-medium ${viewMode === 'unified' ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-2xs' : 'text-zinc-600 dark:text-zinc-400'}`}
            >
              Unified
            </button>
            <button
              onClick={() => setViewMode('split')}
              className={`px-2 py-0.5 rounded font-medium ${viewMode === 'split' ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-2xs' : 'text-zinc-600 dark:text-zinc-400'}`}
            >
              Split
            </button>
          </div>

          <button
            onClick={handleCopy}
            className="p-1.5 rounded-md hover:bg-zinc-200 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400 transition-colors flex items-center gap-1 text-[11px]"
            title="Скопировать патч"
          >
            {copiedPatch ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copiedPatch ? 'Скопировано' : 'Copy patch'}</span>
          </button>
        </div>
      </div>

      {/* Code Diff Display */}
      <div className="font-mono text-xs overflow-x-auto max-h-[460px] bg-zinc-950 text-zinc-100">
        {currentFile.diffHunks.map((hunk, hIdx) => (
          <div key={hIdx}>
            {/* Hunk Header */}
            <div className="bg-zinc-900/90 text-zinc-400 px-4 py-1 text-[11px] select-none border-y border-zinc-800/80">
              {hunk.header}
            </div>

            {/* Lines */}
            <div className="divide-y divide-zinc-900/40">
              {hunk.lines.map((line, lIdx) => {
                const isAdd = line.type === 'add';
                const isDel = line.type === 'delete';

                return (
                  <div
                    key={lIdx}
                    className={`flex items-start text-[11px] leading-5 font-mono ${
                      isAdd
                        ? 'bg-emerald-950/40 text-emerald-200'
                        : isDel
                        ? 'bg-rose-950/40 text-rose-300'
                        : 'text-zinc-300'
                    }`}
                  >
                    {/* Line numbers */}
                    <div className="w-10 shrink-0 text-right pr-2 text-zinc-500 select-none bg-zinc-950/50 border-r border-zinc-800/40">
                      {line.oldLineNo || ''}
                    </div>
                    <div className="w-10 shrink-0 text-right pr-2 text-zinc-500 select-none bg-zinc-950/50 border-r border-zinc-800/40">
                      {line.newLineNo || ''}
                    </div>

                    {/* Diff Marker (+, -, ' ') */}
                    <div className="w-5 shrink-0 text-center select-none font-bold">
                      {isAdd ? '+' : isDel ? '-' : ' '}
                    </div>

                    {/* Code text */}
                    <div className="flex-1 px-2 whitespace-pre overflow-x-auto">
                      {line.text}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
