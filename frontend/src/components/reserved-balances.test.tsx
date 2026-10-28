import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import { ReservedBalances } from './reserved-balances'
import type { Account } from '@/types'
vi.mock('@/contexts/workspace-context', () => ({ useWorkspace: () => ({ canWrite: true }) }))
vi.mock('@/lib/api', () => ({ accounts: { reconcileReserve: vi.fn() } }))
describe('reserved balances', () => {
  it('shows the disclosure without claiming that it increases net worth', () => {
    renderWithProviders(<ReservedBalances account={{ id: 'a', name: 'Mercado Pago', reserves: [
      { id: 'r', name: 'Viagem', amount: '8720.00', currency: 'BRL', classification: 'savings_pot', reconciliation: 'pending', stable_identity: true, updated_at: '2026-10-28' },
    ] } as Account} display={(n, c) => `${c} ${n}`} />)
    expect(screen.getByText('BRL 8720 · BRL')).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveValue('pending')
    expect(screen.getByText(/não acrescentam patrimônio/)).toBeInTheDocument()
  })
})
