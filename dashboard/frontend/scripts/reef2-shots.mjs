// Screenshots of the aquarium at desktop and mobile widths. Usage: node scripts/reef2-shots.mjs [baseUrl] [outDir]
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const base = process.argv[2] ?? 'http://localhost:5173'
const out = process.argv[3] ?? 'screenshots/reef2'
mkdirSync(out, { recursive: true })

const pages = [
  ['aquarium', '/'],
  ['proposal-funded-win', '/proposal/momentum%3A2026-08-19%3ADIPC'],
  ['proposal-funded-loss', '/proposal/contrarian%3A2026-09-15%3ADIPB'],
  ['proposal-declined', '/proposal/momentum%3A2026-08-19%3ADIPA'],
  ['lab', '/lab'],
  ['team-inactive', '/team/value'],
]
const sizes = [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 393, height: 852 }]]

const browser = await chromium.launch()
for (const [sizeName, viewport] of sizes) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: sizeName === 'mobile' ? 2 : 1 })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  for (const [name, path] of pages) {
    await page.goto(base + path, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    await page.screenshot({ path: `${out}/${name}-${sizeName}.png`, fullPage: true })
    console.log(sizeName, name, overflow > 0 ? `HORIZONTAL OVERFLOW ${overflow}px` : 'ok')
  }
  if (errors.length) console.log(sizeName, 'console errors:', errors.slice(0, 5))
  await ctx.close()
}
await browser.close()
