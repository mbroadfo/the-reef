import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

mkdirSync('screenshots', { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1920, height: 1080 });
await page.goto('https://reef.broadfoot.consulting', { waitUntil: 'load', timeout: 30000 });
await page.waitForTimeout(5000);

await page.screenshot({ path: 'screenshots/full.png' });

// Clip sections
const clips = [
  { name: 'topbar',    clip: { x: 246, y: 0,   width: 1354, height: 88  } },
  { name: 'chart',     clip: { x: 246, y: 88,  width: 1354, height: 320 } },
  { name: 'aquarium',  clip: { x: 246, y: 390, width: 1354, height: 260 } },
  { name: 'tape',      clip: { x: 246, y: 650, width: 1354, height: 40  } },
  { name: 'bottom',    clip: { x: 246, y: 690, width: 1354, height: 380 } },
  { name: 'rail',      clip: { x: 1600, y: 88, width: 320,  height: 900 } },
];

for (const { name, clip } of clips) {
  await page.screenshot({ path: `screenshots/${name}.png`, clip });
  console.log(`${name}.png`);
}

await browser.close();
