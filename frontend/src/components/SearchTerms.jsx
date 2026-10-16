// Search lens only: the words behind the number. The word list sets its size, so it is shown with every gap.
// "the week of A" or "the weeks of A, B and C"
function weeksOf(weeks) {
  const w = [...weeks].sort()
  return w.length === 1 ? `the week of ${w[0]}` : `the weeks of ${w.slice(0, -1).join(', ')} and ${w[w.length - 1]}`
}

export default function SearchTerms({ search, missing }) {
  if (!search) return null
  return (
    <>
      <h3>Search words</h3>
      {!search.measured ? (
        <p className="small muted">{search.unmeasured_reason || 'We do not measure searches for this theme.'}</p>
      ) : (
        <>
          <ul className="list small">
            {search.terms.map((t) => (
              <li key={t.ar}><span className="ar" dir="rtl" lang="ar">{t.ar}</span>{t.en && <span className="muted"> · {t.en}</span>}</li>))}
          </ul>
          <p className="small muted">
            We count Google searches from people in Libya that contain any of these words. The word list sets the size
            of the number. Other words would give another number, so we only compare a theme with its own past.
            Each week is measured against searches for an everyday word, <span className="ar" dir="rtl" lang="ar">{search.anchor.ar}</span>
            {search.anchor.en && <> ({search.anchor.en})</>}. Data source: Google Trends.
          </p>
        </>)}
      {search.measured && missing?.length > 0 && (
        <p className="small muted">
          This window is not scored because there is no search data for {weeksOf(missing)}. Google holds back weeks
          with too few searches, and a week only gets data at the first import after it ends.
        </p>)}
    </>
  )
}
