import { it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CommandPalette } from '@/components/command-palette'

it('находит и открывает консоль воркера при поиске', () => {
  const onToggleTerminal = vi.fn()
  const onClose = vi.fn()
  render(
    <CommandPalette
      isOpen={true}
      onClose={onClose}
      tasks={[]}
      currentProjectName="tw-web"
      onSelectTask={vi.fn()}
      onToggleTerminal={onToggleTerminal}
    />
  )
  expect(screen.getByText('Консоль воркера')).toBeTruthy()
  fireEvent.change(screen.getByPlaceholderText(/Поиск задач/), { target: { value: 'консоль' } })
  expect(screen.getByText('Консоль воркера')).toBeTruthy()
  fireEvent.click(screen.getByText('Консоль воркера'))
  expect(onToggleTerminal).toHaveBeenCalledTimes(1)
  expect(onClose).toHaveBeenCalledTimes(1)
})

it('выполняет действие консоли по нажатию Enter', () => {
  const onToggleTerminal = vi.fn()
  const onClose = vi.fn()
  render(
    <CommandPalette
      isOpen={true}
      onClose={onClose}
      tasks={[]}
      currentProjectName="tw-web"
      onSelectTask={vi.fn()}
      onToggleTerminal={onToggleTerminal}
    />
  )
  const input = screen.getByPlaceholderText(/Поиск задач/)
  fireEvent.change(input, { target: { value: 'терминал' } })
  fireEvent.keyDown(window, { key: 'Enter' })
  expect(onToggleTerminal).toHaveBeenCalledTimes(1)
  expect(onClose).toHaveBeenCalledTimes(1)
})
