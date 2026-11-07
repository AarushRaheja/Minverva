// Runs inside the sandbox: parse every TS/TSX file, bundle the shell (so imports must resolve), then render it.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(process.env.GRADER_NODE + "/");
const esbuild = require("esbuild");
const report = (group, name, ok, detail = "") => console.log(JSON.stringify({ group, name, ok, detail: String(detail).slice(0, 300) }));
const [tree, specPath] = process.argv.slice(2);
const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));

const walk = (d) => (fs.existsSync(d) ? fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)])) : []);
for (const f of walk(path.join(tree, "src")).filter((x) => /\.(ts|tsx)$/.test(x))) {
  const rel = path.relative(tree, f);
  try {
    await esbuild.transform(fs.readFileSync(f, "utf8"), { loader: f.endsWith("x") ? "tsx" : "ts", jsx: "automatic" });
    report("parse", `typescript:${rel}`, true);
  } catch (e) {
    report("parse", `typescript:${rel}`, false, e.errors?.[0]?.text ?? e.message);
  }
}

const shell = path.join(tree, "src/frontend/Shell.tsx");
if (!fs.existsSync(shell)) {
  report("frontend", "shell_bundles", false, "no src/frontend/Shell.tsx");
  report("frontend", "shell_renders", false, "no shell");
  for (const p of spec.pages) report("frontend", `links:${p}`, false, "no shell");
  process.exit(0);
}
const outfile = path.join(process.env.TMPDIR, "shell.cjs");
try {
  await esbuild.build({ entryPoints: [shell], bundle: true, platform: "node", format: "cjs", jsx: "automatic", outfile, nodePaths: [process.env.GRADER_NODE], external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent" });
  report("frontend", "shell_bundles", true);
} catch (e) {
  const first = e.errors?.[0];
  report("frontend", "shell_bundles", false, first ? `${first.text}${first.location ? ` at ${path.relative(tree, path.resolve(first.location.file))}` : ""}` : e.message);
  report("frontend", "shell_renders", false, "did not bundle");
  for (const p of spec.pages) report("frontend", `links:${p}`, false, "did not bundle");
  process.exit(0);
}
globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => [] });
let html = "";
try {
  const React = require("react");
  const { renderToString } = require("react-dom/server");
  const { Shell } = require(outfile);
  html = renderToString(React.createElement(Shell));
  report("frontend", "shell_renders", true);
} catch (e) {
  report("frontend", "shell_renders", false, e.message);
}
for (const p of spec.pages) report("frontend", `links:${p}`, html.includes(`href="${p}"`), html ? "" : "did not render");
process.exit(0);
