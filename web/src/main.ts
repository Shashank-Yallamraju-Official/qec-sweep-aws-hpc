import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

const target = document.getElementById('app')!
// The HTML carries a static copy of the shell for the first paint; the live one takes its place.
target.replaceChildren()
mount(App, { target })
