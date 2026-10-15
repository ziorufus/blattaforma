// Crea public/config.js a partire da config.example.js se non esiste ancora.
import { copyFileSync, existsSync } from 'node:fs'

const target = 'public/config.js'

if (!existsSync(target)) {
  copyFileSync('config.example.js', target)
  console.log(`Creato ${target} da config.example.js`)
}
