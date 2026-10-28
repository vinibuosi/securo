import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, t } from '@/test/utils'
import { ConsolidatePositions } from './consolidate-positions'
import type { Asset } from '@/types'
const { consolidate } = vi.hoisted(() => ({ consolidate: vi.fn().mockResolvedValue({ id: 'box' }) }))
vi.mock('@/lib/api', () => ({ assetGroups: { consolidate } }))
describe('manual Caixinha grouping', () => {
  it('submits selected lot ids without creating an extra asset', async () => {
    const lots = [1, 2, 3].map(i => ({ id: `lot-${i}`, name: `RDB ${i}`, source: 'pluggy', currency: 'BRL', current_value: i * 101, purchase_date: '2026-09-01' }) as Asset)
    renderWithProviders(<ConsolidatePositions positions={lots} display={(n, c) => `${c} ${n}`} />)
    fireEvent.click(screen.getByText(t('openfinance.consolidate')))
    for (const checkbox of screen.getAllByRole('checkbox')) fireEvent.click(checkbox)
    fireEvent.click(screen.getByRole('button', { name: t('openfinance.saveGroup') }))
    await waitFor(() => expect(consolidate).toHaveBeenCalledWith('Caixinha', ['lot-1', 'lot-2', 'lot-3']))
  })
})
