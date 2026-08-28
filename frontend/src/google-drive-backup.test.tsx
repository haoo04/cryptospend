// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { GoogleDriveSettings } from './App'
import type { GoogleDriveBackupResult, GoogleDriveBackupStatus } from './api'

const readyStatus: GoogleDriveBackupStatus = {
  configured: true,
  supported: true,
  connected: false,
  folder_name: 'CryptoSpend Backups',
  message: 'Connect Google Drive to enable backups.',
}

const connectedStatus: GoogleDriveBackupStatus = {
  ...readyStatus,
  connected: true,
  message: null,
}

const backupResult: GoogleDriveBackupResult = {
  id: 'file-1',
  name: 'cryptospend-backup-20260829T120000Z.db',
  web_view_link: 'https://drive.google.com/file/file-1',
  created_at: '2026-08-29T12:00:00Z',
}

function renderSettings(
  status: GoogleDriveBackupStatus,
  overrides: Partial<React.ComponentProps<typeof GoogleDriveSettings>> = {},
) {
  return render(
    <GoogleDriveSettings
      status={status}
      lastBackup={null}
      busy={false}
      onConnect={vi.fn()}
      onBackup={vi.fn(async () => undefined)}
      onRefreshStatus={vi.fn(async () => status)}
      {...overrides}
    />,
  )
}

describe('Google Drive backup settings', () => {
  it('keeps backup disabled until Google Drive is connected', () => {
    const onConnect = vi.fn()
    const view = renderSettings(readyStatus, { onConnect })

    expect(screen.getByText('READY TO CONNECT')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Backup database' })).toHaveProperty('disabled', true)
    fireEvent.click(screen.getByRole('button', { name: 'Connect Google Drive' }))
    expect(onConnect).toHaveBeenCalledTimes(1)

    view.unmount()
  })

  it('starts an upload and displays the returned Drive file', async () => {
    const onBackup = vi.fn(async () => undefined)
    renderSettings(connectedStatus, { lastBackup: backupResult, onBackup })

    expect(screen.getByText('CONNECTED')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Backup database' }))

    await waitFor(() => expect(onBackup).toHaveBeenCalledTimes(1))
    expect(screen.getByText(backupResult.name)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open in Google Drive' })).toHaveProperty('href', backupResult.web_view_link)
  })
})
