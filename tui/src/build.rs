//! A Minerva build: the run directory `minerva build` writes (`runs/<date>-<slug>/`).
//!
//! The live picture comes from `events.jsonl` (minerva/events.py): `run_start`, `stage_start`, `stage_end`,
//! `run_end`. The stage files (`run.json`, `ledger.jsonl`, `status.json`, `stages/*.json`, `frontend/`, `verify/`,
//! `project/`, `REPORT.md`) fill in the rest, and stand in for events on runs made before events existed.
//! Every file may be missing or half-written while a build runs; nothing here panics on that.

use serde::Deserialize;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use crate::trace::Status;

/// The stages before and after the frontend rounds, in the order `build()` runs them.
pub const PRE_STAGES: [&str; 5] = ["plan", "backend", "seams", "preflight", "intent"];
pub const ROUND_STAGES: [&str; 3] = ["architect", "audit", "critic"];
pub const POST_STAGES: [&str; 2] = ["verify", "project"];

/// Heavy folders a run's project can grow once someone runs it; never walked.
pub const SKIP_DIRS: [&str; 7] = ["node_modules", ".venv", ".data", "dist", "__pycache__", ".git", "project.previous"];

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct Event {
    pub ts: f64,
    pub event: String,
    pub stage: Option<String>,
    pub round: Option<u32>,
    pub ok: Option<bool>,
    pub cached: Option<bool>,
    pub seconds: Option<f64>,
    pub usd: Option<f64>,
    pub estimate_usd: Option<f64>,
    pub detail: Option<String>,
    pub status: Option<String>,
    pub engine: Option<String>,
    pub resumed: Option<bool>,
    pub budget_usd: Option<f64>,
    pub spent_usd: Option<f64>,
    pub exit_code: Option<i32>,
}

#[derive(Debug, Clone, Default)]
pub struct Meta {
    pub brief: String,
    pub look: String,
    pub engine: String,
    pub started_at: String,
    pub max_repairs: u32,
    pub budget_usd: f64,
}

/// One row of the stage list: a stage, or one stage of one frontend round.
#[derive(Debug, Clone)]
pub struct StageRow {
    pub stage: String,
    pub round: Option<u32>,
    pub status: Status,
    pub cached: bool,
    pub seconds: Option<f64>,
    pub usd: Option<f64>,
    pub estimate: Option<f64>,
    pub detail: String,
    pub t_start: Option<f64>,
    pub t_end: Option<f64>,
}

impl StageRow {
    fn new(stage: &str, round: Option<u32>) -> StageRow {
        StageRow {
            stage: stage.to_string(),
            round,
            status: Status::Pending,
            cached: false,
            seconds: None,
            usd: None,
            estimate: None,
            detail: String::new(),
            t_start: None,
            t_end: None,
        }
    }

    pub fn label(&self) -> String {
        match self.round {
            Some(r) => format!("{} r{r}", self.stage),
            None => self.stage.clone(),
        }
    }
}

/// A backend task the specialists wrote: `t4` → files under src/auth/.
#[derive(Debug, Clone)]
pub struct BackendTask {
    pub id: String,
    pub domain: String,
    pub files: Vec<String>,
}

#[derive(Debug, Clone, Default)]
pub struct Round {
    pub round: u32,
    pub seconds: Option<f64>,
    pub output_tokens: Option<u64>,
    pub generation_error: Option<String>,
    pub audit_pass: Option<bool>,
    pub failed_gates: Vec<String>,
    pub build_errors: Vec<String>,
    pub failed_tests: Vec<String>,
    pub critic: Option<String>,
}

/// How the build stands: running, finished with a pipeline status, or interrupted.
#[derive(Debug, Clone, PartialEq)]
pub enum State {
    /// no events and no status: an empty or foreign directory
    Unknown,
    Running(String),
    /// verified | functional_with_defects | fallback_ui | failed, and the failed stage
    Finished(String, Option<String>),
    Stopped,
    Error(String),
}

#[derive(Debug, Clone, Default)]
pub struct Build {
    pub dir: PathBuf,
    pub id: String,
    pub meta: Meta,
    /// events after the last `run_start` (a resumed run appends to the same file)
    pub events: Vec<Event>,
    pub bad_lines: usize,
    /// total of ledger.jsonl: estimated $ of every paid model call so far
    pub spent: f64,
    pub status: Option<Value>,
    pub report: Option<String>,
    pub plan_name: Option<String>,
    /// domain -> the manager's one-line summary for it
    pub domain_summaries: Vec<(String, String)>,
    pub tasks: Vec<BackendTask>,
    pub rounds: Vec<Round>,
    pub journey: Vec<(String, bool)>,
    pub stamp: Option<SystemTime>,
    /// `files()`, computed once per load: the project is only rewritten when the events (and the stamp) move
    pub file_list: Vec<PathBuf>,
}

fn read_json(path: &Path) -> Option<Value> {
    serde_json::from_str(&fs::read_to_string(path).ok()?).ok()
}

fn mtime(path: &Path) -> Option<SystemTime> {
    fs::metadata(path).and_then(|m| m.modified()).ok()
}

/// The newest change among the files that move while a build runs. Cheap: a handful of stat calls.
pub fn stamp(dir: &Path) -> Option<SystemTime> {
    ["events.jsonl", "ledger.jsonl", "status.json", "run.json", "REPORT.md", "frontend/history.json", "stages"]
        .iter()
        .filter_map(|f| mtime(&dir.join(f)))
        .max()
}

fn domain_of(path: &str) -> &'static str {
    if path.starts_with("src/database") || path.ends_with(".sql") {
        "database"
    } else if path.starts_with("src/auth") {
        "auth"
    } else if path.starts_with("src/network") {
        "network"
    } else if path.starts_with("src/frontend") || path.starts_with("frontend/") {
        "frontend"
    } else {
        "integrator"
    }
}

impl Build {
    pub fn load(dir: &Path) -> Build {
        let mut b = Build {
            dir: dir.to_path_buf(),
            id: dir.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default(),
            stamp: stamp(dir),
            ..Build::default()
        };
        if let Some(m) = read_json(&dir.join("run.json")) {
            b.meta = Meta {
                brief: str_of(&m, "brief"),
                look: str_of(&m, "look"),
                engine: str_of(&m, "engine"),
                started_at: str_of(&m, "started_at"),
                max_repairs: m["max_repairs"].as_u64().unwrap_or(1) as u32,
                budget_usd: m["budget_usd"].as_f64().unwrap_or(0.0),
            };
        }
        b.parse_events(&fs::read_to_string(dir.join("events.jsonl")).unwrap_or_default());
        b.spent = fs::read_to_string(dir.join("ledger.jsonl"))
            .unwrap_or_default()
            .lines()
            .filter_map(|l| serde_json::from_str::<Value>(l).ok())
            .filter_map(|v| v["usd"].as_f64())
            .sum();
        b.status = read_json(&dir.join("status.json"));
        b.report = fs::read_to_string(dir.join("REPORT.md")).ok();
        if let Some(plan) = read_json(&dir.join("stages/plan.json")) {
            let spec: Option<Value> = plan["spec"].as_str().and_then(|s| serde_json::from_str(s).ok());
            if let Some(spec) = spec {
                b.plan_name = spec["name"].as_str().map(String::from);
                for d in ["database", "auth", "network", "frontend"] {
                    if let Some(s) = spec[d]["summary"].as_str() {
                        b.domain_summaries.push((d.to_string(), s.to_string()));
                    }
                }
            }
        }
        if let Some(backend) = read_json(&dir.join("stages/backend.json")) {
            if let Some(arts) = backend["artifacts"].as_object() {
                for (id, art) in arts {
                    let parsed: Option<Value> = art.as_str().and_then(|s| serde_json::from_str(s).ok());
                    let files: Vec<String> = parsed
                        .as_ref()
                        .and_then(|a| a["files"].as_array())
                        .map(|fs| fs.iter().filter_map(|f| f["path"].as_str().map(String::from)).collect())
                        .unwrap_or_default();
                    let domain = files.first().map(|f| domain_of(f)).unwrap_or("?").to_string();
                    b.tasks.push(BackendTask { id: id.clone(), domain, files });
                }
                b.tasks.sort_by(|x, y| crate::trace::natural_cmp(&x.id, &y.id));
            }
        }
        b.rounds = load_rounds(dir);
        if let Some(v) = read_json(&dir.join("verify/evidence.json")) {
            if let Some(tests) = v["tests"].as_array() {
                b.journey = tests
                    .iter()
                    .map(|t| (str_of(t, "id"), t["passed"].as_bool().unwrap_or(false)))
                    .collect();
            }
        }
        b.file_list = b.files();
        b
    }

    /// Keep only the latest attempt: everything after the last `run_start`. Bad lines (a half-written tail) are counted.
    pub fn parse_events(&mut self, text: &str) {
        let mut events = Vec::new();
        for line in text.lines().filter(|l| !l.trim().is_empty()) {
            match serde_json::from_str::<Event>(line) {
                Ok(e) => {
                    if e.event == "run_start" {
                        events.clear();
                    }
                    events.push(e);
                }
                Err(_) => self.bad_lines += 1,
            }
        }
        self.events = events;
    }

    fn run_end(&self) -> Option<&Event> {
        self.events.iter().rev().find(|e| e.event == "run_end")
    }

    pub fn state(&self) -> State {
        if let Some(end) = self.run_end() {
            let status = end.status.clone().unwrap_or_default();
            return match status.as_str() {
                "stopped" => State::Stopped,
                "error" => State::Error(end.detail.clone().unwrap_or_default()),
                _ => State::Finished(status, end.stage.clone()),
            };
        }
        if !self.events.is_empty() {
            let running = self
                .events
                .iter()
                .rev()
                .find(|e| e.event == "stage_start")
                .map(|e| e.stage.clone().unwrap_or_default())
                .unwrap_or_else(|| "starting".into());
            return State::Running(running);
        }
        // a run from before events.jsonl existed
        if let Some(s) = &self.status {
            return State::Finished(str_of(s, "status"), s["stage"].as_str().map(String::from));
        }
        State::Unknown
    }

    pub fn finished(&self) -> bool {
        matches!(self.state(), State::Finished(..) | State::Stopped | State::Error(_))
    }

    /// The engine, from run.json or the run_start event.
    pub fn engine(&self) -> String {
        if !self.meta.engine.is_empty() {
            return self.meta.engine.clone();
        }
        self.events.iter().find_map(|e| e.engine.clone()).unwrap_or_else(|| "?".into())
    }

    pub fn budget(&self) -> f64 {
        if self.meta.budget_usd > 0.0 {
            return self.meta.budget_usd;
        }
        self.events.iter().find_map(|e| e.budget_usd).unwrap_or(0.0)
    }

    /// $ spent: the ledger total, or the run_end figure if the ledger is unreadable.
    pub fn spent(&self) -> f64 {
        if self.spent > 0.0 {
            return self.spent;
        }
        self.run_end().and_then(|e| e.usd).unwrap_or(0.0)
    }

    pub fn detail(&self) -> String {
        if let Some(d) = self.run_end().and_then(|e| e.detail.clone()) {
            return d;
        }
        self.status.as_ref().map(|s| str_of(s, "detail")).unwrap_or_default()
    }

    /// Seconds from the first to the last event (live while running: up to `now`).
    pub fn wall_secs(&self, now: f64) -> f64 {
        let Some(first) = self.events.first() else { return 0.0 };
        let last = if self.finished() { self.events.last().map(|e| e.ts).unwrap_or(first.ts) } else { now };
        (last - first.ts).max(0.0)
    }

    /// Every stage in pipeline order, with what the events say about it. Frontend rounds get one row per stage.
    pub fn stages(&self) -> Vec<StageRow> {
        let mut rows: Vec<StageRow> = PRE_STAGES.iter().map(|s| StageRow::new(s, None)).collect();
        let last_round = self
            .events
            .iter()
            .filter_map(|e| e.round)
            .max()
            .max(self.rounds.iter().map(|r| r.round).max());
        for r in 0..=last_round.unwrap_or(0) {
            for s in ROUND_STAGES {
                rows.push(StageRow::new(s, Some(r)));
            }
        }
        rows.extend(POST_STAGES.iter().map(|s| StageRow::new(s, None)));

        if self.events.is_empty() {
            self.stages_from_files(&mut rows);
        }
        for e in &self.events {
            let Some(stage) = &e.stage else { continue };
            let Some(row) = rows.iter_mut().find(|r| &r.stage == stage && r.round == e.round) else { continue };
            match e.event.as_str() {
                "stage_start" => {
                    row.status = Status::Running;
                    row.t_start = Some(e.ts);
                    row.estimate = e.estimate_usd;
                }
                "stage_end" => {
                    row.status = if e.ok.unwrap_or(true) { Status::Ok } else { Status::Fail };
                    row.cached = e.cached.unwrap_or(false);
                    row.seconds = e.seconds;
                    row.usd = e.usd;
                    row.detail = e.detail.clone().unwrap_or_default();
                    row.t_end = Some(e.ts);
                    if row.t_start.is_none() {
                        row.t_start = Some(e.ts - e.seconds.unwrap_or(0.0));
                    }
                }
                _ => {}
            }
        }
        // A stage still "running" after the process stopped did not finish.
        if matches!(self.state(), State::Stopped | State::Error(_)) {
            for r in rows.iter_mut().filter(|r| r.status == Status::Running) {
                r.status = Status::Fail;
                r.detail = "interrupted".into();
            }
        }
        // Drop the critic rows that never ran (it only runs when an audit passes), unless the run is still going.
        let done = self.finished();
        rows.retain(|r| !(done && r.stage == "critic" && r.status == Status::Pending));
        rows
    }

    /// For runs without events.jsonl: what the stage files say happened.
    fn stages_from_files(&self, rows: &mut [StageRow]) {
        let d = &self.dir;
        let mark = |rows: &mut [StageRow], stage: &str, round: Option<u32>, ok: bool| {
            if let Some(r) = rows.iter_mut().find(|r| r.stage == stage && r.round == round) {
                r.status = if ok { Status::Ok } else { Status::Fail };
            }
        };
        for s in ["plan", "backend", "intent"] {
            if d.join(format!("stages/{s}.json")).exists() {
                mark(rows, s, None, true);
            }
        }
        if d.join("stages/backend.json").exists() {
            mark(rows, "seams", None, !d.join("stages/seams.json").exists());
        }
        if d.join("preflight/evidence.json").exists() {
            mark(rows, "preflight", None, true);
        }
        for r in &self.rounds {
            mark(rows, "architect", Some(r.round), r.generation_error.is_none());
            if let Some(pass) = r.audit_pass {
                mark(rows, "audit", Some(r.round), pass);
            }
            if r.critic.is_some() {
                mark(rows, "critic", Some(r.round), r.critic.as_deref() == Some("accept"));
            }
        }
        if !self.journey.is_empty() {
            mark(rows, "verify", None, self.journey.iter().all(|(_, ok)| *ok));
        }
        if d.join("project").is_dir() {
            mark(rows, "project", None, true);
        }
    }

    /// Short status label for headers and the runs list.
    pub fn label(&self) -> (String, Status) {
        match self.state() {
            State::Unknown => ("NO RUN".into(), Status::Pending),
            State::Running(stage) => (format!("RUNNING {stage}"), Status::Running),
            State::Stopped => ("STOPPED".into(), Status::Fail),
            State::Error(_) => ("ERROR".into(), Status::Fail),
            State::Finished(status, stage) => match status.as_str() {
                "verified" => ("VERIFIED".into(), Status::Ok),
                "functional_with_defects" => ("WORKS, WITH DEFECTS".into(), Status::Ok),
                "fallback_ui" => ("FALLBACK UI".into(), Status::Fail),
                "failed" => (format!("FAILED {}", stage.unwrap_or_default()).trim().to_string(), Status::Fail),
                other => (other.to_uppercase(), Status::Pending),
            },
        }
    }

    /// Files to browse: the generated project, the report and the screenshots, relative to the run dir.
    pub fn files(&self) -> Vec<PathBuf> {
        let mut out = Vec::new();
        if self.dir.join("REPORT.md").exists() {
            out.push(PathBuf::from("REPORT.md"));
        }
        let mut project = Vec::new();
        walk(&self.dir.join("project"), &mut project);
        project.sort();
        out.extend(project.into_iter().filter_map(|p| p.strip_prefix(&self.dir).ok().map(Path::to_path_buf)));
        out.extend(self.screenshots());
        out
    }

    pub fn screenshots(&self) -> Vec<PathBuf> {
        let mut shots = Vec::new();
        let mut dirs = vec![PathBuf::from("verify")];
        dirs.extend(self.rounds.iter().map(|r| PathBuf::from(format!("frontend/round-{}/render", r.round))));
        for rel in dirs {
            let Ok(rd) = fs::read_dir(self.dir.join(&rel)) else { continue };
            let mut pngs: Vec<PathBuf> = rd
                .flatten()
                .map(|e| e.path())
                .filter(|p| p.extension().is_some_and(|x| x == "png"))
                .filter_map(|p| p.file_name().map(|n| rel.join(n)))
                .collect();
            pngs.sort();
            shots.extend(pngs);
        }
        shots
    }
}

fn load_rounds(dir: &Path) -> Vec<Round> {
    // history.json is written once, after the loop; while it runs, read the round folders.
    let mut rounds: Vec<Round> = Vec::new();
    if let Some(h) = read_json(&dir.join("frontend/history.json")) {
        for r in h["rounds"].as_array().into_iter().flatten() {
            let score = &r["score"];
            rounds.push(Round {
                round: r["round"].as_u64().unwrap_or(0) as u32,
                seconds: r["seconds"].as_f64(),
                output_tokens: r["output_tokens"].as_u64(),
                generation_error: r["generation_error"].as_str().map(String::from),
                audit_pass: score["audit_pass"].as_bool(),
                failed_gates: failed_gates(score),
                build_errors: strings(&r["build_errors"]),
                failed_tests: strings(&r["failed_tests"]),
                critic: r["critic_verdict"].as_str().map(String::from),
            });
        }
        return rounds;
    }
    for n in 0..8u32 {
        let rd = dir.join(format!("frontend/round-{n}"));
        if !rd.is_dir() {
            break;
        }
        let mut round = Round { round: n, ..Round::default() };
        if let Some(g) = read_json(&rd.join("generation.json")) {
            round.seconds = g["seconds"].as_f64();
            round.output_tokens = g["output_tokens"].as_u64();
            round.generation_error = g["error"].as_str().map(String::from);
        }
        if let Some(c) = read_json(&rd.join("critique.json")) {
            round.critic = c["effective_verdict"].as_str().map(String::from);
        }
        rounds.push(round);
    }
    rounds
}

fn failed_gates(score: &Value) -> Vec<String> {
    score
        .as_object()
        .map(|m| {
            m.iter()
                .filter(|(k, v)| v.as_bool() == Some(false) && k.as_str() != "audit_pass")
                .map(|(k, _)| k.clone())
                .collect()
        })
        .unwrap_or_default()
}

fn strings(v: &Value) -> Vec<String> {
    v.as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default()
}

fn str_of(v: &Value, k: &str) -> String {
    v[k].as_str().unwrap_or_default().to_string()
}

/// Recursive file list that never enters SKIP_DIRS or follows symlinked folders.
pub fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(rd) = fs::read_dir(dir) else { return };
    for e in rd.flatten() {
        let p = e.path();
        let is_link = e.file_type().map(|t| t.is_symlink()).unwrap_or(false);
        if p.is_dir() {
            let name = e.file_name();
            if !is_link && !SKIP_DIRS.iter().any(|s| name == *s) {
                walk(&p, out);
            }
        } else {
            out.push(p);
        }
    }
}

/// `runs/*/` folders that hold a `run.json`, with the time they last changed.
pub fn list_builds(root: &Path) -> Vec<(PathBuf, SystemTime)> {
    let Ok(rd) = fs::read_dir(root.join("runs")) else { return Vec::new() };
    let mut out: Vec<(PathBuf, SystemTime)> = rd
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.join("run.json").exists())
        .map(|p| {
            let t = stamp(&p).unwrap_or(SystemTime::UNIX_EPOCH);
            (p, t)
        })
        .collect();
    out.sort_by(|a, b| b.1.cmp(&a.1));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
    }

    #[test]
    fn finished_build_reads_stages_rounds_and_status() {
        let b = Build::load(&fixture("build-finished"));
        assert_eq!(b.meta.engine, "modal");
        assert_eq!(b.state(), State::Finished("fallback_ui".into(), None));
        assert_eq!(b.label().0, "FALLBACK UI");
        let stages = b.stages();
        let plan = stages.iter().find(|r| r.stage == "plan").unwrap();
        assert_eq!(plan.status, Status::Ok);
        assert_eq!(plan.usd, Some(0.133));
        let audit0 = stages.iter().find(|r| r.stage == "audit" && r.round == Some(0)).unwrap();
        assert_eq!(audit0.status, Status::Fail);
        assert!(audit0.detail.contains("build"));
        assert!(!stages.iter().any(|r| r.stage == "critic"), "the critic never ran, so it is not listed");
        assert!((b.spent() - 0.581).abs() < 1e-9);
        assert_eq!(b.rounds.len(), 2);
        assert!(b.tasks.iter().any(|t| t.id == "t4" && t.domain == "auth"));
        assert_eq!(b.journey, vec![("journey:desktop".to_string(), true), ("journey:mobile".to_string(), true)]);
        let files = b.files();
        assert_eq!(files[0], PathBuf::from("REPORT.md"));
        assert!(files.iter().any(|f| f == Path::new("project/src/app.py")));
        assert!(!files.iter().any(|f| f.to_string_lossy().contains("node_modules") || f.to_string_lossy().contains(".data")));
        assert!(files.iter().any(|f| f == Path::new("verify/desktop.png")));
    }

    #[test]
    fn running_build_tolerates_a_half_written_line_and_keeps_the_last_attempt() {
        let b = Build::load(&fixture("build-running"));
        assert_eq!(b.bad_lines, 1);
        assert_eq!(b.state(), State::Running("architect".into()));
        assert_eq!(b.label().1, Status::Running);
        let stages = b.stages();
        let plan = stages.iter().find(|r| r.stage == "plan").unwrap();
        assert!(plan.cached, "the resumed attempt reused the saved plan");
        let arch = stages.iter().find(|r| r.stage == "architect" && r.round == Some(0)).unwrap();
        assert_eq!(arch.status, Status::Running);
        assert_eq!(arch.estimate, Some(0.3));
        assert!(stages.iter().any(|r| r.stage == "critic"), "a running build still lists the critic");
        assert!(b.wall_secs(b.events[0].ts + 10.0) >= 10.0);
    }

    #[test]
    fn stopped_build_marks_the_running_stage_interrupted() {
        let mut b = Build::default();
        b.parse_events(concat!(
            r#"{"ts": 1, "event": "run_start", "engine": "offline"}"#, "\n",
            r#"{"ts": 2, "event": "stage_start", "stage": "plan"}"#, "\n",
            r#"{"ts": 3, "event": "run_end", "status": "stopped", "usd": 0.0}"#, "\n",
        ));
        assert_eq!(b.state(), State::Stopped);
        let plan = b.stages().into_iter().find(|r| r.stage == "plan").unwrap();
        assert_eq!((plan.status, plan.detail.as_str()), (Status::Fail, "interrupted"));
    }

    #[test]
    fn lists_only_folders_with_run_json() {
        let root = std::env::temp_dir().join(format!("nova-builds-{}", std::process::id()));
        fs::create_dir_all(root.join("runs/a")).unwrap();
        fs::create_dir_all(root.join("runs/not-a-run")).unwrap();
        fs::write(root.join("runs/a/run.json"), "{}").unwrap();
        let found = list_builds(&root);
        assert_eq!(found.len(), 1);
        assert!(found[0].0.ends_with("runs/a"));
        fs::remove_dir_all(&root).ok();
    }
}
