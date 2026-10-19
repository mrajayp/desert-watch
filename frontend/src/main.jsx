import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { initialLang, loadCatalogue, setLang } from './i18n'
import './styles.css'

// the Arabic catalogue is its own chunk: fetched before the first render only when the interface starts
// in Arabic (a failed fetch falls back to English rather than a blank page)
const lang = initialLang()
loadCatalogue(lang).catch(() => {}).then(() => {
  setLang(lang)
  createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <BrowserRouter><App /></BrowserRouter>
    </React.StrictMode>,
  )
})
