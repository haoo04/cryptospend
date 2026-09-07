// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FeedbackToast } from './App'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('operation feedback toast', () => {
  it('announces success politely and closes it after four seconds', () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    render(
      <FeedbackToast
        notice={{ id: 1, kind: 'success', title: 'Trade posted successfully.' }}
        onClose={onClose}
      />,
    )

    expect(screen.getByRole('status').textContent).toContain('Trade posted successfully.')
    act(() => vi.advanceTimersByTime(3999))
    expect(onClose).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(onClose).toHaveBeenCalledWith(1)
  })

  it('keeps errors visible until the user closes them', () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    render(
      <FeedbackToast
        notice={{ id: 2, kind: 'error', title: 'Unable to post trade', message: 'Rate is inconsistent.' }}
        onClose={onClose}
      />,
    )

    expect(screen.getByRole('alert').textContent).toContain('Rate is inconsistent.')
    act(() => vi.advanceTimersByTime(10_000))
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Close notification' }))
    expect(onClose).toHaveBeenCalledWith(2)
  })

  it('cleans up an old success timer when a warning replaces it', () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    const view = render(
      <FeedbackToast
        notice={{ id: 3, kind: 'success', title: 'Saved.' }}
        onClose={onClose}
      />,
    )
    view.rerender(
      <FeedbackToast
        notice={{ id: 4, kind: 'warning', title: 'Saved, but refresh failed' }}
        onClose={onClose}
      />,
    )

    act(() => vi.advanceTimersByTime(5000))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toContain('Saved, but refresh failed')
  })
})
