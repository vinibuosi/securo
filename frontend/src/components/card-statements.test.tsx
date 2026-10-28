import { describe, expect, it, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import { CardStatements } from './card-statements'
import type { Account } from '@/types'
const { billingOverview } = vi.hoisted(() => ({ billingOverview: vi.fn() }))
vi.mock('@/lib/api', () => ({ accounts: { billingOverview } }))
describe('monthly statements', () => {
  it('navigates bills with equal due dates by id and separates card debt', async () => {
    billingOverview.mockResolvedValue({ total_debt: 1200, currency: 'BRL', pending: [], future_installments: [], unresolved: [], aggregate_purchases: [], cycles: [
      { id: 'one', external_id: 'oct-a', due_date: '2026-10-05', closing_date: '2026-09-25', currency: 'BRL', total: 100, paid: 40, remaining: 60, status: 'partially_paid', detail_total: 100, discrepancy: 0, incomplete: false, estimated: false, transactions: [{ id: 't', description: 'Parcela loja', amount: 100, currency: 'BRL', date: '2026-09-10', type: 'debit', total_installments: 12, installment_number: 1 }] },
      { id: 'two', external_id: 'oct-b', due_date: '2026-10-05', currency: 'BRL', total: 200, paid: null, remaining: null, status: 'closed', detail_total: 200, incomplete: true, estimated: false, transactions: [] },
    ] })
    renderWithProviders(<CardStatements account={{ id: 'xp', available_credit: 800, currency: 'BRL' } as Account} display={(n, c) => `${c} ${n}`} />)
    const picker = await screen.findByRole('combobox')
    expect(screen.getByText('BRL 1200')).toBeInTheDocument()
    expect(screen.getByText('BRL 60')).toBeInTheDocument()
    expect(screen.getByText('1 / 12')).toBeInTheDocument()
    fireEvent.change(picker, { target: { value: 'two' } })
    expect(picker).toHaveValue('two')
    expect(screen.queryByText(/Parcela loja/)).not.toBeInTheDocument()
    expect(screen.getByText('BRL 1200')).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})
