// Runs compiled frontend checks for slm/bench/test_quality.py: one JSON request per stdin line.
// NODE_PATH must hold react, react-dom, jsdom and esbuild.
const esbuild = require("esbuild");
const { JSDOM } = require("jsdom");
const readline = require("readline");

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = require("react");
const { createRoot } = require("react-dom/client");
const { act } = React;
const realFetch = globalThis.fetch;
const ROWS = [{ id: 1, title: "row one" }, { id: 2, title: "row two" }];

function load(root, file) {
  const built = esbuild.buildSync({
    entryPoints: [`${root}/${file}`], bundle: true, write: false, format: "cjs", platform: "node",
    jsx: "automatic", external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent",
  });
  const mod = { exports: {} };
  new Function("require", "module", "exports", built.outputFiles[0].text)(require, mod, mod.exports);
  return mod.exports;
}

function stubFetch(calls) {
  globalThis.fetch = async (url, opts = {}) => {
    calls.push({ url, method: (opts.method || "GET").toUpperCase(), body: opts.body });
    return { ok: true, status: 200, json: async () => (opts.method ? { id: 3, title: "new" } : ROWS) };
  };
}

function liveFetch(base) {
  globalThis.fetch = (url, opts = {}) => realFetch(base + url, {
    ...opts, headers: { ...(opts.headers || {}), Cookie: "app_session=good" },
  });
}

const tick = (ms = 25) => new Promise((resolve) => setTimeout(resolve, ms));

async function mount(Component) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(Component));
    await tick();
  });
  return { host, stop: () => act(async () => root.unmount()).then(() => host.remove()) };
}

async function submit(host) {
  await act(async () => {
    host.querySelector("form").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
    await tick(120);
  });
}

const ops = {
  async client_calls({ root, file, name, path }) {
    const calls = [];
    stubFetch(calls);
    const client = load(root, file);
    await client[`list${name}`]();
    await client[`create${name}`]({ title: "t" });
    const [a, b] = calls;
    return calls.length === 2 && a.method === "GET" && a.url === path && b.method === "POST" && b.url === path
      && JSON.parse(b.body || "{}").title === "t";
  },
  async route_export({ root, file, route }) {
    stubFetch([]);
    return load(root, file).route === route;
  },
  async page_renders({ root, file, comp, path }) {
    const calls = [];
    stubFetch(calls);
    const { host, stop } = await mount(load(root, file)[comp]);
    const items = [...host.querySelectorAll("li")].map((li) => li.textContent);
    await stop();
    return items.length === 2 && items.includes("row one") && items.includes("row two")
      && (!path || calls.some((c) => c.method === "GET" && c.url === path));
  },
  async form_submits({ root, file, comp }) {
    const calls = [];
    stubFetch(calls);
    const { host, stop } = await mount(load(root, file)[comp]);
    await submit(host);
    await stop();
    return calls.filter((c) => c.method === "POST").length === 1;
  },
  async shell_renders({ root, routes, headings }) {
    stubFetch([]);
    const { host, stop } = await mount(load(root, "src/frontend/Shell.tsx").Shell);
    const links = [...host.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    const titles = [...host.querySelectorAll("h1")].map((h) => h.textContent);
    await stop();
    return routes.every((r) => links.includes(r)) && headings.every((h) => titles.includes(h));
  },
  async client_create_list({ root, file, name, path, base }) {
    liveFetch(base);
    const client = load(root, file);
    await client[`create${name}`]({ title: "fresh row" });
    const res = await fetch(path);
    const rows = await res.json();
    return res.status === 200 && Array.isArray(rows) && rows.some((r) => r.title === "fresh row");
  },
  async form_to_page({ root, formFile, formComp, pageFile, pageComp, route, base }) {
    liveFetch(base);
    if (load(root, pageFile).route !== route) return false;
    const form = await mount(load(root, formFile)[formComp]);
    await submit(form.host);
    await form.stop();
    const page = await mount(load(root, pageFile)[pageComp]);
    await act(async () => { await tick(120); });
    const items = page.host.querySelectorAll("li").length;
    await page.stop();
    return items >= 1;
  },
};

const lines = readline.createInterface({ input: process.stdin });
lines.on("line", async (line) => {
  const req = JSON.parse(line);
  let pass = false;
  let error = null;
  try {
    pass = await Promise.race([ops[req.op](req), new Promise((_, no) => setTimeout(() => no(new Error("timeout")), 6000))]);
  } catch (e) {
    error = String(e).slice(0, 200);
  }
  process.stdout.write(JSON.stringify({ pass: !!pass, error }) + "\n");
});
console.error = () => {};
// Components fire requests without awaiting them, so a broken version can reject after its check ends.
process.on("unhandledRejection", () => {});
// A form fires its request without awaiting it, so a failed request must not kill this process.
const logFile = process.env.HARNESS_LOG;
function note(kind, e) {
  if (logFile) require("fs").appendFileSync(logFile, `${kind}: ${e && e.stack ? e.stack : e}\n`);
}
process.on("unhandledRejection", (e) => note("unhandledRejection", e));
process.on("uncaughtException", (e) => note("uncaughtException", e));
process.on("exit", (code) => note("exit", code));
