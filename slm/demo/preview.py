"""Open a generated project in a real browser and take a screenshot.

    uv run --with fastapi --with uvicorn --with asyncpg python -m slm.demo.preview \
        <project_dir> <out.png> --node-modules out/demo/node_modules

Starts its own temporary Postgres, the project's API and a Vite dev server, adds sample rows, then
shoots the page with headless Chrome. It adds build files beside the project, in a temporary copy.

Preview only: Vite adds a demo session cookie, because generated projects have no sign-in page.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
INDEX = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head>
<body><div id="root"></div><script type="module" src="/preview_main.tsx"></script></body></html>
"""
MAIN = """import { createRoot } from "react-dom/client";
import { Shell } from "./src/frontend/Shell";
const forms = import.meta.glob("./src/frontend/*Form.tsx", { eager: true }) as Record<string, any>;
createRoot(document.getElementById("root")!).render(
  <>
    <Shell />
    {Object.entries(forms).map(([path, mod]) => {
      const Form = Object.values(mod)[0] as any;
      return <Form key={path} />;
    })}
  </>,
);
"""
VITE = """import react from "@vitejs/plugin-react";
export default {
  plugins: [react()],
  server: { host: "127.0.0.1", port: %d, strictPort: true, proxy: { "/api": { target: "http://127.0.0.1:%d", headers: { Cookie: "app_session=demo" } } } },
};
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(url: str, seconds: float = 40) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except urllib.error.HTTPError:
            return True
        except OSError:
            time.sleep(0.3)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("out")
    ap.add_argument("--node-modules", required=True)
    args = ap.parse_args()

    source, out = Path(args.project).resolve(), Path(args.out).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="prev"))
    app_dir = tmp / "app"
    shutil.copytree(source, app_dir)
    db_port, api_port, web_port = free_port(), free_port(), free_port()
    (app_dir / "node_modules").symlink_to(Path(args.node_modules).resolve())
    title = (app_dir / "README.md").read_text().splitlines()[0].lstrip("# ")
    (app_dir / "index.html").write_text(INDEX.format(title=title))
    (app_dir / "preview_main.tsx").write_text(MAIN)
    (app_dir / "vite.config.mjs").write_text(VITE % (web_port, api_port))

    procs = []
    data = tmp / "pg"
    psql = ["psql", "-h", "localhost", "-p", str(db_port), "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-q"]
    try:
        subprocess.run(["initdb", "-D", data, "-A", "trust", "-U", "postgres"], check=True, capture_output=True)
        subprocess.run(["pg_ctl", "-D", data, "-o", f"-p {db_port} -c listen_addresses=localhost -c unix_socket_directories=''",
                        "-l", tmp / "pg.log", "-w", "start"], check=True, capture_output=True)
        schemas = sorted((app_dir / "src/database").glob("*.sql"), key=lambda p: p.name != "users.sql")
        tables = [p.stem for p in schemas if p.stem != "users"]
        for sql in schemas:
            subprocess.run([*psql, "-f", sql], check=True, capture_output=True)
        subprocess.run([*psql, "-c", "INSERT INTO users (email, password_hash, session_token) VALUES ('demo@example.com','x','demo')"],
                       check=True, capture_output=True)
        for t in tables:
            subprocess.run([*psql, "-c", f"INSERT INTO {t} (owner_id, title) VALUES (1,'First {t}'),(1,'Second {t}'),(1,'Third {t}')"],
                           check=True, capture_output=True)
        env = {"DATABASE_URL": f"postgresql://postgres@localhost:{db_port}/postgres"}
        import os
        procs.append(subprocess.Popen(["python", "-m", "uvicorn", "src.app:app", "--port", str(api_port), "--log-level", "warning"],
                                      cwd=app_dir, env={**os.environ, **env}, stdout=(tmp / "api.log").open("w"), stderr=subprocess.STDOUT))
        procs.append(subprocess.Popen([str(app_dir / "node_modules/.bin/vite")], cwd=app_dir,
                                      stdout=(tmp / "web.log").open("w"), stderr=subprocess.STDOUT))
        ok_api = wait(f"http://127.0.0.1:{api_port}/docs")
        ok_web = wait(f"http://127.0.0.1:{web_port}/")
        statuses = {}
        for t in tables:
            base = next((p.read_text().split('@router.get("')[1].split('"')[0]
                         for p in (app_dir / "src/network").glob(f"{t}_api.py")), None)
            if base:
                req = urllib.request.Request(f"http://127.0.0.1:{web_port}{base}")
                try:
                    statuses[base] = len(json.loads(urllib.request.urlopen(req, timeout=8).read()))
                except Exception as e:  # noqa: BLE001
                    statuses[base] = repr(e)[:80]
        out.parent.mkdir(parents=True, exist_ok=True)
        # Vite's live-reload socket never goes idle, so wait a fixed time rather than for the page to settle.
        chrome = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={tmp / 'chrome'}",
                                   "--window-size=1280,1000", "--timeout=12000", f"--screenshot={out}",
                                   f"http://127.0.0.1:{web_port}/"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(chrome)
        end = time.time() + 45
        while time.time() < end and not (out.exists() and chrome.poll() is not None):
            time.sleep(0.5)
        print(json.dumps({"project": source.name, "api_started": ok_api, "web_started": ok_web, "rows_via_proxy": statuses,
                          "screenshot": out.exists(), "api_log": (tmp / "api.log").read_text()[-300:],
                          "web_errors": [l[:160] for l in (tmp / "web.log").read_text().splitlines() if "rror" in l][:4]}, indent=1))
    finally:
        for p in procs:
            p.terminate()
        subprocess.run(["pg_ctl", "-D", data, "-m", "fast", "stop"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
