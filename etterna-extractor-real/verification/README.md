Run `npm install` then `npm test` in this folder with Node 24+. The runner copies miniapp sources into `.tmp`, performs strict TypeScript checks against SDK 3.4.0, and runs timing-metric/heatmap tests plus simulated UI/background tests. No physical device or API key is used. Fixtures are derived from the bundled game CSV sample. Do not copy this folder's test dependencies into your working miniapp.


Optional rendered layout regression, from this folder after `npm test`:

```bash
npm install --no-save playwright@1.57.0
npx playwright install chromium
node test-layout.cjs
```

This checks the CSV Song page at 320/393/430/768px with a deliberately centered starter root and a long heatmap. It checks page bounds, chart-only horizontal scrolling and mobile metric stacking. Screenshots stay in `.tmp`. An existing Chromium can be selected with CHROMIUM_PATH. The hosted runner may block browser launch; the normal simulated tests do not measure CSS geometry.
