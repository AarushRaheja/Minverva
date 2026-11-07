"""`slm code [PATH]`: the workbench in a terminal, laid out like VS Code.

Activity bar, explorer, tabbed editor, a Problems / Plan / Output panel, a command palette and a status bar.
Runs go through the same start_run() as the web UI, into <PATH>/<project>-<run id>/. Saving a file from a
run re-runs the integrator on what's on disk, so Problems stays current as you fix things.

    ctrl+p or F1   command palette and file search     ctrl+s   save
    ctrl+n         new run                             ctrl+w   close tab
    ctrl+b         toggle explorer                     ctrl+j or F4   toggle panel
    ctrl+pgup/pgdn switch tab                          ctrl+q   quit
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, DataTable, DirectoryTree, Input, Label, RichLog, Select, Static, TabbedContent, TabPane,
    Tabs, TextArea,
)

from slm.ui import server as S
from slm.ui import workspace as W

WELCOME = """[b]slm code[/b]

[#9cdcfe]ctrl+n[/]        new run: brief → manager → specialists → integrator
[#9cdcfe]ctrl+p[/] or [#9cdcfe]F1[/]  command palette and file search
[#9cdcfe]ctrl+s[/]        save (files from a run are re-checked)
[#9cdcfe]ctrl+w[/]        close tab
[#9cdcfe]ctrl+b[/]        toggle explorer
[#9cdcfe]ctrl+j[/] or [#9cdcfe]F4[/]  toggle panel
[#9cdcfe]ctrl+q[/]        quit
"""
STATUS_MARK = {"ok": "[#89d185]✓[/]", "failed": "[#f14c4c]✗[/]", "pending": "[#858585]·[/]"}


class Explorer(DirectoryTree):
    def filter_paths(self, paths):
        return [p for p in paths if p.name not in W.IGNORED_DIRS]


class Editor(TextArea):
    def __init__(self, path: Path, text: str, language: str | None, **kw):
        super().__init__(text, read_only=False, show_line_numbers=True, tab_behavior="indent", soft_wrap=False,
                         theme="vscode_dark", **kw)
        if language in self.available_languages:
            self.language = language
        self.path = path
        self.saved_text = text
        self.mtime = path.stat().st_mtime_ns

    @property
    def dirty(self) -> bool:
        return self.text != self.saved_text


class ActivityIcon(Static):
    def __init__(self, icon: str, action: str, tip: str):
        super().__init__(icon, classes="icon")
        self.tooltip = tip
        self.icon_action = action

    async def on_click(self) -> None:
        await self.app.run_action(self.icon_action)


class NewRun(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def compose(self) -> ComposeResult:
        meta = S.meta()
        self.templates = {t["id"]: t for t in meta["templates"]}
        backends = [(b["label"], b["id"]) for b in meta["backends"] if b["available"]]
        off = [f"{b['label']}: {b['why']}" for b in meta["backends"] if not b["available"]]
        first = meta["templates"][0]
        with VerticalScroll(id="new-run"):
            yield Label("[b]New run[/b]")
            yield Label("Template")
            yield Select([(f"{t['name']} ({t['split']})", t["id"]) for t in meta["templates"]], value=first["id"],
                         allow_blank=False, compact=True, id="template")
            yield Label("Backend")
            yield Select(backends, value=backends[0][1], allow_blank=False, compact=True, id="backend")
            for line in off:
                yield Label(line, classes="dim")
            yield Label("Name")
            yield Input(first["name"], compact=True, id="name")
            yield Label("Entities (comma-separated, 1 to 4)")
            yield Input(", ".join(first["entities"]), compact=True, id="entities")
            yield Label("Form entity")
            yield Input(first["form"], compact=True, id="form")
            yield Checkbox("OAuth", first["oauth"], compact=True, id="oauth")
            yield Label("Brief (the demo backend plans from the fields above instead)")
            yield Input(first["brief"], compact=True, id="brief")
            yield Label("", id="new-run-error", classes="error")
            with Horizontal(id="new-run-buttons"):
                yield Button("Run", variant="primary", id="go")
                yield Button("Cancel", id="cancel")

    @on(Select.Changed, "#template")
    def _template(self, event: Select.Changed) -> None:
        t = self.templates[event.value]
        self.query_one("#name", Input).value = t["name"]
        self.query_one("#entities", Input).value = ", ".join(t["entities"])
        self.query_one("#form", Input).value = t["form"]
        self.query_one("#oauth", Checkbox).value = t["oauth"]
        self.query_one("#brief", Input).value = t["brief"]

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#go")
    def _go(self) -> None:
        backend = self.query_one("#backend", Select).value
        value = lambda i: self.query_one(f"#{i}", Input).value  # noqa: E731
        req = {"backend": backend, "planner": "manager",
               "brief": "" if backend == "demo" else value("brief"),
               "spec": {"name": value("name"), "entities": [e for e in value("entities").replace(" ", "").split(",") if e],
                        "form": value("form"), "oauth": self.query_one("#oauth", Checkbox).value}}
        error = self.app.begin_run(req)
        if error:
            self.query_one("#new-run-error", Label).update(error)
        else:
            self.dismiss(None)


class Commands(Provider):
    """The command palette: actions first, then every file in the workspace."""

    ACTIONS = (("New run", "new_run"), ("Save file", "save"), ("Close tab", "close_tab"),
               ("Toggle explorer", "toggle_sidebar"), ("Toggle panel", "toggle_panel"), ("Quit", "quit"))

    def _entries(self):
        app = self.app
        for label, action in self.ACTIONS:
            yield f"> {label}", (lambda a=action: app.run_action_soon(a))
        for path in app.workspace_files():
            yield str(path.relative_to(app.root)), (lambda p=path: app.call_later(app.open_path, p))

    async def discover(self) -> Hits:
        for text, run in self._entries():
            yield DiscoveryHit(text, run)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for text, run in self._entries():
            score = matcher.match(text)
            if score > 0:
                yield Hit(score, matcher.highlight(text), run, text=text)


class SlmCode(App):
    TITLE = "slm code"
    COMMANDS = App.COMMANDS | {Commands}
    CSS = """
    Screen { background: #1e1e1e; color: #cccccc; layout: vertical; }
    #main { height: 1fr; }
    #activity { width: 5; background: #333333; }
    .icon { width: 100%; height: 3; content-align: center middle; color: #858585; }
    .icon:hover { color: #ffffff; }
    #sidebar { width: 32; background: #252526; border-right: solid #3c3c3c; }
    #sidebar-title { height: 1; padding: 0 1; color: #bbbbbb; text-style: bold; }
    Explorer { background: #252526; height: 1fr; }
    #workbench { width: 1fr; }
    #editors { height: 1fr; }
    #panel { height: 12; border-top: solid #3c3c3c; background: #1e1e1e; }
    TabbedContent ContentSwitcher { height: 1fr; }
    TabPane { padding: 0; height: 1fr; }
    Tabs { background: #252526; }
    Tab { color: #969696; }
    Tab.-active { color: #ffffff; background: #1e1e1e; }
    Editor { height: 1fr; border: none; padding: 0; background: #1e1e1e; }
    Editor:focus { border: none; }
    #welcome { padding: 2 4; }
    DataTable, RichLog { height: 1fr; background: #1e1e1e; }
    #status { height: 1; background: #007acc; color: #ffffff; padding: 0 1; }
    #status.failed { background: #c72e0f; }
    NewRun { align: center middle; background: #000000 50%; }
    #new-run { width: 76; max-height: 90%; height: auto; padding: 1 2; background: #252526; border: solid #007acc; }
    #new-run Input, #new-run Select, #new-run Checkbox { margin-bottom: 1; }
    #new-run-buttons { height: auto; margin-top: 1; }
    #new-run-buttons Button { margin-right: 2; }
    .error { color: #f14c4c; }
    .dim { color: #858585; }
    """
    BINDINGS = [
        Binding("ctrl+n", "new_run", "New run", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("ctrl+w", "close_tab", "Close tab", priority=True),
        Binding("ctrl+b", "toggle_sidebar", "Explorer", priority=True),
        Binding("ctrl+j,f4", "toggle_panel", "Panel", priority=True),
        Binding("ctrl+p,f1", "command_palette", show=False, priority=True),
        Binding("ctrl+pagedown", "tab(1)", show=False, priority=True),
        Binding("ctrl+pageup", "tab(-1)", show=False, priority=True),
    ]

    def __init__(self, root: str | Path = ".", autorun: dict | None = None):
        super().__init__()
        self.root = Path(root).resolve()
        self.autorun = autorun
        self.editors: dict[Path, tuple[str, Editor]] = {}
        self._next_pane = 0
        self._close_armed: str | None = None
        self._quit_armed = False
        self._overwrite_armed: Path | None = None
        self.runs: dict[str, S.Run] = {}
        self.current_run: S.Run | None = None
        self.run_dir: Path | None = None
        self._written: set[str] = set()
        self._rejected: list[str] = []
        self._seen_events = 0
        self._finished = False
        self.checks: list[CheckRow] = []

    # --- layout -----------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="activity"):
                yield ActivityIcon("▤", "toggle_sidebar", "Explorer (ctrl+b)")
                yield ActivityIcon("▶", "new_run", "New run (ctrl+n)")
                yield ActivityIcon("⌘", "command_palette", "Command palette (ctrl+p)")
            with Vertical(id="sidebar"):
                yield Static("EXPLORER", id="sidebar-title")
                yield Explorer(self.root, id="tree")
            with Vertical(id="workbench"):
                with TabbedContent(id="editors"):
                    with TabPane("Welcome", id="welcome-pane"):
                        yield Static(WELCOME, id="welcome")
                with TabbedContent(id="panel"):
                    with TabPane("Problems", id="problems-pane"):
                        yield DataTable(id="problems", cursor_type="row")
                    with TabPane("Plan", id="plan-pane"):
                        yield DataTable(id="plan", cursor_type="row")
                    with TabPane("Output", id="output-pane"):
                        yield RichLog(id="output", markup=False, wrap=True)
        yield Static("", id="status")

    def on_mount(self) -> None:
        self.query_one("#problems", DataTable).add_columns("", "check", "detail")
        self.query_one("#plan", DataTable).add_columns("", "level", "task", "domain", "kind", "target")
        self.set_interval(0.25, self.poll_run)
        self.update_status()
        self.query_one("#tree", Explorer).focus()
        if self.autorun:
            error = self.begin_run(self.autorun)
            if error:
                self.notify(error, severity="error")

    def workspace_files(self, limit: int = 5000) -> list[Path]:
        out: list[Path] = []
        for folder, dirs, files in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d not in W.IGNORED_DIRS)
            out += [Path(folder) / f for f in sorted(files)]
            if len(out) >= limit:
                break
        return out[:limit]

    def run_action_soon(self, action: str) -> None:
        self.call_later(self.run_action, action)

    # --- editors ----------------------------------------------------------------

    @on(DirectoryTree.FileSelected)
    async def _file_selected(self, event: DirectoryTree.FileSelected) -> None:
        await self.open_path(event.path)

    async def open_path(self, path: Path) -> None:
        path = Path(path).resolve()
        tabs = self.query_one("#editors", TabbedContent)
        if path in self.editors:
            pane_id, editor = self.editors[path]
            tabs.active = pane_id
            editor.focus()
            return
        try:
            if path.stat().st_size > W.MAX_OPEN_BYTES:
                self.notify(f"{path.name} is too large to open", severity="warning")
                return
            text = path.read_text()
        except (OSError, UnicodeDecodeError) as e:
            self.notify(f"Can't open {path.name}: {type(e).__name__}", severity="error")
            return
        self._next_pane += 1
        pane_id = f"file-{self._next_pane}"
        editor = Editor(path, text, W.language_for(path))
        self.editors[path] = (pane_id, editor)
        await tabs.add_pane(TabPane(path.name, editor, id=pane_id))
        tabs.active = pane_id
        editor.focus()
        self.update_status()

    def current_editor(self) -> Editor | None:
        active = self.query_one("#editors", TabbedContent).active
        return next((e for pane, e in self.editors.values() if pane == active), None)

    def _label(self, editor: Editor) -> None:
        pane_id, _ = self.editors[editor.path]
        self.query_one("#editors", TabbedContent).get_tab(pane_id).label = (
            f"● {editor.path.name}" if editor.dirty else editor.path.name)

    @on(TextArea.Changed)
    def _edited(self, event: TextArea.Changed) -> None:
        if isinstance(event.text_area, Editor):
            self._close_armed = None
            self._quit_armed = False
            self._overwrite_armed = None
            self._label(event.text_area)
            self.update_status()

    @on(TextArea.SelectionChanged)
    def _moved(self) -> None:
        self.update_status()

    @on(TabbedContent.TabActivated, "#editors")
    def _tab_changed(self) -> None:
        self.update_status()

    def action_save(self) -> None:
        editor = self.current_editor()
        if editor is None:
            return
        changed_outside = editor.path.exists() and editor.path.stat().st_mtime_ns != editor.mtime
        if changed_outside and self._overwrite_armed != editor.path:
            self._overwrite_armed = editor.path
            self.notify(f"{editor.path.name} changed on disk. Press ctrl+s again to overwrite it.", severity="warning")
            return
        self._overwrite_armed = None
        try:
            editor.path.write_text(editor.text)
        except OSError as e:
            self.notify(f"Save failed: {e}", severity="error")
            return
        editor.saved_text = editor.text
        editor.mtime = editor.path.stat().st_mtime_ns
        self._label(editor)
        self.notify(f"Saved {editor.path.name}", timeout=2)
        if self.run_dir and editor.path.is_relative_to(self.run_dir.resolve()) and self.current_run and self.current_run.status != "running":
            self.recheck_run()
        self.update_status()

    async def action_close_tab(self) -> None:
        editor = self.current_editor()
        if editor is None:
            return
        pane_id, _ = self.editors[editor.path]
        if editor.dirty and self._close_armed != pane_id:
            self._close_armed = pane_id
            self.notify(f"{editor.path.name} has unsaved changes. Press ctrl+w again to discard them.", severity="warning")
            return
        self._close_armed = None
        del self.editors[editor.path]
        await self.query_one("#editors", TabbedContent).remove_pane(pane_id)
        self.update_status()

    async def action_quit(self) -> None:
        dirty = [e.path.name for _, e in self.editors.values() if e.dirty]
        if dirty and not self._quit_armed:
            self._quit_armed = True
            self.notify(f"Unsaved: {', '.join(dirty)}. Press ctrl+q again to quit without saving.", severity="warning")
            return
        self.exit()

    def action_toggle_sidebar(self) -> None:
        bar = self.query_one("#sidebar")
        bar.display = not bar.display

    def action_toggle_panel(self) -> None:
        panel = self.query_one("#panel")
        panel.display = not panel.display

    def action_tab(self, step: int) -> None:
        tabs = self.query_one("#editors", TabbedContent).query_one(Tabs)
        (tabs.action_next_tab if step > 0 else tabs.action_previous_tab)()

    # --- runs -------------------------------------------------------------------

    def action_new_run(self) -> None:
        if not isinstance(self.screen, NewRun):
            self.push_screen(NewRun())

    def begin_run(self, req: dict) -> str | None:
        """Start a run. Returns an error message for the caller to show, or None."""
        if self.current_run and self.current_run.status == "running":
            return "A run is still in progress."
        try:
            run = S.start_run(req, self.runs)
        except ValueError as e:
            return str(e)
        name = (req.get("spec") or {}).get("name") or "run"
        self.current_run, self.run_dir = run, self.root / f"{W.slug(name)}-{run.id}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._written, self._rejected, self._seen_events, self._finished = set(), [], 0, False
        self.checks = []
        self.query_one("#output", RichLog).clear()
        self.query_one("#output", RichLog).write(f"run {run.id} on {req.get('backend', 'demo')} -> {self.run_dir}")
        self.query_one("#problems", DataTable).clear()
        self.query_one("#panel", TabbedContent).active = "plan-pane"
        self.update_status()
        return None

    async def poll_run(self) -> None:
        if self.current_run is None or self._finished:
            return
        snap = self.current_run.snapshot(self._seen_events)
        finished = snap["status"] != "running"
        self._seen_events = snap["n_events"]
        log = self.query_one("#output", RichLog)
        for e in snap["events"]:
            log.write(event_line(e))
        files = [f for art in snap["artifacts"].values() for f in art.get("files", [])]
        files += (snap["deliverable"] or {}).get("files", [])
        new, rejected = W.write_new_files(self.run_dir, files, self._written)
        self._rejected += rejected
        for rel in rejected:
            log.write(f"REFUSED to write outside the run folder: {rel}")
        self.update_plan(snap)
        if new:
            await self.query_one("#tree", Explorer).reload()
        if finished:
            self._finished = True
            if snap["error"]:
                log.write(f"error: {snap['error']}")
            self.checks = [CheckRow(c["name"], c["ok"], c.get("detail", "")) for c in (snap["deliverable"] or {}).get("checks", [])]
            self.update_problems(snap["error"])
            self.query_one("#panel", TabbedContent).active = "problems-pane"
            await self.expand_run_folder()
            entry = (snap["deliverable"] or {}).get("entry")
            target = W.safe_target(self.run_dir, entry) if entry else None
            if target is not None and target.is_file():
                await self.open_path(target)
        self.update_status()

    async def expand_run_folder(self) -> None:
        tree = self.query_one("#tree", Explorer)
        await tree.reload()
        for node in tree.root.children:
            if node.data is not None and Path(node.data.path).resolve() == self.run_dir.resolve():
                node.expand()

    def update_plan(self, snap: dict) -> None:
        view = snap["plan"]
        table = self.query_one("#plan", DataTable)
        table.clear()
        if not view:
            return
        plan = W.plan_from_view(view)
        level_of = {tid: lv for lv, ids in enumerate(view["levels"]) for tid in ids}
        for t in sorted(plan.tasks, key=lambda t: (level_of.get(t.id, 0), t.id)):
            state = W.task_status(plan, t, snap["artifacts"].get(t.id))
            table.add_row(Text.from_markup(STATUS_MARK[state]), str(level_of.get(t.id, 0)), t.id, t.domain, t.kind, t.target or "")

    def update_problems(self, error: str | None = None) -> None:
        table = self.query_one("#problems", DataTable)
        table.clear()
        if error:
            table.add_row(Text("✗", style="#f14c4c"), "run", error)
        for rel in self._rejected:
            table.add_row(Text("✗", style="#f14c4c"), "unsafe_path", rel)
        for c in self.checks:
            if not c.ok:
                table.add_row(Text("✗", style="#f14c4c"), c.name, c.detail)
        count = table.row_count
        if not count and self.checks:
            table.add_row(Text("✓", style="#89d185"), "no problems", f"all {len(self.checks)} checks pass")
        pane = self.query_one("#panel", TabbedContent).get_tab("problems-pane")
        pane.label = f"Problems ({count})" if count else "Problems"

    def recheck_run(self) -> None:
        snap = self.current_run.snapshot()
        if not snap["plan"]:
            return
        d = W.recheck(self.current_run.id, W.plan_from_view(snap["plan"]), snap["artifacts"], self.run_dir)
        self.checks = [CheckRow(c.name, c.ok, c.detail or "") for c in d.checks]
        self.update_problems(snap["error"])
        self.query_one("#panel", TabbedContent).active = "problems-pane"

    @on(DataTable.RowSelected, "#problems")
    async def _problem_selected(self, event: DataTable.RowSelected) -> None:
        row = event.data_table.get_row(event.row_key)
        target = W.path_in_problem(str(row[2]), self.run_dir) if self.run_dir else None
        if target is not None:
            await self.open_path(target)

    # --- status bar -------------------------------------------------------------

    def update_status(self) -> None:
        bar = self.query_one("#status", Static)
        left = [f"⌂ {self.root.name}"]
        failed = sum(not c.ok for c in self.checks) + len(self._rejected)
        if self.current_run:
            state = self.current_run.status
            if self.checks:
                state += f" · {sum(c.ok for c in self.checks)}/{len(self.checks)} checks"
            left.append(f"run {self.current_run.id} {state}")
        bar.set_class(bool(failed), "failed")
        right = []
        editor = self.current_editor()
        if editor is not None:
            row, col = editor.cursor_location
            right = [f"Ln {row + 1}, Col {col + 1}", editor.language or "plain text"]
        bar.update(Text("   ".join(left) + "     " + "   ".join(right)))


class CheckRow:
    def __init__(self, name: str, ok: bool, detail: str):
        self.name, self.ok, self.detail = name, ok, detail


def event_line(e: dict) -> str:
    bits = [e.get("kind", "?"), e.get("callee") or "", e.get("task_id") or ""]
    if e.get("latency_ms") is not None:
        bits.append(f"{e['latency_ms'] / 1000:.1f}s")
    if e.get("output_tokens"):
        bits.append(f"{e['output_tokens']} tok")
    if e.get("ok") is False:
        bits.append(f"FAILED {str(e.get('error') or '')[:160]}")
    return " ".join(b for b in bits if b)


def run_app(path: str = ".", autorun: dict | None = None) -> None:
    SlmCode(path, autorun).run()
