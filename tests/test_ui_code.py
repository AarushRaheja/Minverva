"""`slm code`: disk safety and re-checking, then the real app driven headless. No model runs."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from slm.ui import workspace as W

SPEC = {"name": "plant tracker", "entities": ["plant", "garden"], "form": "plant", "oauth": True}


@pytest.mark.parametrize("rel", ["../evil.py", "src/../../evil.py", "/etc/evil", "", ".", "a\0b"])
def test_paths_cannot_leave_the_run_folder(tmp_path, rel):
    assert W.safe_target(tmp_path, rel) is None


def test_symlink_out_of_the_run_folder_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside)
    assert W.safe_target(root, "link/evil.py") is None


def test_writer_reports_rejects_and_never_rewrites(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    written: set[str] = set()
    done, bad = W.write_new_files(root, [{"path": "src/a.py", "content": "1"}, {"path": "../b.py", "content": "x"}], written)
    assert done == ["src/a.py"] and bad == ["../b.py"] and not (tmp_path / "b.py").exists()
    (root / "src/a.py").write_text("my edit")
    assert W.write_new_files(root, [{"path": "src/a.py", "content": "2"}], written) == ([], [])
    assert (root / "src/a.py").read_text() == "my edit"


pytest.importorskip("textual")

from textual.command import CommandPalette  # noqa: E402
from textual.widgets import DataTable, TabbedContent  # noqa: E402

from slm.ui.code import Commands, Editor, NewRun, SlmCode  # noqa: E402


def demo():
    return {"backend": "demo", "spec": SPEC}


async def finish(app, pilot):
    for _ in range(400):
        await pilot.pause(0.02)
        if app._finished:
            await pilot.pause()
            return
    raise AssertionError("the run did not finish")


def go(coro):
    return asyncio.run(coro)


def test_layout_has_the_vscode_regions(tmp_path):
    async def body():
        app = SlmCode(tmp_path)
        async with app.run_test(size=(140, 45)):
            for region in ("#activity", "#sidebar", "#editors", "#panel", "#status"):
                assert app.query_one(region).display
    go(body())


def test_toggles_hide_and_show(tmp_path):
    async def body():
        app = SlmCode(tmp_path)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("ctrl+b", "f4")
            assert not app.query_one("#sidebar").display and not app.query_one("#panel").display
            await pilot.press("ctrl+b", "ctrl+j")
            assert app.query_one("#sidebar").display and app.query_one("#panel").display
    go(body())


def test_open_edit_save_and_status(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")

    async def body():
        app = SlmCode(tmp_path)
        async with app.run_test(size=(140, 45)) as pilot:
            await app.open_path(f)
            await pilot.pause()
            ed = app.current_editor()
            assert isinstance(ed, Editor) and ed.language == "python"
            await app.open_path(f)
            assert len(app.editors) == 1  # the same file reuses its tab
            await pilot.press("y")
            assert ed.dirty and str(app.query_one(TabbedContent).get_tab("file-1").label).startswith("●")
            assert f.read_text() == "x = 1\n"
            await pilot.press("ctrl+s")
            assert f.read_text() == "yx = 1\n" and not ed.dirty
            assert "Col 2" in str(app.query_one("#status").render())
    go(body())


def test_closing_or_quitting_dirty_needs_a_second_press(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x\n")

    async def body():
        app = SlmCode(tmp_path)
        async with app.run_test(size=(140, 45)) as pilot:
            await app.open_path(f)
            await pilot.pause()
            await pilot.press("y")
            await pilot.press("ctrl+q")
            assert app.is_running and app._quit_armed
            await pilot.press("ctrl+w")
            assert len(app.editors) == 1
            await pilot.press("ctrl+w")
            await pilot.pause()
            assert not app.editors and f.read_text() == "x\n"
    go(body())


def test_save_warns_before_overwriting_an_outside_change(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x\n")

    async def body():
        app = SlmCode(tmp_path)
        async with app.run_test(size=(140, 45)) as pilot:
            await app.open_path(f)
            await pilot.pause()
            await pilot.press("y")
            f.write_text("changed elsewhere\n")
            app.current_editor().mtime -= 1
            await pilot.press("ctrl+s")
            assert f.read_text() == "changed elsewhere\n"
            await pilot.press("ctrl+s")
            assert f.read_text() == "yx\n"
    go(body())


def test_binary_file_is_refused_not_a_crash(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"\xff\xfe\x00")

    async def body():
        app = SlmCode(tmp_path)
        async with app.run_test(size=(140, 45)):
            await app.open_path(f)
            assert not app.editors
    go(body())


def test_demo_run_writes_files_then_an_edit_shows_up_in_problems(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def body():
        ws = tmp_path / "ws"
        ws.mkdir()
        app = SlmCode(ws, demo())
        async with app.run_test(size=(140, 45)) as pilot:
            await finish(app, pilot)
            assert app.current_run.status == "done" and app.checks and all(c.ok for c in app.checks)
            problems = app.query_one("#problems", DataTable)
            plan = app.query_one("#plan", DataTable)
            assert "no problems" in str(problems.get_row_at(0)[1]) and plan.row_count == len(app.current_run.plan["tasks"])
            page = next(app.run_dir.rglob("PlantPage.tsx"))
            page.write_text(page.read_text())
            await app.open_path(page)
            await pilot.pause()
            ed = app.current_editor()
            ed.text = "// emptied by the user\n"
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert any(not c.ok for c in app.checks) and "no problems" not in str(problems.get_row_at(0)[1])
            assert "failed" in app.query_one("#status").classes
    go(body())


def test_unsafe_model_path_is_reported_not_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def body():
        ws = tmp_path / "ws"
        ws.mkdir()
        app = SlmCode(ws, demo())
        async with app.run_test(size=(140, 45)) as pilot:
            await finish(app, pilot)
            with app.current_run.lock:  # after the run ends, so the demo finishing first can't race this
                app.current_run.artifacts["evil"] = {"files": [{"path": "../../evil.py", "content": "x"}], "summary": ""}
            app._finished = False
            await app.poll_run()
            assert not (tmp_path / "evil.py").exists() and not (ws / "evil.py").exists()
            assert app._rejected == ["../../evil.py"]
            assert app.query_one("#problems", DataTable).row_count >= 1
    go(body())


def test_new_run_form_shows_errors_and_starts_a_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def body():
        ws = tmp_path / "ws"
        ws.mkdir()
        app = SlmCode(ws)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert isinstance(app.screen, NewRun)
            app.screen.query_one("#entities").value = "Not A Slug!"
            app.screen.query_one("#go").press()
            await pilot.pause()
            assert isinstance(app.screen, NewRun) and app.current_run is None
            app.screen.query_one("#entities").value = "plant"
            app.screen.query_one("#form").value = "plant"
            app.screen.query_one("#go").press()
            await pilot.pause()
            assert not isinstance(app.screen, NewRun)
            await finish(app, pilot)
            assert app.current_run.status == "done"
    go(body())


def test_palette_lists_actions_and_skips_ignored_folders(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/config").write_text("")

    async def body():
        app = SlmCode(tmp_path)
        async with app.run_test(size=(140, 45)):
            names = [str(Path(p).relative_to(tmp_path)) for p in app.workspace_files()]
            assert names == ["src/a.py"]
            assert ("New run", "new_run") in Commands.ACTIONS
    go(body())


@pytest.mark.parametrize("key", ["ctrl+p", "f1"])
def test_palette_opens_over_the_editor_and_opens_a_file(tmp_path, key):
    (tmp_path / "a.py").write_text("x\n")
    (tmp_path / "target.py").write_text("y\n")

    async def body():
        app = SlmCode(tmp_path)
        async with app.run_test(size=(140, 45)) as pilot:
            await app.open_path(tmp_path / "a.py")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            await pilot.press(*"target")
            await pilot.pause(0.5)
            await pilot.press("down", "enter")
            await pilot.pause(0.2)
            assert app.current_editor().path == (tmp_path / "target.py").resolve()
            assert app.editors[(tmp_path / "a.py").resolve()][1].text == "x\n"  # nothing typed into the editor
    go(body())


def test_app_run_is_not_shadowed(tmp_path):
    """A `self.run` attribute once replaced App.run(), so `slm code` crashed on launch while run_test() passed."""
    async def body():
        app = SlmCode(tmp_path, demo())
        async with app.run_test(size=(140, 45)) as pilot:
            await finish(app, pilot)
            assert callable(app.run)
    go(body())
