// Search lens only: the words behind the number. The word list sets its size, so it is shown with every gap.
import { isAr, t } from '../i18n.js'
import { weekRange } from '../charts/trendText'

// "the week of 5 to 11 Oct 2026" or "the weeks of A, B and C" (the API sends each week's Monday)
function weeksOf(weeks) {
  const w = [...weeks].sort().map(weekRange)
  return w.length === 1 ? t('the week of {week}', { week: w[0] })
    : t('the weeks of {weeks} and {last}', { weeks: w.slice(0, -1).join(isAr() ? '، ' : ', '), last: w[w.length - 1] })
}

export default function SearchTerms({ search, missing }) {
  if (!search) return null
  return (
    <>
      <h3>{t('Search words')}</h3>
      {!search.measured ? (
        <p className="small muted">{search.unmeasured_reason || t('Too few people in Libya search for this theme for Google to report it, so there is nothing to compare its coverage with.')}</p>
      ) : (
        <>
          <ul className="list small">
            {search.terms.map((t) => (
              <li key={t.ar}><span className="ar" dir="rtl" lang="ar">{t.ar}</span>{t.en && <span className="muted"> · {t.en}</span>}</li>))}
          </ul>
          <p className="small muted">
            {t('We count Google searches from people in Libya that contain any of these words. The word list sets the size of the number. Other words would give another number, so we only compare a theme with its own past.')}
            {' '}{t('Each week is measured against searches for an everyday word,')} <span className="ar" dir="rtl" lang="ar">{search.anchor.ar}</span>
            {search.anchor.en && <> ({search.anchor.en})</>}. {t('Data source: Google Trends.')}
          </p>
        </>)}
      {search.measured && missing?.length > 0 && (
        <p className="small muted">
          {t('These 4 weeks are not judged because there is no search data for {weeks}. Google holds back weeks with too few searches, and a week only gets data at the first import after it ends.', { weeks: weeksOf(missing) })}
        </p>)}
    </>
  )
}
