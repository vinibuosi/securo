import type { Asset } from '@/types'
// Money is summed, never percentages. Uncertain withdrawals invalidate return.
export function positionGroup(positions: Pick<Asset, 'current_value' | 'purchase_price' | 'external_metadata'>[]) {
  const current = positions.reduce((s, p) => s + Number(p.current_value ?? 0), 0)
  const complete = positions.length > 0 && positions.every(p => p.purchase_price != null && !p.external_metadata?._securo_return_incomplete)
  const invested = complete ? positions.reduce((s, p) => s + Number(p.purchase_price), 0) : null
  return { current, invested, profit: invested == null ? null : current - invested }
}
