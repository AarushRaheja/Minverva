//! App state and key handling. Rendering lives in `ui/`.

use crate::arch::{self, ArchRun, Score};
use crate::build::{self, Build};
use crate::demo::Demo;
use crate::form::{self, Action, BuildForm, EngineInfo, EngineList};
use crate::runner::{BuildOpts, Job, JobKind, Msg, RunOpts};
use crate::trace::{Run, list_runs};
use ratatui::crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use std::collections::{BTreeMap, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{Receiver, TryRecvError};
use std::time::{Duration, Instant, SystemTime};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tab {
    Pipeline,
    Tasks,
    Timeline,
    Deliverable,
    Log,
    Arms,
    Report,
}

impl Tab {
    pub const ALL: [Tab; 7] = [Tab::Pipeline, Tab::Tasks, Tab::Timeline, Tab::Deliverable, Tab::Log, Tab::Arms, Tab::Report];

    pub fn title(self) -> &'static str {
        match self {
            Tab::Pipeline => "Pipeline",
            Tab::Tasks => "Tasks",
            Tab::Timeline => "Timeline",
            Tab::Deliverable => "Deliverable",
            Tab::Log => "Log",
            Tab::Arms => "Arms",
            Tab::Report => "Report",
        }
    }

    fn index(self) -> usize {
        Tab::ALL.iter().position(|t| *t == self).unwrap_or(0)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Focus {
    Runs,
    Main,
}

pub struct App {
    pub root: PathBuf,
    pub trace_dir: PathBuf,
    pub out_dir: PathBuf,
    pub runs: Vec<(PathBuf, SystemTime)>,
    pub run_sel: usize,
    pub run: Run,
    pub demo: Option<Demo>,
    pub tab: Tab,
    pub focus: Focus,
    pub task_sel: usize,
    pub files: Vec<PathBuf>,
    pub file_sel: usize,
    pub preview_scroll: u16,
    pub job: Option<Job>,
    pub log: VecDeque<String>,
    pub log_scroll: u16,
    pub opts: RunOpts,
    pub show_help: bool,
    pub status: String,
    pub started: Instant,
    pub quit: bool,
    /// out/arch/<run>/ folders with results, newest first, and the one shown in the Arms view
    pub arch_runs: Vec<PathBuf>,
    pub arch_sel: usize,
    pub arm_sel: usize,
    pub score: Score,
    arch: Option<(PathBuf, Option<SystemTime>, ArchRun)>,
    demo_arch: ArchRun,
    /// task id -> (kind, one-line spec), read from the deliverable's README (real ids are just t1..tN)
    pub task_info: BTreeMap<String, (String, String)>,
    pinned: Option<PathBuf>,
    /// the selected Minerva build, when the selected run is a `runs/<id>/` folder (cached by its stamp)
    pub build: Option<Build>,
    /// the new-build dialog, when open
    pub form: Option<BuildForm>,
    /// engines from `minerva engines --json`, loaded the first time the dialog opens
    pub engines: Option<EngineList>,
    engines_rx: Option<Receiver<EngineList>>,
    /// the job's process exited at this time with this code; lines still in the pipes are drained first
    finishing: Option<(Instant, Option<i32>)>,
    /// `q` was pressed while a build runs; a second `q` stops it and quits
    pub confirm_quit: bool,
    pub report_scroll: u16,
}

const LOG_CAP: usize = 2000;

impl App {
    pub fn new(root: PathBuf, trace: Option<PathBuf>, demo: bool) -> App {
        let trace_dir = root.join(".slm/traces");
        let out_dir = root.join("out/deliverable");
        let mut app = App {
            root,
            trace_dir,
            out_dir,
            runs: Vec::new(),
            run_sel: 0,
            run: Run::default(),
            demo: demo.then(Demo::new),
            tab: Tab::Pipeline,
            focus: Focus::Main,
            task_sel: 0,
            files: Vec::new(),
            file_sel: 0,
            preview_scroll: 0,
            job: None,
            log: VecDeque::new(),
            log_scroll: 0,
            opts: RunOpts::default(),
            show_help: false,
            status: String::new(),
            started: Instant::now(),
            quit: false,
            arch_runs: Vec::new(),
            arch_sel: 0,
            arm_sel: 0,
            score: Score::Spec,
            arch: None,
            demo_arch: arch::demo_run(),
            task_info: BTreeMap::new(),
            pinned: trace,
            build: None,
            form: None,
            engines: None,
            engines_rx: None,
            finishing: None,
            confirm_quit: false,
            report_scroll: 0,
        };
        app.status = if app.demo.is_some() {
            "demo run (synthetic trace). d: leave demo, r: run the real pipeline".into()
        } else {
            "r: new build   T: old slm run   ?: help".to_string()
        };
        app.refresh();
        app
    }

    pub fn spinner(&self) -> &'static str {
        const F: [&str; 10] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
        F[(self.started.elapsed().as_millis() / 90) as usize % F.len()]
    }

    pub fn job_running(&self) -> bool {
        self.job.is_some()
    }

    /// Minerva builds (runs/*/), traces from `slm run` / `slm ui` (.slm/traces) and from `slm.arch run`
    /// (out/arch/*/traces), newest first.
    fn all_runs(&self) -> Vec<(PathBuf, SystemTime)> {
        let mut all = build::list_builds(&self.root);
        all.extend(list_runs(&self.trace_dir));
        for dir in arch::list_arch_runs(&self.root) {
            all.extend(list_runs(&dir.join("traces")));
        }
        all.sort_by(|a, b| b.1.cmp(&a.1));
        all
    }

    pub fn is_build_path(path: &Path) -> bool {
        path.is_dir()
    }

    /// Sidebar name: the slug of a build (`track-invoices-for-my-clients`), `a1/mgr-G4--proj-dev-x` for arch
    /// traces, the file stem otherwise.
    pub fn run_label(&self, path: &Path) -> String {
        let stem = path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
        if Self::is_build_path(path) {
            let name = path.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
            // runs/<YYYYmmdd>-<HHMMSS>-<slug>: show the slug; other names as they are
            let parts: Vec<&str> = name.splitn(3, '-').collect();
            return match parts.as_slice() {
                [d, t, slug] if d.len() == 8 && t.len() == 6 && d.chars().all(|c| c.is_ascii_digit()) => slug.to_string(),
                _ => name,
            };
        }
        match arch_trace_parts(path) {
            Some((run_dir, _, _)) => format!("{}/{stem}", run_dir.file_name().unwrap_or_default().to_string_lossy()),
            None => stem,
        }
    }

    /// Re-read results.jsonl only when it changed (it can be large once many arms ran).
    fn refresh_arch(&mut self) {
        self.arch_runs = arch::list_arch_runs(&self.root);
        self.arch_sel = self.arch_sel.min(self.arch_runs.len().saturating_sub(1));
        let Some(dir) = self.arch_runs.get(self.arch_sel).cloned() else {
            self.arch = None;
            return;
        };
        let mtime = std::fs::metadata(dir.join("results.jsonl")).and_then(|m| m.modified()).ok();
        let checks = std::fs::metadata(dir.join("runchecks.jsonl")).and_then(|m| m.modified()).ok();
        let stamp = mtime.max(checks);
        if !matches!(&self.arch, Some((d, t, _)) if *d == dir && *t == stamp) {
            self.arch = Some((dir.clone(), stamp, ArchRun::load(&dir)));
        }
    }

    /// What the Arms view shows: the selected out/arch run, or made-up numbers in demo mode.
    pub fn arch_run(&self) -> Option<&ArchRun> {
        if self.demo.is_some() && self.arch.is_none() {
            return Some(&self.demo_arch);
        }
        self.arch.as_ref().map(|(_, _, r)| r)
    }

    /// Called every tick: drain the job, then re-read the selected run. A trace is re-parsed (traces are small); a
    /// build is reloaded only when its stamp (the newest of a few file times) changes.
    pub fn refresh(&mut self) {
        self.drain_job();
        self.poll_engines();
        self.refresh_arch();
        if let Some(d) = &self.demo {
            self.run = d.snapshot();
            self.build = None;
            self.refresh_files();
            return;
        }
        self.runs = self.all_runs();
        if let Some(p) = &self.pinned {
            match self.runs.iter().position(|(r, _)| r == p) {
                Some(i) => self.run_sel = i,
                // opened with --build/--trace from outside runs/ or .slm/traces: list it first, so the sidebar agrees
                None if p.exists() => {
                    let t = fs::metadata(p).and_then(|m| m.modified()).unwrap_or(SystemTime::UNIX_EPOCH);
                    self.runs.insert(0, (p.clone(), t));
                    self.run_sel = 0;
                }
                None => {}
            }
        }
        let mut selected = None;
        if selected.is_none() {
            self.run_sel = self.run_sel.min(self.runs.len().saturating_sub(1));
            selected = self.runs.get(self.run_sel).map(|(p, _)| p.clone());
        }
        match selected {
            Some(p) if Self::is_build_path(&p) => {
                let stamp = build::stamp(&p);
                let fresh = !matches!(&self.build, Some(b) if b.dir == p && b.stamp == stamp);
                if fresh {
                    self.build = Some(Build::load(&p));
                }
                self.run = Run::default();
            }
            Some(p) => {
                self.build = None;
                self.run = Run::load(&p);
            }
            None => {
                self.build = None;
                self.run = Run::default();
            }
        }
        self.refresh_files();
    }

    fn poll_engines(&mut self) {
        let Some(rx) = &self.engines_rx else { return };
        match rx.try_recv() {
            Ok(list) => {
                self.engines = Some(list);
                self.engines_rx = None;
            }
            Err(TryRecvError::Disconnected) => self.engines_rx = None,
            Err(TryRecvError::Empty) => {}
        }
    }

    /// The engines the dialog can offer; empty while they load or if listing them failed.
    pub fn engine_list(&self) -> &[EngineInfo] {
        match &self.engines {
            Some(Ok(list)) => list,
            _ => &[],
        }
    }

    fn drain_job(&mut self) {
        let Some(job) = &mut self.job else { return };
        let mut lines = Vec::new();
        let mut trace = None;
        let mut run_dir = None;
        let mut disconnected = false;
        loop {
            match job.rx.try_recv() {
                Ok(Msg::Line(l)) => lines.push(l),
                Ok(Msg::Trace(p)) => trace = Some(p),
                Ok(Msg::RunDir(p)) => run_dir = Some(p),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => {
                    disconnected = true;
                    break;
                }
            }
        }
        job.escalate();
        if self.finishing.is_none() {
            if let Some(code) = job.poll_exit() {
                job.reap_group();
                self.finishing = Some((Instant::now(), code));
            }
        }
        let kind = job.kind.clone();
        for l in lines {
            self.push_log(l);
        }
        if let Some(p) = trace.or(run_dir) {
            self.pinned = Some(p);
            self.task_sel = 0;
            self.file_sel = 0;
            self.report_scroll = 0;
        }
        // After the exit, keep reading until the pipes close (or 1.5 s, if a grandchild holds them open).
        let Some((at, code)) = self.finishing else { return };
        if !disconnected && at.elapsed() < Duration::from_millis(1500) {
            return;
        }
        let msg = match (&kind, code) {
            (JobKind::Build(_), Some(0)) => "build finished: verified".to_string(),
            (JobKind::Build(_), Some(10)) => "build finished: works, with defects (see Report)".to_string(),
            (JobKind::Build(_), Some(20)) => "build finished: fallback UI shipped (see Report)".to_string(),
            (JobKind::Build(_), Some(30)) => "build failed (see Report)".to_string(),
            (JobKind::Build(_), Some(130)) => "build stopped; e resumes it".to_string(),
            (JobKind::Slm(o), Some(0)) => format!("project {} finished", o.project),
            (_, Some(c)) => format!("run exited with code {c} (see Log)"),
            (_, None) => "run was killed".to_string(),
        };
        self.push_log(format!("── {msg}"));
        self.status = msg;
        self.job = None;
        self.finishing = None;
        self.confirm_quit = false;
        // The newest run is the one we just made.
        if self.pinned.is_none() {
            self.run_sel = 0;
        }
    }

    fn push_log(&mut self, line: String) {
        self.log.push_back(line);
        while self.log.len() > LOG_CAP {
            self.log.pop_front();
        }
    }

    fn refresh_files(&mut self) {
        if let Some(b) = &self.build {
            self.files = b.file_list.clone();
            self.task_info.clear();
            self.file_sel = self.file_sel.min(self.files.len().saturating_sub(1));
            return;
        }
        let Some(base) = self.deliverable_dir() else {
            self.files.clear();
            self.task_info.clear();
            return;
        };
        self.task_info = fs::read_to_string(base.join("README.md")).map(|t| parse_task_info(&t)).unwrap_or_default();
        let mut files = Vec::new();
        walk(&base, &mut files);
        files.sort();
        self.files = files.into_iter().filter_map(|p| p.strip_prefix(&base).ok().map(Path::to_path_buf)).collect();
        self.file_sel = self.file_sel.min(self.files.len().saturating_sub(1));
    }

    pub fn deliverable_dir(&self) -> Option<PathBuf> {
        if let Some(b) = &self.build {
            return Some(b.dir.clone());
        }
        // an arch trace's files live at out/arch/<run>/files/<arm>/<project_id>
        if let Some((run_dir, arm, pid)) = arch_trace_parts(&self.run.path) {
            return Some(run_dir.join("files").join(arm).join(pid));
        }
        self.run.project_id().map(|p| self.out_dir.join(p))
    }

    /// Text of the selected file; None for binary files (screenshots) and anything over 1 MB.
    pub fn selected_file_text(&self) -> Option<String> {
        let rel = self.files.get(self.file_sel)?;
        let path = self.deliverable_dir()?.join(rel);
        if fs::metadata(&path).map(|m| m.len() > 1_000_000).unwrap_or(true) {
            return None;
        }
        fs::read_to_string(path).ok()
    }

    pub fn selected_file_path(&self) -> Option<PathBuf> {
        Some(self.deliverable_dir()?.join(self.files.get(self.file_sel)?))
    }

    fn start(&mut self, kind: JobKind) {
        if self.job.is_some() {
            self.status = "a run is already going (x to stop it)".into();
            return;
        }
        self.demo = None;
        let cmd = kind.command_line();
        match Job::spawn(&self.root, kind) {
            Ok(job) => {
                self.push_log(format!("$ {cmd}"));
                self.status = format!("running: {cmd}");
                self.job = Some(job);
                self.pinned = None;
                self.task_sel = 0;
                self.finishing = None;
            }
            Err(e) => {
                self.status = format!("could not start uv: {e} (is uv installed and --root right?)");
                self.push_log(self.status.clone());
            }
        }
    }

    pub fn start_build(&mut self, opts: BuildOpts) {
        self.tab = Tab::Pipeline;
        self.start(JobKind::Build(opts));
    }

    fn open_form(&mut self, form: BuildForm) {
        if self.job.is_some() {
            self.status = "a build is running (x stops it)".into();
            return;
        }
        if self.engines.is_none() && self.engines_rx.is_none() {
            self.engines_rx = Some(form::load_engines(&self.root));
        }
        self.form = Some(form);
    }

    /// `e`: resume the selected build with `--out`, so finished stages are not paid for again.
    fn resume_selected(&mut self) {
        let Some(b) = &self.build else {
            self.status = "select a Minerva build to resume (e)".into();
            return;
        };
        if matches!(b.state(), build::State::Finished(ref s, _) if s != "failed") {
            self.status = "this build finished; r starts a new one".into();
            return;
        }
        let form = BuildForm::resume(b.dir.clone(), &b.meta, b.spent(), self.engine_list());
        self.open_form(form);
    }

    /// `O`: open the selected file (a screenshot, the report, a source file) with the system viewer. Local only.
    fn open_selected(&mut self) {
        let Some(path) = self.selected_file_path() else {
            self.status = "select a file in Deliverable (4) to open it".into();
            return;
        };
        let opener = if cfg!(target_os = "macos") { "open" } else { "xdg-open" };
        match std::process::Command::new(opener)
            .arg(&path)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
        {
            Ok(_) => self.status = format!("opened {}", path.display()),
            Err(e) => self.status = format!("could not run {opener}: {e}"),
        }
    }

    fn stop_job(&mut self) {
        if let Some(j) = &mut self.job {
            j.stop();
            self.status = "stopping: sent Ctrl-C to the build (it saves what finished; e resumes)".into();
        }
    }

    pub fn on_key(&mut self, key: KeyEvent) {
        if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
            self.quit = true;
            return;
        }
        if let Some(form) = &mut self.form {
            let engines: Vec<EngineInfo> = match &self.engines {
                Some(Ok(list)) => list.clone(),
                _ => Vec::new(),
            };
            match form.on_key(key, &engines) {
                Action::None => {}
                Action::Cancel => self.form = None,
                Action::Start(opts) => {
                    self.form = None;
                    self.start_build(opts);
                }
            }
            return;
        }
        if self.show_help {
            self.show_help = false;
            return;
        }
        let quit_key = matches!(key.code, KeyCode::Char('q') | KeyCode::Esc);
        if self.confirm_quit && !quit_key {
            self.confirm_quit = false;
            self.status = "still running".into();
        }
        match key.code {
            KeyCode::Char('q') | KeyCode::Esc => {
                if self.job.is_some() && !self.confirm_quit {
                    self.confirm_quit = true;
                    self.status = "a build is running: q again stops it and quits, any other key stays".into();
                } else {
                    self.quit = true;
                }
            }
            KeyCode::Char('?') => self.show_help = true,
            KeyCode::Tab => self.tab = Tab::ALL[(self.tab.index() + 1) % Tab::ALL.len()],
            KeyCode::BackTab => self.tab = Tab::ALL[(self.tab.index() + Tab::ALL.len() - 1) % Tab::ALL.len()],
            KeyCode::Char(c @ '1'..='7') => self.tab = Tab::ALL[c as usize - '1' as usize],
            KeyCode::Left | KeyCode::Char('h') => self.focus = Focus::Runs,
            KeyCode::Right | KeyCode::Char('l') => self.focus = Focus::Main,
            KeyCode::Down | KeyCode::Char('j') => self.move_sel(1),
            KeyCode::Up | KeyCode::Char('k') => self.move_sel(-1),
            KeyCode::PageDown => self.move_sel(10),
            KeyCode::PageUp => self.move_sel(-10),
            KeyCode::Char('J') => self.scroll_text(5),
            KeyCode::Char('K') => self.scroll_text(-5),
            KeyCode::Char('r') | KeyCode::Char('n') => self.open_form(BuildForm::new()),
            KeyCode::Char('e') => self.resume_selected(),
            KeyCode::Char('O') => self.open_selected(),
            KeyCode::Char('T') => self.start(JobKind::Slm(self.opts.clone())),
            KeyCode::Char('x') => self.stop_job(),
            KeyCode::Char('+') | KeyCode::Char('=') => self.opts.project += 1,
            KeyCode::Char('-') => self.opts.project = self.opts.project.saturating_sub(1),
            KeyCode::Char('g') => self.opts.gold = !self.opts.gold,
            KeyCode::Char('p') => self.opts.parallel = !self.opts.parallel,
            KeyCode::Char('s') => {
                self.opts.split = if self.opts.split == "dev" { "test".into() } else { "dev".into() }
            }
            KeyCode::Char('d') => {
                if self.demo.is_some() {
                    self.demo = None;
                    self.status = format!("watching {}", self.trace_dir.display());
                } else {
                    self.demo = Some(Demo::new());
                    self.status = "demo run (synthetic trace)".into();
                }
            }
            KeyCode::Char('[') => self.arch_sel = self.arch_sel.saturating_sub(1),
            KeyCode::Char(']') => self.arch_sel = (self.arch_sel + 1).min(self.arch_runs.len().saturating_sub(1)),
            KeyCode::Char('o') => {
                self.score = if self.score == Score::Spec { Score::Run } else { Score::Spec };
                self.status = format!("arms graded by the {}", self.score.label());
            }
            KeyCode::Char('R') => {
                if let Some(d) = &mut self.demo {
                    d.restart();
                }
            }
            _ => {}
        }
    }

    /// J/K: scroll the file preview (Deliverable) or the report (Report).
    fn scroll_text(&mut self, delta: i32) {
        let apply = |v: u16| (v as i32 + delta).max(0) as u16;
        match self.tab {
            Tab::Report => self.report_scroll = apply(self.report_scroll),
            _ => self.preview_scroll = apply(self.preview_scroll),
        }
    }

    /// Rows the selection moves over in the Pipeline, Tasks and Timeline views.
    pub fn row_count(&self) -> usize {
        match &self.build {
            Some(b) if self.tab == Tab::Tasks => crate::ui::build_task_count(b),
            Some(b) => b.stages().len(),
            None => self.run.tasks().len(),
        }
    }

    fn move_sel(&mut self, delta: i32) {
        let step = |v: usize, len: usize| -> usize {
            if len == 0 {
                0
            } else {
                (v as i64 + delta as i64).clamp(0, len as i64 - 1) as usize
            }
        };
        if self.focus == Focus::Runs {
            self.run_sel = step(self.run_sel, self.runs.len());
            self.pinned = None;
            self.task_sel = 0;
            self.file_sel = 0;
            self.preview_scroll = 0;
            self.report_scroll = 0;
            return;
        }
        match self.tab {
            Tab::Tasks | Tab::Timeline | Tab::Pipeline => self.task_sel = step(self.task_sel, self.row_count()),
            Tab::Report => self.report_scroll = (self.report_scroll as i32 + delta).max(0) as u16,
            Tab::Deliverable => {
                self.file_sel = step(self.file_sel, self.files.len());
                self.preview_scroll = 0;
            }
            Tab::Arms => {
                let n = self.arch_run().map(|r| arch::summarize(&r.scored(self.score)).len()).unwrap_or(0);
                self.arm_sel = step(self.arm_sel, n);
            }
            Tab::Log => {
                // log_scroll counts lines up from the tail, so "down" moves toward the tail
                self.log_scroll = (self.log_scroll as i32 - delta).max(0) as u16;
            }
        }
    }
}

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    build::walk(dir, out)
}

/// Lines like "- `t4` [auth/session] Session cookie auth: ..." from the integrator's README.
fn parse_task_info(readme: &str) -> BTreeMap<String, (String, String)> {
    readme
        .lines()
        .filter_map(|l| {
            let rest = l.trim().strip_prefix("- `")?;
            let (id, rest) = rest.split_once('`')?;
            let rest = rest.trim().strip_prefix('[')?;
            let (dk, desc) = rest.split_once(']')?;
            let kind = dk.split_once('/').map(|(_, k)| k).unwrap_or(dk);
            Some((id.to_string(), (kind.to_string(), desc.trim().to_string())))
        })
        .collect()
}

impl App {
    /// "t4 session" when the deliverable README names the task's kind, else the bare id.
    pub fn task_label(&self, id: &str) -> String {
        match self.task_info.get(id) {
            Some((kind, _)) if !id.contains(kind.as_str()) => format!("{id} {kind}"),
            _ => id.to_string(),
        }
    }
}

/// out/arch/<run>/traces/<arm>--<project_id>.jsonl -> (out/arch/<run>, arm, project_id)
fn arch_trace_parts(path: &Path) -> Option<(PathBuf, String, String)> {
    let traces = path.parent()?;
    if traces.file_name()? != "traces" {
        return None;
    }
    let run_dir = traces.parent()?;
    if run_dir.parent()?.file_name()? != "arch" {
        return None;
    }
    let stem = path.file_stem()?.to_string_lossy().into_owned();
    let (arm, pid) = stem.split_once("--")?;
    Some((run_dir.to_path_buf(), arm.to_string(), pid.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_task_kinds_from_the_deliverable_readme() {
        let m = parse_task_info("## Tasks\n- `t4` [auth/session] Session cookie auth.\n- not a task\n");
        assert_eq!(m["t4"], ("session".to_string(), "Session cookie auth.".to_string()));
        assert_eq!(m.len(), 1);
    }

    #[test]
    fn arch_trace_paths_map_to_saved_files() {
        let p = Path::new("/r/out/arch/a1/traces/mgr-G4--proj-dev-x.jsonl");
        let (run, arm, pid) = arch_trace_parts(p).unwrap();
        assert_eq!(run, Path::new("/r/out/arch/a1"));
        assert_eq!((arm.as_str(), pid.as_str()), ("mgr-G4", "proj-dev-x"));
        assert!(arch_trace_parts(Path::new("/r/.slm/traces/cli-x.jsonl")).is_none());
    }
}
