// Runs only inside an isolated Modal Sandbox with networking disabled.
import fs from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import { chromium, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const task = JSON.parse(fs.readFileSync('/work/task.json', 'utf8'));
const out = '/work/result';
fs.mkdirSync(out, { recursive: true });
const report = { schema_version: '1.0', build: null, views: {}, tests: [], references: [],
  runtime_errors: [], console_errors: [], failed_requests: [], screenshots: {},
  limitations: ['Automated accessibility is incomplete.', 'Keyboard focus traces require human interpretation.', 'Visual quality and critique precision require independent human labels.'] };
const save = () => fs.writeFileSync(`${out}/evidence.json`, JSON.stringify(report));
const build = spawnSync('npm', ['run', 'build'], { cwd: '/work', encoding: 'utf8', timeout: 90_000, maxBuffer: 1_000_000 });
report.build = { passed: build.status === 0, exit_code: build.status, log: (build.stdout + build.stderr).slice(-16000), error: build.error?.message ?? null };
report.references.push({ type: 'build', ref: 'build' });
save();
if (!report.build.passed) process.exit(0);

const server = spawn('node', ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', '4173', '--strictPort'], { cwd: '/work', stdio: 'ignore' });
let browser;
try {
  for (let i = 0; i < 100; i++) {
    try { const response = await fetch('http://127.0.0.1:4173'); if (response.ok) break; } catch {}
    if (i === 99) throw new Error('Preview server did not start');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ headless: true });
  const viewports = { desktop: [1440, 900], tablet: [768, 1024], mobile: [390, 844], stress: [320, 800], wide: [1920, 1080] };
  for (const [name, [width, height]] of Object.entries(viewports)) {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, locale: 'en-US', timezoneId: 'UTC', colorScheme: 'light', reducedMotion: 'reduce', serviceWorkers: 'block' });
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      return url.origin === 'http://127.0.0.1:4173' || ['data:', 'blob:'].includes(url.protocol) ? route.continue() : route.abort('blockedbyclient');
    });
    await context.addInitScript(() => {
      let seed = 42;
      Math.random = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
      const FixedDate = Date;
      class FrozenDate extends FixedDate { constructor(...args) { super(...(args.length ? args : ['2026-11-07T12:00:00Z'])); } static now() { return 1794052800000; } }
      globalThis.Date = FrozenDate;
    });
    const page = await context.newPage();
    page.setDefaultTimeout(2500);
    page.on('pageerror', error => report.runtime_errors.push({ view: name, message: error.message }));
    page.on('console', msg => { if (msg.type() === 'error') report.console_errors.push({ view: name, message: msg.text().slice(0, 1000) }); });
    page.on('requestfailed', request => report.failed_requests.push({ view: name, url: request.url(), error: request.failure()?.errorText }));
    page.on('response', response => { if (response.status() >= 400) report.failed_requests.push({ view: name, url: response.url(), status: response.status() }); });
    try {
      await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle', timeout: 15000 });
      await page.evaluate(() => document.fonts.ready);
      const metrics = await page.evaluate(() => ({
        horizontal_overflow: document.documentElement.scrollWidth > innerWidth + 1,
        scroll_width: document.documentElement.scrollWidth, viewport_width: innerWidth,
        scroll_height: document.documentElement.scrollHeight, viewport_height: innerHeight,
        text_length: document.body.innerText.length,
        broken_images: [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.getAttribute('src')),
        controls: [...document.querySelectorAll('button,input,select,textarea,a')].slice(0, 100).map(e => ({ tag: e.tagName, text: e.textContent?.slice(0, 100), label: e.getAttribute('aria-label'), test_id: e.getAttribute('data-testid') })),
      }));
      const screenshot = `${name}.png`;
      await page.screenshot({ path: `${out}/${screenshot}`, fullPage: false, animations: 'disabled', timeout: 10000 });
      report.screenshots[name] = screenshot;
      const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
      report.views[name] = { ...metrics, accessibility: accessibility.violations, accessibility_incomplete: accessibility.incomplete,
        dom_snapshot: await page.locator('body').ariaSnapshot(), keyboard_trace: [] };
      for (const type of ['screenshot', 'accessibility', 'overflow', 'runtime']) report.references.push({ type, ref: name });
      for (let i = 0; i < 8; i++) {
        await page.keyboard.press('Tab');
        report.views[name].keyboard_trace.push(await page.evaluate(() => {
          const e = document.activeElement; const r = e.getBoundingClientRect();
          return { tag: e.tagName, text: e.textContent?.slice(0, 80), test_id: e.getAttribute('data-testid'), visible: r.width > 0 && r.height > 0 };
        }));
      }
      if (['desktop', 'mobile'].includes(name)) {
        for (const test of task.tests) {
          await page.reload({ waitUntil: 'networkidle' });
          const result = { id: `${test.id}:${name}`, view: name, passed: true, steps: [] };
          for (const instruction of test.steps) {
            const first = instruction.test_id.endsWith(':first');
            let locator = page.getByTestId(instruction.test_id.replace(/:first$/, ''));
            if (first) locator = locator.first();
            try {
              switch (instruction.action) {
                case 'click': await locator.click(); break;
                case 'fill': await locator.fill(instruction.value); break;
                case 'select': await locator.selectOption(instruction.value); break;
                case 'press': await locator.press(instruction.value); break;
                case 'expect_visible': await expect(locator).toBeVisible(); break;
                case 'expect_hidden': await expect(locator).toBeHidden(); break;
                case 'expect_text': await expect(locator).toContainText(instruction.value); break;
                case 'expect_count': await expect(locator).toHaveCount(Number(instruction.value)); break;
                default: throw new Error(`Unknown action ${instruction.action}`);
              }
              result.steps.push({ ...instruction, passed: true });
            } catch (error) {
              result.passed = false;
              result.steps.push({ ...instruction, passed: false, error: error.message.slice(0, 1500) });
              break;
            }
          }
          report.tests.push(result);
          report.references.push({ type: 'test', ref: result.id });
          const stateName = `${name}-after`;
          await page.screenshot({ path: `${out}/${stateName}.png`, animations: 'disabled' });
          report.screenshots[stateName] = `${stateName}.png`;
          report.references.push({ type: 'screenshot', ref: stateName });
          const afterAxe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
          report.views[name].after_accessibility = afterAxe.violations;
          report.views[name].after_overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
        }
      }
    } catch (error) {
      report.views[name] = { ...report.views[name], harness_error: error.message };
    } finally {
      await context.close();
      save();
    }
  }
} catch (error) {
  report.harness_error = error.message;
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
  save();
}
