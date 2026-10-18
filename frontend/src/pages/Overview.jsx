import { qs } from '../api'
import { useApp } from '../App'
import CoverageMap from '../components/CoverageMap'
import Filters from '../components/Filters'
import { ErrorBox } from '../components/Notices'
import SourceHealth from '../components/SourceHealth'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import { t } from '../i18n'

// The Map page (/map): who covers where, in both map views, with the outlets in view. The ranked gap
// list is the This week page (/), the heatmap and the language balance are the Trends page's By region block.
export default function Overview() {
  const { filters, version } = useApp()
  usePageTitle(t('Map'))
  const cellsQ = useApi(filters.week ? '/api/cells' + qs({ lens: filters.lens, week: filters.week }) : null, { deps: [version] })
  const cells = cellsQ.data?.cells || []
  return (
    <>
      <Filters />
      <main className="page">
        {cellsQ.error && <ErrorBox error={cellsQ.error} onRetry={cellsQ.retry} />}
        <section className="card">
          <CoverageMap cells={cells} outlets />
        </section>
        <SourceHealth compact />
      </main>
    </>
  )
}
