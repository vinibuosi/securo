import { describe, expect, it } from 'vitest'
import { positionGroup } from './position-group'
describe('Caixinha position rollup', () => {
  it('sums lots and principal, never return percentages', () => {
    const lots = [100, 200, 300].map(n => ({ current_value: n * 1.01, purchase_price: n }))
    expect(positionGroup(lots)).toEqual({ current: 606, invested: 600, profit: 6 })
  })
  it('does not classify a deposit or partial withdrawal as return', () => {
    expect(positionGroup([{ current_value: 100, purchase_price: null }]).profit).toBeNull()
    expect(positionGroup([{ current_value: 80, purchase_price: 100, external_metadata: { _securo_return_incomplete: true } }]).profit).toBeNull()
  })
})
