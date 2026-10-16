// Which week a lens opens on. The search lens has no data for the week in progress (Google data
// comes with the weekly import), so it opens on its latest scored week. Other lenses open on the latest week.
export function lensWeek(meta, lens) {
  const l = meta?.lenses?.find((x) => x.key === lens)
  return (lens === 'search' && l?.latest_scored_week) || meta?.latest_week || null
}

// Switching lens keeps a week the user picked. A week that was only the old lens's default moves to the new one's.
export function lensPatch(meta, filters, lens) {
  return { lens, week: filters.week === lensWeek(meta, filters.lens) ? lensWeek(meta, lens) : filters.week }
}
