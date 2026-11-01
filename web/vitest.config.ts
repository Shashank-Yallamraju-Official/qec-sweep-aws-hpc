import { defineConfig } from 'vitest/config'

// Unit tests live beside the code they test; tests/ holds the Playwright specs,
// which vitest must not collect. They are plain TypeScript, so no Svelte plugin is needed.
export default defineConfig({
  test: { include: ['src/**/*.test.ts'] },
})
