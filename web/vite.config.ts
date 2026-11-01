import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// GitHub Pages serves the site under the repository name; locally it is the root.
export default defineConfig({
  base: process.env.BASE_PATH ?? '/',
  plugins: [svelte()],
})
