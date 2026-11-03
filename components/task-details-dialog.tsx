'use client'
import type { ReactNode } from 'react'
import { Dialog } from 'radix-ui'
import { AppIcon } from './app-icon'
export function TaskDetailsDialog({title,children,icon='document',iconOnly=false}:{title:string;children:ReactNode;icon?:string;iconOnly?:boolean}){
 return <Dialog.Root><Dialog.Trigger aria-label={title} data-tip={iconOnly?title:undefined} className={iconOnly?'detail-button detail-icon':'detail-button'}><AppIcon name={icon}/>{!iconOnly&&title}</Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="details-dialog" aria-describedby={undefined}><header><Dialog.Title>{title}</Dialog.Title><Dialog.Close aria-label="Закрыть"><AppIcon name="close"/></Dialog.Close></header><div className="dialog-body">{children}</div></Dialog.Content></Dialog.Portal></Dialog.Root>
}
