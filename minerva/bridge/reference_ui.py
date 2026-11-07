"""A plain, correct App.tsx written from the contract.

It validates the audit (it must pass, and each broken copy of it must fail), and it is the labelled fallback when the
Architect produces nothing acceptable. It is not meant to be good-looking.
"""

from __future__ import annotations

from minerva.bridge.contract import AppContract


def render_reference_ui(contract: AppContract) -> str:
    imports = ", ".join(sorted(["ApiError", "signOut", *(f"list{e.pascal}" for e in contract.entities),
                                *(f"create{e.pascal}" for e in contract.entities)]))
    panels = ",\n".join(
        f'  {{ key: "{e.tid}", label: "{e.label}", list: list{e.pascal}, create: create{e.pascal} }}'
        for e in contract.entities)
    title = contract.name.replace("\\", "\\\\").replace('"', '\\"')
    return f'''import {{ useEffect, useState, type FormEvent }} from "react";
import {{ {imports} }} from "./api";

type Item = {{ id: number; title: string; created_at: string }};
type Panel = {{ key: string; label: string; list: () => Promise<Item[]>; create: (title: string) => Promise<Item> }};

const PANELS: Panel[] = [
{panels},
];

function describe(failure: unknown): string {{
  return failure instanceof ApiError ? failure.message : "Something went wrong. Please try again.";
}}

function PanelView({{ panel }}: {{ panel: Panel }}) {{
  const [rows, setRows] = useState<Item[] | null>(null);
  const [title, setTitle] = useState("");
  const [formError, setFormError] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {{
    let live = true;
    setRows(null);
    setLoadError("");
    panel.list().then(
      (found) => {{ if (live) setRows(found); }},
      (failure) => {{ if (live) setLoadError(describe(failure)); }},
    );
    return () => {{ live = false; }};
  }}, [panel]);

  async function submit(event: FormEvent) {{
    event.preventDefault();
    if (!title.trim()) {{
      setFormError("Enter a title.");
      return;
    }}
    setFormError("");
    try {{
      const created = await panel.create(title.trim());
      setRows((current) => [created, ...(current ?? [])]);
      setTitle("");
    }} catch (failure) {{
      setFormError(describe(failure));
    }}
  }}

  const id = `${{panel.key}}-title`;
  return (
    <section aria-label={{panel.label}} className="space-y-6">
      <h2 className="text-xl font-semibold">{{panel.label}}</h2>
      <form onSubmit={{submit}} noValidate className="space-y-2">
        <label htmlFor={{id}} className="block text-sm font-medium">New title</label>
        <div className="flex flex-wrap gap-2">
          <input id={{id}} data-testid={{`${{panel.key}}-title-input`}} value={{title}} onChange={{(e) => setTitle(e.target.value)}}
            className="min-w-0 flex-1 rounded border border-slate-500 px-3 py-2" />
          <button data-testid={{`${{panel.key}}-submit`}} type="submit" className="rounded bg-blue-700 px-4 py-2 font-medium text-white">Add</button>
        </div>
        {{formError && <p role="alert" data-testid={{`${{panel.key}}-form-error`}} className="text-sm text-red-800">{{formError}}</p>}}
      </form>
      {{loadError && <p role="alert" className="text-sm text-red-800">{{loadError}}</p>}}
      {{rows === null && !loadError && <p>Loading…</p>}}
      {{rows !== null && (
        <div data-testid={{`${{panel.key}}-list`}}>
          {{rows.length === 0 && <p>Nothing here yet.</p>}}
          <ul className="divide-y divide-slate-300">
            {{rows.map((row) => <li key={{row.id}} data-testid={{`${{panel.key}}-row`}} className="py-2 break-words">{{row.title}}</li>)}}
          </ul>
        </div>
      )}}
    </section>
  );
}}

export default function App() {{
  const [active, setActive] = useState(PANELS[0]);
  return (
    <div className="min-h-screen bg-white text-slate-900">
      <header className="border-b border-slate-300">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-3 p-4">
          <h1 className="mr-auto text-lg font-semibold">{{"{title}"}}</h1>
          <nav aria-label="Sections" className="flex flex-wrap gap-2">
            {{PANELS.map((panel) => (
              <button key={{panel.key}} type="button" data-testid={{`nav-${{panel.key}}`}} onClick={{() => setActive(panel)}}
                aria-current={{panel === active ? "page" : undefined}}
                className={{panel === active ? "rounded bg-slate-900 px-3 py-2 text-white" : "rounded px-3 py-2 text-slate-900 underline"}}>
                {{panel.label}}
              </button>
            ))}}
          </nav>
          <button type="button" data-testid="sign-out" onClick={{() => void signOut()}} className="rounded border border-slate-500 px-3 py-2">Sign out</button>
        </div>
      </header>
      <main className="mx-auto max-w-3xl p-4">
        <PanelView panel={{active}} />
      </main>
    </div>
  );
}}
'''
