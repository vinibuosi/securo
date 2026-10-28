import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { accounts } from '@/lib/api'
import { localDateString } from '@/lib/date-utils'
import type { Account, StatementTransaction } from '@/types'

export function CardStatements({ account, display }: { account: Account; display: (n: number, c: string) => string }) {
  const { t } = useTranslation()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data, isLoading, isError } = useQuery({ queryKey: ['accounts', account.id, 'billing-overview'], queryFn: () => accounts.billingOverview(account.id) })
  if (isLoading) return <p role="status">{t('common.loading')}</p>
  if (isError || !data) return <p role="alert">{t('openfinance.statementError', 'Não foi possível carregar as faturas.')}</p>
  const today = localDateString(new Date())
  const selected = data.cycles.find(c => c.id === selectedId) ?? [...data.cycles].reverse().find(c => c.due_date >= today && !c.estimated) ?? data.cycles[0]
  const rows = (items: StatementTransaction[]) => <ul className="divide-y">{items.map(tx => <li className="py-2 text-sm" key={tx.id}>
    <span>{tx.date} · {tx.description}</span>{' '}
    <strong>{tx.type === 'credit' ? '−' : ''}{display(tx.amount, tx.currency)}</strong>{' '}
    {tx.total_installments != null && <span>{tx.installment_number ?? '?'} / {tx.total_installments}</span>}
    {tx.reason && <span className="block text-xs text-muted-foreground">{t(`openfinance.${tx.reason}`, tx.reason)}</span>}
    <span className="block text-xs text-muted-foreground">{tx.external_id}</span>
  </li>)}</ul>
  return <div className="space-y-5">
    <div className="grid sm:grid-cols-2 gap-3">
      <p className="border rounded-xl p-4">{t('openfinance.totalDebt', 'Saldo devedor total do cartão')}: <strong>{display(data.total_debt, data.currency)}</strong></p>
      <p className="border rounded-xl p-4">{t('accounts.availableCredit', 'Limite disponível')}: <strong>{account.available_credit == null ? '—' : display(account.available_credit, account.currency)}</strong></p>
    </div>
    <p className="text-sm text-muted-foreground">{t('openfinance.debtHelp', 'O patrimônio considera a dívida total informada pela instituição. A seleção de uma fatura não altera essa dívida.')}</p>
    <label>{t('openfinance.selectStatement', 'Selecionar fatura / ciclo')}{' '}
      <select className="border rounded p-2" aria-label={t('openfinance.selectStatement', 'Selecionar fatura / ciclo')} value={selected?.id ?? ''} onChange={e => setSelectedId(e.target.value)}>
        {data.cycles.map(c => <option key={c.id} value={c.id}>{c.due_date} · {c.external_id ?? t('openfinance.estimated', 'Estimativa')}</option>)}
      </select>
    </label>
    {selected ? <section className="border rounded-xl p-4 space-y-3">
      <h2 className="font-semibold">{t(`openfinance.status_${selected.status}`, selected.status)} · {selected.due_date}</h2>
      <dl className="grid sm:grid-cols-2 gap-2 text-sm">
        <div><dt>{t('openfinance.closing', 'Fechamento oficial')}</dt><dd>{selected.closing_date ?? '—'}</dd></div>
        <div><dt>{t('openfinance.due', 'Vencimento')}</dt><dd>{selected.due_date}</dd></div>
        <div><dt>{selected.estimated ? t('openfinance.estimatedTotal', 'Total estimado') : t('openfinance.officialTotal', 'Total oficial')}</dt><dd>{display(selected.total, selected.currency)}</dd></div>
        <div><dt>{t('openfinance.paid', 'Valor pago identificado')}</dt><dd>{selected.paid == null ? '—' : display(selected.paid, selected.currency)}</dd></div>
        <div><dt>{t('openfinance.remaining', 'Saldo restante identificado')}</dt><dd>{selected.remaining == null ? '—' : display(selected.remaining, selected.currency)}</dd></div>
        <div><dt>{t('openfinance.detailTotal', 'Soma dos lançamentos (sem pagamentos)')}</dt><dd>{display(selected.detail_total, selected.currency)}</dd></div>
      </dl>
      {selected.incomplete && <p role="status" className="text-sm text-amber-700">{t('openfinance.incompleteStatement', 'Dados incompletos ou divergentes; valores ausentes não são considerados zero.')}</p>}
      {selected.discrepancy != null && Math.abs(selected.discrepancy) > 0.005 && <p>{t('openfinance.discrepancy', 'Diferença entre total oficial e detalhes')}: {display(selected.discrepancy, selected.currency)}</p>}
      {rows(selected.transactions)}
    </section> : <p>{t('openfinance.noStatements', 'Ainda não há faturas disponíveis.')}</p>}
    <details className="border rounded-xl p-4"><summary>{t('openfinance.future', 'Parcelas futuras informadas pela instituição')} ({data.future_installments.length})</summary>{rows(data.future_installments)}</details>
    <details className="border rounded-xl p-4"><summary>{t('openfinance.pendingPurchases', 'Compras pendentes')} ({data.pending.length})</summary>{rows(data.pending)}</details>
    <details className="border rounded-xl p-4"><summary>{t('openfinance.aggregatePurchases', 'Compras agregadas / parcelamento sem ciclo confirmado')} ({data.aggregate_purchases.length})</summary>
      <p className="text-sm">{t('openfinance.aggregateHelp', 'O valor integral permanece disponível para auditoria. Não foi dividido nem somado às parcelas mensais. Sem vínculo confiável, a relação permanece pendente.')}</p>{rows(data.aggregate_purchases)}
    </details>
    <details className="border rounded-xl p-4"><summary>{t('openfinance.unresolved', 'Lançamentos sem ciclo confirmado')} ({data.unresolved.length})</summary>{rows(data.unresolved)}</details>
  </div>
}
