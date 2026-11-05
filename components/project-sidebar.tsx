'use client'
import { useState } from 'react'
import { Sidebar,SidebarHeader,SidebarContent,SidebarGroup,SidebarGroupLabel,SidebarFooter,useSidebar } from '@/components/ui/sidebar'
import type { Projects } from '@/lib/contracts'
import { AppIcon } from './app-icon'
export function ProjectSidebar({project,count,projects,selected,onSelect}:{project:string;count:number;running:boolean;projects?:Projects;selected?:string;onSelect?:(id:string)=>void}){
 const [search,setSearch]=useState('');const [page,setPage]=useState(0);const {setOpenMobile}=useSidebar()
 const items=(projects?.items||[]).filter(p=>p.name.toLocaleLowerCase('ru').includes(search.toLocaleLowerCase('ru')))
 const pages=Math.max(1,Math.ceil(items.length/8));const current=Math.min(page,pages-1)
 return <Sidebar><SidebarHeader><strong className="brand"><span className="brand-mark">tw</span>tw</strong><p className="muted">Рабочее пространство</p></SidebarHeader><SidebarContent><SidebarGroup><SidebarGroupLabel>ПРОЕКТЫ</SidebarGroupLabel><input aria-label="Поиск проектов" placeholder="Найти проект…" value={search} onChange={event=>{setSearch(event.target.value);setPage(0)}}/><nav aria-label="Проекты" className="project-list">{items.slice(current*8,current*8+8).map(p=><button key={p.id} type="button" aria-current={selected===p.id?'page':undefined} onClick={()=>{onSelect?.(p.id);setOpenMobile(false)}}><AppIcon name="folder"/>{p.name}</button>)}</nav>{!projects?.items.length&&<p className="muted">{project}</p>}{projects?.items.length&&!items.length?<p>Проекты не найдены.</p>:null}{pages>1&&<nav className="pagination" aria-label="Страницы проектов"><button disabled={!current} onClick={()=>setPage(current-1)}>Назад</button><span>{current+1}/{pages}</span><button disabled={current===pages-1} onClick={()=>setPage(current+1)}>Далее</button></nav>}{projects?.connect_url&&<a href={projects.connect_url} target="_blank" rel="noopener noreferrer">Подключить проект</a>}</SidebarGroup></SidebarContent><SidebarFooter><p className="muted">Задач в проекте: {count}</p><p className="muted">Локальная панель управления</p></SidebarFooter></Sidebar>
}
