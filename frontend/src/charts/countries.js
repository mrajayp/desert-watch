// Country names in the interface language. The API sends an outlet's base country in English; the
// catalogue has Arabic for the countries the register uses, and any other country gets the browser's
// own Arabic name. Kept apart from RegionalNetwork.jsx so the outlet dialog and the Contribute queue
// (main chunk) do not pull the map code (d3-geo) in with it.
import { isAr, t } from '../i18n'

export function countryName(c) {
  if (!c) return ''
  const names = {
    Libya: t('Libya'), 'United Kingdom': t('United Kingdom'), Qatar: t('Qatar'), 'United Arab Emirates': t('United Arab Emirates'),
    Egypt: t('Egypt'), Turkey: t('Turkey'), France: t('France'), Italy: t('Italy'), Lebanon: t('Lebanon'), 'Saudi Arabia': t('Saudi Arabia'),
    Greece: t('Greece'), Malta: t('Malta'), Morocco: t('Morocco'), Syria: t('Syria'), Israel: t('Israel'), Palestine: t('Palestine'),
    Nigeria: t('Nigeria'), Ukraine: t('Ukraine'), 'United States': t('United States'), Switzerland: t('Switzerland'), Tunisia: t('Tunisia'),
    Germany: t('Germany'), Jordan: t('Jordan'), Algeria: t('Algeria'), Sudan: t('Sudan'), Iraq: t('Iraq'), Russia: t('Russia'),
    Spain: t('Spain'), Belgium: t('Belgium'), Netherlands: t('Netherlands'), Kuwait: t('Kuwait'), Bahrain: t('Bahrain'), Oman: t('Oman'),
    Chad: t('Chad'), Niger: t('Niger'), Mali: t('Mali'), Canada: t('Canada'), Iran: t('Iran'), Austria: t('Austria'), Sweden: t('Sweden'),
    Norway: t('Norway'), Denmark: t('Denmark'), Portugal: t('Portugal'), Yemen: t('Yemen'), India: t('India'), Pakistan: t('Pakistan'),
    Australia: t('Australia'),
  }
  return names[c] || (isAr() && regionAr(c)) || c
}

// any other country: the browser's own Arabic name, found through its English name
let REGIONS = null
function regionAr(name) {
  try {
    if (!REGIONS) {
      const en = new Intl.DisplayNames(['en'], { type: 'region' }), ar = new Intl.DisplayNames(['ar'], { type: 'region' })
      REGIONS = new Map()
      for (let a = 65; a < 91; a++) for (let b = 65; b < 91; b++) {
        const code = String.fromCharCode(a, b)
        const n = en.of(code)
        if (n && n !== code) REGIONS.set(n, ar.of(code))
      }
    }
    return REGIONS.get(name) || ''
  } catch { return '' }
}
