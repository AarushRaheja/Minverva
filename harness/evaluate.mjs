// Audits an assembled project on its real stack: Postgres, the generated FastAPI app, and the built frontend.
// Derived from FrontEndSLM's audit/evaluate.mjs (audit 2.1). The viewports, axe scans and evidence shape are the
// same, so frontendslm's scoring and Critic read this evidence unchanged. See docs/consolidation/DECISIONS.md.
//
// It runs generated code. Run model output only inside the Modal sandbox (modal_apps/pipeline_app.py).
//
// Env: AUDIT_PROJECT (a scratch copy with frontend/node_modules), AUDIT_TASK, AUDIT_OUT, AUDIT_PYTHON,
//      AUDIT_PORT (default 4173), AUDIT_PG_BIN (optional).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { chromium, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const project = process.env.AUDIT_PROJECT;
const task = JSON.parse(fs.readFileSync(process.env.AUDIT_TASK, 'utf8'));
const out = process.env.AUDIT_OUT;
const python = process.env.AUDIT_PYTHON;
const port = Number(process.env.AUDIT_PORT || 4173);
const origin = `http://127.0.0.1:${port}`;
const bin = name => (process.env.AUDIT_PG_BIN ? path.join(process.env.AUDIT_PG_BIN, name) : name);
const VIEWPORTS = { desktop: [1440, 900], tablet: [768, 1024], mobile: [390, 844], stress: [320, 800], wide: [1920, 1080] };
const views = task.views ?? Object.keys(VIEWPORTS);
const testViews = task.test_views ?? ['desktop', 'mobile'];
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'];
const STATE_CHANGES = ['click', 'click_if_enabled', 'fill', 'select', 'press'];

fs.mkdirSync(out, { recursive: true });
const report = { schema_version: '1.0', audit_version: 'minerva-2.1', mode: task.mode, stack: {}, api_checks: [], build: null,
  views: {}, tests: [], references: [], runtime_errors: [], console_errors: [], failed_requests: [], screenshots: {},
  limitations: ['Automated accessibility is incomplete.', 'Keyboard focus traces require human interpretation.',
    'Visual quality and critique precision require independent human labels.'] };
const save = () => fs.writeFileSync(`${out}/evidence.json`, JSON.stringify(report));
const processes = [];
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'minerva-audit-'));
fs.chmodSync(tmp, 0o777);
const data = path.join(tmp, 'pg');
const asPostgres = process.getuid?.() === 0 ? ['runuser', '-u', 'postgres', '--'] : [];  // Postgres refuses to run as root

function run(command, args, options = {}) {
  const [file, ...rest] = [...(options.asPostgres ? asPostgres : []), command, ...args];
  const result = spawnSync(file, rest, { encoding: 'utf8', timeout: options.timeout ?? 90_000, maxBuffer: 4_000_000,
    cwd: options.cwd ?? project, env: { ...process.env, ...options.env } });
  return { ok: result.status === 0, exit_code: result.status, log: `${result.stdout ?? ''}${result.stderr ?? ''}`.slice(-8000),
    error: result.error?.message ?? null };
}

const freePort = () => 20000 + (process.pid % 20000);
// `verify` names a database that does not exist and runs no setup, so the app has to prepare everything itself.
const selfSetup = task.mode === 'verify';
const databaseUrl = `postgresql://postgres@127.0.0.1:${freePort()}/${selfSetup ? 'app' : 'postgres'}`;
const apiEnv = { DATABASE_URL: databaseUrl, PYTHONPATH: project, PYTHONDONTWRITEBYTECODE: '1', AUTO_BUILD_FRONTEND: '0' };

function startPostgres() {
  const init = run(bin('initdb'), ['-D', data, '-A', 'trust', '-U', 'postgres', '-E', 'UTF8'], { asPostgres: true });
  if (!init.ok) return init;
  return run(bin('pg_ctl'), ['-D', data, '-w', '-l', path.join(tmp, 'pg.log'),
    '-o', `-p ${freePort()} -c listen_addresses=127.0.0.1 -c unix_socket_directories=''`, 'start'], { asPostgres: true });
}

function resetDatabase() {
  if (!task.seed_sql) return { ok: true };
  const file = path.join(tmp, 'seed.sql');
  fs.writeFileSync(file, task.seed_sql);
  return run(bin('psql'), [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-q', '-f', file]);
}

async function startApi() {
  const log = fs.openSync(path.join(tmp, 'api.log'), 'a');
  const server = spawn(python, ['-m', 'uvicorn', 'src.app:app', '--host', '127.0.0.1', '--port', String(port), '--log-level', 'warning'],
    { cwd: project, env: { ...process.env, ...apiEnv }, stdio: ['ignore', log, log] });
  processes.push(server);
  for (let i = 0; i < 200; i++) {
    try { await fetch(`${origin}/api/auth/me`); return true; } catch {}
    if (server.exitCode !== null) return false;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return false;
}

const apiLog = () => { try { return fs.readFileSync(path.join(tmp, 'api.log'), 'utf8').slice(-4000); } catch { return ''; } };

async function probeApi() {
  const add = (name, ok, detail = '') => report.api_checks.push({ name, ok: Boolean(ok), detail: String(detail).slice(0, 300) });
  const cookie = { cookie: `app_session=${task.session_token}` };
  const json = { 'content-type': 'application/json' };
  const body = async response => { try { return await response.json(); } catch { return null; } };
  const request = async (name, url, init) => {
    try { return await fetch(`${origin}${url}`, init); } catch (error) { add(name, false, error.message); return null; }
  };
  let me = await request('auth_me_signed_out', '/api/auth/me');
  if (me) add('auth_me_signed_out', me.status === 200 && (await body(me))?.user === null, me.status);
  for (const e of task.api_probes?.entities ?? []) {
    let r = await request(`list:${e.base}`, e.base, { headers: cookie });
    if (r) {
      const rows = await body(r);
      add(`list:${e.base}`, r.status === 200 && Array.isArray(rows) && rows.length === e.seeded && rows.some(x => x?.title === e.seed_title),
        `${r.status} ${JSON.stringify(rows)?.slice(0, 160)}`);
    }
    r = await request(`create:${e.base}`, e.base, { method: 'POST', headers: { ...cookie, ...json }, body: JSON.stringify({ title: e.probe_title }) });
    let created = null;
    if (r) {
      created = await body(r);
      add(`create:${e.base}`, r.status < 300 && created?.title === e.probe_title && created?.id != null, `${r.status} ${JSON.stringify(created)?.slice(0, 160)}`);
    }
    if (created?.id != null) {
      r = await request(`fetch_one:${e.base}`, `${e.base}/${created.id}`, { headers: cookie });
      if (r) { const one = await body(r); add(`fetch_one:${e.base}`, r.status === 200 && one?.title === e.probe_title, r.status); }
    } else add(`fetch_one:${e.base}`, false, 'nothing was created to fetch');
    // Refused means refused: a 5xx is a crash, not access control.
    r = await request(`list_needs_session:${e.base}`, e.base);
    if (r) add(`list_needs_session:${e.base}`, [401, 403].includes(r.status), r.status);
    r = await request(`create_needs_session:${e.base}`, e.base, { method: 'POST', headers: json, body: JSON.stringify({ title: 'intruder' }) });
    if (r) add(`create_needs_session:${e.base}`, [401, 403].includes(r.status), r.status);
  }
  for (const page of task.api_probes?.guarded_pages ?? []) {
    const r = await request(`guard_blocks:${page}`, page, { redirect: 'manual' });
    if (r) add(`guard_blocks:${page}`, [401, 403].includes(r.status), r.status);
  }
}

async function startContext(browser, name) {
  const [width, height] = VIEWPORTS[name];
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, locale: 'en-US', timezoneId: 'UTC', colorScheme: 'light', reducedMotion: 'reduce', serviceWorkers: 'block' });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return url.origin === origin || ['data:', 'blob:'].includes(url.protocol) ? route.continue() : route.abort('blockedbyclient');
  });
  await context.addInitScript(() => {
    let seed = 42;
    Math.random = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    const FixedDate = Date;
    class FrozenDate extends FixedDate { constructor(...args) { super(...(args.length ? args : ['2026-11-07T12:00:00Z'])); } static now() { return 1794052800000; } }
    globalThis.Date = FrozenDate;
  });
  return context;
}

const signIn = context => context.addCookies([{ name: 'app_session', value: task.session_token, url: origin }]);

async function runTest(page, context, test, name) {
  resetDatabase();
  await context.clearCookies();
  if (!test.signed_out) await signIn(context);
  await page.goto(origin, { waitUntil: 'networkidle', timeout: 15000 });
  const result = { id: `${test.id}:${name}`, view: name, passed: true, steps: [] };
  for (const [stepIndex, instruction] of test.steps.entries()) {
    const first = instruction.test_id.endsWith(':first');
    let locator = page.getByTestId(instruction.test_id.replace(/:first$/, ''));
    if (first) locator = locator.first();
    const observeText = async () => {
      if (!['expect_text', 'expect_text_exact'].includes(instruction.action)) return {};
      const values = await locator.allTextContents();
      return { observation: { kind: 'text_content_after_assertion',
        values: values.slice(0, 20).map(value => value.slice(0, 2000)),
        truncated: values.length > 20 || values.some(value => value.length > 2000) } };
    };
    try {
      switch (instruction.action) {
        case 'click': await locator.click(); break;
        case 'click_if_enabled': if (await locator.isEnabled()) await locator.click(); break;
        case 'expect_focused': await expect(locator).toBeFocused(); break;
        case 'fill': await locator.fill(instruction.value); break;
        case 'select': await locator.selectOption(instruction.value); break;
        case 'press': await locator.press(instruction.value); break;
        case 'reload': await page.reload({ waitUntil: 'networkidle' }); break;
        case 'expect_visible': await expect(locator).toBeVisible(); break;
        case 'expect_hidden': await expect(locator).toBeHidden(); break;
        case 'expect_text': await expect(locator).toContainText(instruction.value); break;
        case 'expect_text_exact': await expect(locator).toHaveText(instruction.value); break;
        case 'expect_count': await expect(locator).toHaveCount(Number(instruction.value)); break;
        case 'expect_api_contains': {
          // The UI could fake persistence with local state; the server cannot.
          const { path: apiPath, title } = JSON.parse(instruction.value);
          const rows = await (await page.request.get(`${origin}${apiPath}`)).json();
          expect(Array.isArray(rows) && rows.some(row => row?.title === title), `server rows contain ${title}`).toBe(true);
          break;
        }
        default: throw new Error(`Unknown action ${instruction.action}`);
      }
      result.steps.push({ ...instruction, passed: true, ...await observeText() });
      if (STATE_CHANGES.includes(instruction.action)) {
        const stateRef = `${result.id}:step-${stepIndex}`;
        // A step can trigger a reload (sign-out does). Measure the page it lands on, not the one being torn down.
        for (let attempt = 1; ; attempt++) {
          try {
            await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
            const scan = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
            const horizontal_overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
            report.views[name].interaction_states ??= [];
            report.views[name].interaction_states.push({ ref: stateRef, test_id: result.id, step_index: stepIndex, accessibility: scan.violations, horizontal_overflow });
            report.references.push({ type: 'accessibility', ref: stateRef }, { type: 'overflow', ref: stateRef });
            break;
          } catch (error) {
            const navigating = /context was destroyed|navigation/i.test(error.message);
            if (navigating && attempt < 4) { await page.waitForTimeout(250); continue; }
            report.views[name].harness_error = `Intermediate measurement failed: ${error.message}`;
            break;
          }
        }
      }
    } catch (error) {
      result.passed = false;
      const observation = await observeText().catch(failure => ({ observation_error: failure.message }));
      result.steps.push({ ...instruction, passed: false, error: error.message.slice(0, 1500), ...observation });
      break;
    }
  }
  report.tests.push(result);
  report.references.push({ type: 'test', ref: result.id });
  const stateName = `${name}-after`;
  await page.screenshot({ path: `${out}/${stateName}.png`, animations: 'disabled' });
  report.screenshots[stateName] = `${stateName}.png`;
  report.references.push({ type: 'screenshot', ref: stateName });
  const afterAxe = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  report.views[name].after_accessibility = afterAxe.violations;
  report.views[name].after_overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
}

async function auditViews(browser) {
  for (const name of views) {
    const context = await startContext(browser, name);
    const page = await context.newPage();
    page.setDefaultTimeout(4000);
    page.on('pageerror', error => report.runtime_errors.push({ view: name, message: error.message }));
    page.on('console', msg => { if (msg.type() === 'error') report.console_errors.push({ view: name, message: msg.text().slice(0, 1000) }); });
    // A fetch cancelled by a reload or unmount is normal once a page talks to a real server; it is not a failure.
    page.on('requestfailed', request => {
      const error = request.failure()?.errorText;
      if (error !== 'net::ERR_ABORTED') report.failed_requests.push({ view: name, url: request.url(), error });
    });
    page.on('response', response => { if (response.status() >= 400) report.failed_requests.push({ view: name, url: response.url(), status: response.status() }); });
    try {
      resetDatabase();
      if (task.mode !== 'verify') await signIn(context);
      await page.goto(origin, { waitUntil: 'networkidle', timeout: 15000 });
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
      const accessibility = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
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
      if (testViews.includes(name)) for (const test of task.tests) await runTest(page, context, test, name);
    } catch (error) {
      report.views[name] = { ...report.views[name], harness_error: error.message };
    } finally {
      await context.close();
      save();
    }
  }
}

let browser;
try {
  const pg = startPostgres();
  report.stack.postgres = { ok: pg.ok, log: pg.log.slice(-1500) };
  if (!pg.ok) throw new Error('Postgres did not start');
  if (!selfSetup) {
    const migrate = run(python, ['-m', 'src.database.migrate'], { env: apiEnv });
    report.stack.migrate = { ok: migrate.ok, log: migrate.log.slice(-3000) };
    if (migrate.ok) {
      const again = run(python, ['-m', 'src.database.migrate'], { env: apiEnv });
      report.stack.migrate_is_repeatable = again.ok && !again.log.includes('applied');
    }
    if (!migrate.ok) { report.stack.failed = 'migrate'; save(); process.exitCode = 0; throw new Error('STOP'); }
    const seeded = resetDatabase();
    report.stack.seed = { ok: seeded.ok, log: (seeded.log ?? '').slice(-1500) };
    if (!seeded.ok) { report.stack.failed = 'seed'; save(); throw new Error('STOP'); }
  }
  report.stack.api_started = await startApi();
  if (!report.stack.api_started) { report.stack.failed = 'api_start'; save(); throw new Error('STOP'); }
  if (selfSetup) {
    // Tables the app made on its own, on a database it created on its own. Only now may the harness touch them.
    const seeded = resetDatabase();
    report.stack.self_setup = { ok: seeded.ok, log: (seeded.log ?? '').slice(-1500) };
    if (!seeded.ok) { report.stack.failed = 'self_setup'; save(); throw new Error('STOP'); }
  }
  await probeApi();
  resetDatabase();
  save();
  if (task.mode === 'preflight') throw new Error('STOP');

  const build = run('npm', ['run', 'build'], { cwd: path.join(project, 'frontend') });
  report.build = { passed: build.ok, exit_code: build.exit_code, log: build.log.slice(-16000), error: build.error };
  report.references.push({ type: 'build', ref: 'build' });
  save();
  if (!report.build.passed) throw new Error('STOP');

  browser = await chromium.launch({ headless: true });
  await auditViews(browser);
} catch (error) {
  if (error.message !== 'STOP') report.harness_error = error.message;
} finally {
  if (browser) await browser.close();
  report.stack.api_log = apiLog();
  for (const child of processes) child.kill('SIGTERM');
  run(bin('pg_ctl'), ['-D', data, '-m', 'fast', 'stop'], { asPostgres: true });
  save();
  fs.rmSync(tmp, { recursive: true, force: true });
}
