/// <reference types="vitest/config" />
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig, type Plugin } from 'vite'

// The stylesheet is a kilobyte; inlined, the first paint waits for nothing but the HTML.
function inlineCss(): Plugin {
  return {
    name: 'inline-css',
    apply: 'build',
    enforce: 'post',
    generateBundle(_, bundle) {
      const html = bundle['index.html']
      if (!html || html.type !== 'asset' || typeof html.source !== 'string') return
      for (const asset of Object.values(bundle)) {
        if (asset.type !== 'asset' || !asset.fileName.endsWith('.css')) continue
        const link = new RegExp(`<link[^>]*rel="stylesheet"[^>]*href="[^"]*${asset.fileName}"[^>]*>`)
        if (!link.test(html.source)) continue
        html.source = html.source.replace(link, `<style>${String(asset.source)}</style>`)
        delete bundle[asset.fileName]
      }
    },
  }
}

// GitHub Pages serves the site under the repository name; locally it is the root.
export default defineConfig({
  base: process.env.BASE_PATH ?? '/',
  plugins: [svelte(), inlineCss()],
  // Unit tests live beside the code; tests/ holds the Playwright specs, which vitest must not collect.
  test: { include: ['src/**/*.test.ts'] },
})
