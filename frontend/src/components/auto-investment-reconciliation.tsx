import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { accounts, assets, connections } from '@/lib/api'
import type { Account } from '@/types'
import { useWorkspace } from '@/contexts/workspace-context'
import { toast } from 'sonner'

export function AutoInvestmentReconciliation({ account, display }: { account: Account; display: (n: number, c: string) => string }) {
  const { t } = useTranslation()
  const { canWrite } = useWorkspace()
  const client = useQueryClient()
  const [choices, setChoices] = useState<Record<string, string>>({})
  const { data } = useQuery({ queryKey: ['assets'], queryFn: () => assets.list() })
  const positions = (data ?? []).filter(a => a.connection_id === account.connection_id && a.currency === account.currency && a.source === 'pluggy' && !a.sell_date && !a.is_archived)
  const choiceFor = (a: (typeof positions)[number]) => choices[a.id] ?? (a.external_metadata?._securo_auto_invested ? 'mirror' : a.external_metadata?._securo_independent ? 'independent' : 'pending')
  const mutation = useMutation({
    mutationFn: async () => {
      await accounts.reconcileAutoInvestments(account.id, positions.filter(a => choiceFor(a) === 'mirror').map(a => a.id), positions.filter(a => choiceFor(a) === 'independent').map(a => a.id))
      if (account.connection_id) await connections.sync(account.connection_id)
    },
    onSuccess: () => client.invalidateQueries(),
    onError: () => toast.error(t('openfinance.autoError', 'Falha ao reconciliar ou sincronizar. Verifique a conexão e tente novamente.')),
  })
  return <details className="border rounded-xl p-4 mb-6">
    <summary>{t('openfinance.autoBalance', 'Saldo aplicado automaticamente')}: {display(Number(account.automatically_invested_balance), account.currency)}</summary>
    <p className="text-sm py-2">{t('openfinance.autoHelp', 'Confirme quais posições já estão no saldo bancário. Posições cuja relação é desconhecida ficam pendentes, com valor adicional zero no patrimônio. Igualdade entre valores não comprova identidade.')}</p>
    {positions.map(a => <label className="flex gap-2 my-2 text-sm" key={a.id}>
      {a.name} · {display(Number(a.external_metadata?._securo_reported_value ?? a.current_value ?? 0), a.currency)}
      <select aria-label={a.name} disabled={!canWrite || mutation.isPending} value={choiceFor(a)} onChange={e => setChoices({ ...choices, [a.id]: e.target.value })}>
        <option value="pending">{t('openfinance.pending', 'Pendente — sem valor adicional')}</option>
        <option value="mirror">{t('openfinance.included', 'Já incluída no saldo bancário')}</option>
        <option value="independent">{t('openfinance.independent', 'Investimento independente do saldo')}</option>
      </select>
    </label>)}
    {canWrite && <button className="border rounded p-2" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{t('openfinance.saveSync', 'Salvar e sincronizar')}</button>}
  </details>
}
