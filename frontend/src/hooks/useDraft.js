// A text the person is still writing, kept in sessionStorage under a key for the object it belongs to
// (a comment on gap 3:7, the note on a vote), so that switching language, which remounts the whole
// app, or opening another panel and coming back loses nothing. clear() on a successful submit.
//   const [body, setBody, clearBody] = useDraft(`comment:${objectType}:${objectKey}`)
import { useCallback, useState } from 'react'

const read = (k) => { try { return sessionStorage.getItem(`dw-draft-${k}`) ?? '' } catch { return '' } }
const write = (k, v) => { try { v ? sessionStorage.setItem(`dw-draft-${k}`, v) : sessionStorage.removeItem(`dw-draft-${k}`) } catch { /* storage blocked */ } }

export function useDraft(key, initial = '') {
  const [value, setValueState] = useState(() => read(key) || initial)
  const setValue = useCallback((v) => { setValueState(v); write(key, v) }, [key])
  const clear = useCallback(() => { setValueState(''); write(key, '') }, [key])
  return [value, setValue, clear]
}
