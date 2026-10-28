import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { accounts } from '@/lib/api'
import type { Account } from '@/types'
import { useWorkspace } from '@/contexts/workspace-context'
import { toast } from 'sonner'

export function ReservedBalances({ account, display }: { account: Account; display: (amount: number, currency: string) => string }) {
  const { t } = useTranslation()
  const { canWrite } = useWorkspace()
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: ({ id, relationship, classification }: { id: string; relationship: string; classification?: string }) => accounts.reconcileReserve(account.id, id, relationship, classification),
    onSuccess: () => client.invalidateQueries(),
    onError: () => toast.error(t('openfinance.reconciliationError', 'Não foi possível salvar a reconciliação.')),
  })
  if (!account.reserves?.length) return null
  return <section className="rounded-xl border p-4 mb-6 space-y-3" aria-label={t('openfinance.reserves', 'Cofrinhos e reservas')}>
    <h2 className="font-semibold">{t('openfinance.reserves', 'Cofrinhos e reservas')}</h2>
    <p className="text-sm text-muted-foreground">{t('openfinance.reserveHelp', 'Confirme a relação com o saldo da conta e com os investimentos. Reservas pendentes não acrescentam patrimônio.')}</p>
    {account.reserves.map(reserve => <article key={reserve.id} className="border-t pt-3 space-y-1">
      <h3>{reserve.name} · {account.institution_name ?? account.name}</h3>
      <p>{reserve.amount == null ? t('openfinance.missingValue', 'Valor indisponível') : display(Number(reserve.amount), reserve.currency)} · {reserve.currency}</p>
      <p className="text-xs text-muted-foreground">{t(`openfinance.${reserve.classification}`, reserve.classification)} · Pluggy /accounts · {reserve.updated_at}</p>
      <label className="text-sm">{t('openfinance.classification', 'Classificação')}{' '}
        <select value={reserve.classification} disabled={!canWrite || mutation.isPending} onChange={e => mutation.mutate({ id: reserve.id, relationship: reserve.reconciliation, classification: e.target.value })}>
          <option value="generic_reserve">{t('openfinance.generic_reserve', 'Reserva genérica')}</option>
          <option value="savings_pot">{t('openfinance.savings_pot', 'Cofrinho')}</option>
          <option value="blocked_balance">{t('openfinance.blocked_balance', 'Saldo bloqueado')}</option>
          <option value="judicial_block">{t('openfinance.judicial_block', 'Bloqueio judicial')}</option>
        </select>
      </label>
      {reserve.stale && <p role="status">{t('openfinance.staleReserve', 'Último valor conhecido; atualização pendente. Valor adicional no patrimônio: zero.')}</p>}
      <label className="text-sm">{t('openfinance.reconciliation', 'Reconciliação patrimonial')}{' '}
        <select aria-label={`${t('openfinance.reconciliation', 'Reconciliação patrimonial')}: ${reserve.name}`} value={reserve.investment_id ? 'investment' : reserve.reconciliation}
          disabled={!canWrite || mutation.isPending || !!reserve.investment_id}
          onChange={e => mutation.mutate({ id: reserve.id, relationship: e.target.value })}>
          <option value="pending">{t('openfinance.pending', 'Pendente — sem valor adicional')}</option>
          <option value="included">{t('openfinance.included', 'Já incluída no saldo bancário')}</option>
          <option value="investment">{t('openfinance.investment', 'Já representada nos investimentos')}</option>
          <option value="outside" disabled={!reserve.stable_identity || reserve.stale}>{t('openfinance.outside', 'Confirmo: fora da conta e dos investimentos')}</option>
        </select>
      </label>
    </article>)}
  </section>
}
