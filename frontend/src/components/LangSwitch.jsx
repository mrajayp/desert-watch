import { t } from '../i18n'

// English / Arabic switch for the whole interface. Each button names its language in that language.
export default function LangSwitch({ lang, setLang }) {
  return (
    <div className="seg" role="group" aria-label={t('Interface language')}>
      <button lang="en" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
      <button lang="ar" aria-pressed={lang === 'ar'} onClick={() => setLang('ar')}>عربي</button>
    </div>
  )
}
