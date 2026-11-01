// The theme: the system's unless the reader chose one, remembered in this browser only.
export type Theme = 'system' | 'light' | 'dark'

const KEY = 'theme'

export function storedTheme(): Theme {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

export function applyTheme(theme: Theme): void {
  if (theme === 'system') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = theme
  try {
    if (theme === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    // A private window may refuse; the choice then lasts for the page.
  }
}

/** Calls back whenever the colours in force change: the toggle, or the OS while following it. */
export function onThemeChange(callback: () => void): () => void {
  const media = matchMedia('(prefers-color-scheme: dark)')
  const observer = new MutationObserver(callback)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  media.addEventListener('change', callback)
  return () => {
    observer.disconnect()
    media.removeEventListener('change', callback)
  }
}
