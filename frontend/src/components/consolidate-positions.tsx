import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { assetGroups } from '@/lib/api'
import type { Asset } from '@/types'
import { toast } from 'sonner'

export function ConsolidatePositions({ positions, display }: { positions: Asset[]; display: (n: number, currency: string) => string }) {
  const { t } = useTranslation()
  const [name, setName] = useState('Caixinha')
  const [selected, setSelected] = useState<string[]>([])
  const client = useQueryClient()
  const candidates = positions.filter(p => p.source === 'pluggy' && !p.sell_date && !p.is_archived)
  const mutation = useMutation({
    mutationFn: () => assetGroups.consolidate(name, selected),
    onSuccess: () => { setSelected([]); void client.invalidateQueries() },
    onError: () => toast.error(t('openfinance.groupError', 'Selecione posições da mesma conexão e moeda.')),
  })
  if (!candidates.length) return null
  return <details className="rounded-xl border p-4">
    <summary>{t('openfinance.consolidate', 'Consolidar Caixinha / posições')}</summary>
    <p className="text-sm my-2">{t('openfinance.groupHelp', 'Sem identificador de Caixinha, selecione explicitamente os lotes. A consolidação preserva cada posição e não cria saldo adicional.')}</p>
    <label>{t('openfinance.groupName', 'Nome da Caixinha')} <input className="border rounded p-1" maxLength={100} value={name} onChange={e => setName(e.target.value)} /></label>
    <div className="max-h-64 overflow-auto my-3">{candidates.map(p => <label key={p.id} className="flex gap-2 my-1">
      <input type="checkbox" checked={selected.includes(p.id)} onChange={e => setSelected(e.target.checked ? [...selected, p.id] : selected.filter(id => id !== p.id))} />
      {p.name} · {display(Number(p.current_value ?? 0), p.currency)} · {p.purchase_date ?? '—'}
    </label>)}</div>
    <button className="border rounded p-2" disabled={mutation.isPending || !name.trim() || !selected.length} onClick={() => mutation.mutate()}>{t('openfinance.saveGroup', 'Salvar agrupamento')}</button>
  </details>
}
