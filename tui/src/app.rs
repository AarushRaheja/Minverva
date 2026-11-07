//! App state and key handling. Rendering lives in `ui/`.

use crate::arch::{self, ArchRun, Score};
use crate::demo::Demo;
use crate::runner::{Job, Msg, RunOpts};
use crate::trace::{Run, list_runs};
use ratatui::crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use std::collections::{BTreeMap, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tab {
    Pipeline,
    Tasks,
    Timeline,
    Deliverable,
    Log,
    Arms,
}

impl Tab {
    pub const ALL: [Tab; 6] = [Tab::Pipeline, Tab::Tasks, Tab::Timeline, Tab::Deliverable, Tab::Log, Tab::Arms];

    pub fn title(self) -> &'static str {
        match self {
            Tab::Pipeline => "Pipeline",
            Tab::Tasks => "Tasks",
            Tab::Timeline => "Timeline",
            Tab::Deliverable => "Deliverable",
            Tab::Log => "Log",
            Tab::Arms => "Arms",
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
        };
        app.status = if app.demo.is_some() {
            "demo run (synthetic trace). d: leave demo, r: run the real pipeline".into()
        } else {
            format!("watching {}", app.trace_dir.display())
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

    /// Traces from `slm run` / `slm ui` (.slm/traces) and from `slm.arch run` (out/arch/*/traces).
    fn all_traces(&self) -> Vec<(PathBuf, SystemTime)> {
        let mut all = list_runs(&self.trace_dir);
        for dir in arch::list_arch_runs(&self.root) {
            all.extend(list_runs(&dir.join("traces")));
        }
        all.sort_by(|a, b| b.1.cmp(&a.1));
        all
    }

    /// Sidebar name: `a1/mgr-G4--proj-dev-x` for arch traces, the file stem otherwise.
    pub fn run_label(&self, path: &Path) -> String {
        let stem = path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
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

    /// Called every tick: re-read the selected trace (cheap; traces are small) and drain the job.
    pub fn refresh(&mut self) {
        self.drain_job();
        self.refresh_arch();
        if let Some(d) = &self.demo {
            self.run = d.snapshot();
            self.refresh_files();
            return;
        }
        self.runs = self.all_traces();
        if let Some(p) = &self.pinned {
            if let Some(i) = self.runs.iter().position(|(r, _)| r == p) {
                self.run_sel = i;
            } else if p.exists() {
                self.run = Run::load(p);
                self.refresh_files();
                return;
            }
        }
        self.run_sel = self.run_sel.min(self.runs.len().saturating_sub(1));
        self.run = match self.runs.get(self.run_sel) {
            Some((p, _)) => Run::load(p),
            None => Run::default(),
        };
        self.refresh_files();
    }

    fn drain_job(&mut self) {
        let Some(job) = &mut self.job else { return };
        let mut lines = Vec::new();
        let mut trace = None;
        while let Ok(m) = job.rx.try_recv() {
            match m {
                Msg::Line(l) => lines.push(l),
                Msg::Trace(p) => trace = Some(p),
            }
        }
        let exit = job.poll_exit();
        let project = job.opts.project;
        for l in lines {
            self.push_log(l);
        }
        if let Some(p) = trace {
            self.pinned = Some(p);
        }
        if let Some(code) = exit {
            let msg = match code {
                Some(0) => format!("project {} finished", project),
                Some(c) => format!("run exited with code {c} (see Log)"),
                None => "run was killed".to_string(),
            };
            self.push_log(format!("── {msg}"));
            self.status = msg;
            self.job = None;
            // The newest trace is the run we just made.
            if self.pinned.is_none() {
                self.run_sel = 0;
            }
        }
    }

    fn push_log(&mut self, line: String) {
        self.log.push_back(line);
        while self.log.len() > LOG_CAP {
            self.log.pop_front();
        }
    }

    fn refresh_files(&mut self) {
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
        // an arch trace's files live at out/arch/<run>/files/<arm>/<project_id>
        if let Some((run_dir, arm, pid)) = arch_trace_parts(&self.run.path) {
            return Some(run_dir.join("files").join(arm).join(pid));
        }
        self.run.project_id().map(|p| self.out_dir.join(p))
    }

    pub fn selected_file_text(&self) -> Option<String> {
        let rel = self.files.get(self.file_sel)?;
        fs::read_to_string(self.deliverable_dir()?.join(rel)).ok()
    }

    fn start_job(&mut self) {
        if self.job.is_some() {
            self.status = "a run is already going (x to stop it)".into();
            return;
        }
        self.demo = None;
        let cmd = self.opts.command_line();
        match Job::spawn(&self.root, self.opts.clone()) {
            Ok(job) => {
                self.push_log(format!("$ {cmd}"));
                self.status = format!("running: {cmd}");
                self.job = Some(job);
                self.pinned = None;
                self.task_sel = 0;
            }
            Err(e) => {
                self.status = format!("could not start uv: {e} (is uv installed and --root right?)");
                self.push_log(self.status.clone());
            }
        }
    }

    pub fn on_key(&mut self, key: KeyEvent) {
        if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
            self.quit = true;
            return;
        }
        if self.show_help {
            self.show_help = false;
            return;
        }
        match key.code {
            KeyCode::Char('q') | KeyCode::Esc => self.quit = true,
            KeyCode::Char('?') => self.show_help = true,
            KeyCode::Tab => self.tab = Tab::ALL[(self.tab.index() + 1) % Tab::ALL.len()],
            KeyCode::BackTab => self.tab = Tab::ALL[(self.tab.index() + Tab::ALL.len() - 1) % Tab::ALL.len()],
            KeyCode::Char(c @ '1'..='6') => self.tab = Tab::ALL[c as usize - '1' as usize],
            KeyCode::Left | KeyCode::Char('h') => self.focus = Focus::Runs,
            KeyCode::Right | KeyCode::Char('l') => self.focus = Focus::Main,
            KeyCode::Down | KeyCode::Char('j') => self.move_sel(1),
            KeyCode::Up | KeyCode::Char('k') => self.move_sel(-1),
            KeyCode::PageDown => self.move_sel(10),
            KeyCode::PageUp => self.move_sel(-10),
            KeyCode::Char('r') => self.start_job(),
            KeyCode::Char('x') => {
                if let Some(j) = &mut self.job {
                    j.kill();
                    self.status = "stopping run...".into();
                }
            }
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
            return;
        }
        match self.tab {
            Tab::Tasks | Tab::Timeline | Tab::Pipeline => {
                self.task_sel = step(self.task_sel, self.run.tasks().len())
            }
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
    let Ok(rd) = fs::read_dir(dir) else { return };
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            walk(&p, out);
        } else {
            out.push(p);
        }
    }
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
