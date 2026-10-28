import { useTranslation } from 'react-i18next'
import type { Asset } from '@/types'

export function PositionProvenance({ asset, display }: { asset: Asset; display: (n: number, c: string) => string }) {
  const { t } = useTranslation()
  if (asset.source !== 'pluggy') return null
  const meta = asset.external_metadata ?? {}
  return <dl className="grid sm:grid-cols-2 gap-2 px-4 py-3 text-xs border-t">
    <div><dt>{t('openfinance.purchaseDate', 'Data de aquisição')}</dt><dd>{asset.purchase_date ?? '—'}</dd></div>
    <div><dt>{t('openfinance.maturityDate', 'Vencimento da aplicação')}</dt><dd>{asset.maturity_date ?? '—'}</dd></div>
    <div><dt>{t('openfinance.issuer', 'Emissor')}</dt><dd>{typeof meta.issuer === 'string' ? meta.issuer : '—'}</dd></div>
    <div><dt>{t('openfinance.taxes', 'Impostos informados')}</dt><dd>{meta.taxes == null ? '—' : display(Number(meta.taxes), asset.currency)} / {meta.taxes2 == null ? '—' : display(Number(meta.taxes2), asset.currency)}</dd></div>
    {meta._securo_reconciliation_pending === true && <div className="sm:col-span-2 text-amber-700"><dt>{t('openfinance.reportedPending', 'Valor informado pela instituição, pendente de reconciliação')}</dt><dd>{display(Number(meta._securo_reported_value), asset.currency)}</dd></div>}
  </dl>
}
