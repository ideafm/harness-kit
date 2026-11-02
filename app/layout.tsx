import type { ReactNode } from 'react'
require('./globals.css')
export const metadata = { title: 'tw-web · Рабочая панель' }
export default function Layout({ children }: { children: ReactNode }) { return <html lang="ru"><body>{children}</body></html> }
