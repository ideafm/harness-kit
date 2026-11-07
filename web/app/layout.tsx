import type { ReactNode } from 'react'
require('./globals.css')
export const metadata = { title: 'tw-web · Рабочая панель' }
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" className="h-full">
      <body className="h-full overflow-hidden bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 font-sans antialiased">
        {children}
      </body>
    </html>
  )
}

