/**
 * Visual review tool — captures the dashboard at multiple viewports.
 * Usage:
 *   node scripts/screenshot.js                      # screenshots live site
 *   node scripts/screenshot.js http://localhost:5173 # screenshots local dev server
 */
const { chromium } = require('playwright');
const path = require('path');

const URL = process.argv[2] || 'https://reef.broadfoot.consulting';

const VIEWPORTS = [
  { name: 'mobile-portrait',  width: 393,  height: 852  },  // iPhone 17 Pro portrait
  { name: 'mobile-landscape', width: 852,  height: 393  },  // iPhone 17 Pro landscape
  { name: 'tablet',           width: 768,  height: 1024 },  // iPad
  { name: 'desktop',          width: 1440, height: 900  },  // Desktop
];

async function run() {
  const browser = await chromium.launch();
  console.log(`Screenshotting ${URL}...\n`);

  for (const vp of VIEWPORTS) {
    const page = await browser.newPage();
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1500); // let charts render
    const outPath = path.join(__dirname, '..', 'screenshots', `${vp.name}.png`);
    await page.screenshot({ path: outPath });
    await page.close();
    console.log(`  [${vp.width}x${vp.height}] ${vp.name}.png`);
  }

  await browser.close();
  console.log('\nDone. Screenshots in dashboard/frontend/screenshots/');
}

run().catch(e => { console.error(e); process.exit(1); });
