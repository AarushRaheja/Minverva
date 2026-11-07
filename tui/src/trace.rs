//! Reads the append-only JSONL traces written by `slm/trace.py` (.slm/traces/<run_id>.jsonl).
//! Field names mirror `TraceEvent` exactly; every field is optional so older traces still parse.

use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

pub const DOMAINS: [&str; 4] = ["database", "auth", "network", "frontend"];

pub fn adapter_of(domain: &str) -> String {
    format!("spec-{domain}")
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct TraceEvent {
    pub run_id: String,
    pub ts: f64,
    pub kind: String,
    pub caller: String,
    pub callee: String,
    pub model: Option<String>,
    pub input_chars: u64,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub latency_ms: f64,
    pub attempt: u32,
    pub ok: bool,
    pub error: Option<String>,
    pub mode: Option<String>,
    pub project_id: Option<String>,
    pub task_id: Option<String>,
    pub domain: Option<String>,
    pub dep_level: Option<u32>,
    pub adapter: Option<String>,
    pub t_start: Option<f64>,
    pub t_end: Option<f64>,
    pub output: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    #[allow(dead_code)] // planned but not yet routed; kept for the manager-plan view
    Pending,
    Running,
    Ok,
    Fail,
}

impl Status {
    pub fn label(self) -> &'static str {
        match self {
            Status::Pending => "pending",
            Status::Running => "running",
            Status::Ok => "ok",
            Status::Fail => "fail",
        }
    }
}

#[derive(Debug, Clone)]
pub struct TaskRow {
    pub id: String,
    pub domain: String,
    pub adapter: String,
    pub level: u32,
    pub status: Status,
    pub detail: String,
    pub t_start: Option<f64>,
    pub t_end: Option<f64>,
}

impl TaskRow {
    pub fn secs(&self) -> Option<f64> {
        Some(self.t_end? - self.t_start?)
    }
}

#[derive(Debug, Clone, Default)]
pub struct AdapterStats {
    pub calls: u32,
    pub failures: u32,
    pub in_tokens: u64,
    pub out_tokens: u64,
    pub latency_ms: Vec<f64>,
}

impl AdapterStats {
    pub fn avg_ms(&self) -> f64 {
        if self.latency_ms.is_empty() {
            0.0
        } else {
            self.latency_ms.iter().sum::<f64>() / self.latency_ms.len() as f64
        }
    }
}

/// Everything the UI needs about one run, derived from its events alone.
#[derive(Debug, Clone, Default)]
pub struct Run {
    pub id: String,
    pub path: PathBuf,
    pub modified: Option<SystemTime>,
    pub events: Vec<TraceEvent>,
    pub bad_lines: usize,
}

impl Run {
    pub fn load(path: &Path) -> Run {
        let text = fs::read_to_string(path).unwrap_or_default();
        let mut run = Run::from_text(&text);
        run.path = path.to_path_buf();
        run.modified = fs::metadata(path).and_then(|m| m.modified()).ok();
        if run.id.is_empty() {
            run.id = path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
        }
        run
    }

    pub fn from_text(text: &str) -> Run {
        let mut run = Run::default();
        for line in text.lines().filter(|l| !l.trim().is_empty()) {
            match serde_json::from_str::<TraceEvent>(line) {
                Ok(e) => run.events.push(e),
                Err(_) => run.bad_lines += 1, // a half-written last line while the run is live
            }
        }
        run.id = run.events.first().map(|e| e.run_id.clone()).unwrap_or_default();
        run
    }

    pub fn project_id(&self) -> Option<&str> {
        self.events.iter().find_map(|e| e.project_id.as_deref())
    }

    pub fn mode(&self) -> &str {
        self.events.iter().rev().find_map(|e| e.mode.as_deref()).unwrap_or("?")
    }

    pub fn plan(&self) -> Option<&TraceEvent> {
        self.events.iter().find(|e| e.kind == "plan")
    }

    pub fn final_event(&self) -> Option<&TraceEvent> {
        self.events.iter().rev().find(|e| e.kind == "final")
    }

    /// "pass", "fail:<check>", "error", or "running".
    pub fn verdict(&self) -> String {
        match self.final_event() {
            None => "running".into(),
            Some(f) if !f.ok => "error".into(),
            Some(f) => f.output.clone().unwrap_or_else(|| "?".into()),
        }
    }

    pub fn passed(&self) -> Option<bool> {
        self.final_event().map(|f| f.ok && f.output.as_deref() == Some("pass"))
    }

    pub fn planned_tasks(&self) -> Option<usize> {
        self.plan()?.output.as_deref()?.parse().ok()
    }

    /// One row per task: a `route` event makes it Running, its `task` event settles it.
    pub fn tasks(&self) -> Vec<TaskRow> {
        let mut rows: Vec<TaskRow> = Vec::new();
        let mut index: BTreeMap<String, usize> = BTreeMap::new();
        for e in &self.events {
            if e.kind != "route" && e.kind != "task" {
                continue;
            }
            let Some(id) = e.task_id.clone() else { continue };
            let domain = e.domain.clone().unwrap_or_else(|| "?".into());
            let i = *index.entry(id.clone()).or_insert_with(|| {
                rows.push(TaskRow {
                    id: id.clone(),
                    adapter: e.adapter.clone().unwrap_or_else(|| adapter_of(&domain)),
                    domain: domain.clone(),
                    level: e.dep_level.unwrap_or(0),
                    status: Status::Running,
                    detail: String::new(),
                    t_start: e.t_start,
                    t_end: None,
                });
                rows.len() - 1
            });
            if e.kind == "task" {
                let r = &mut rows[i];
                r.status = if e.ok { Status::Ok } else { Status::Fail };
                r.detail = e.error.clone().or_else(|| e.output.clone()).unwrap_or_default();
                r.t_start = e.t_start.or(r.t_start);
                r.t_end = e.t_end;
                if let Some(l) = e.dep_level {
                    r.level = l;
                }
            }
        }
        rows.sort_by(|a, b| a.level.cmp(&b.level).then_with(|| natural_cmp(&a.id, &b.id)));
        rows
    }

    pub fn max_level(&self) -> u32 {
        self.tasks().iter().map(|t| t.level).max().unwrap_or(0)
    }

    /// Model-call stats keyed by callee (manager, spec-database, ...).
    pub fn llm_stats(&self) -> BTreeMap<String, AdapterStats> {
        let mut out: BTreeMap<String, AdapterStats> = BTreeMap::new();
        for e in self.events.iter().filter(|e| e.kind == "llm") {
            let s = out.entry(e.callee.clone()).or_default();
            s.calls += 1;
            if !e.ok {
                s.failures += 1;
            }
            s.in_tokens += e.input_tokens;
            s.out_tokens += e.output_tokens;
            s.latency_ms.push(e.latency_ms);
        }
        out
    }

    /// (start, end) wall time of the run, for the timeline.
    pub fn span(&self) -> Option<(f64, f64)> {
        let starts = self.events.iter().filter_map(|e| e.t_start.or(Some(e.ts)));
        let ends = self.events.iter().filter_map(|e| e.t_end.or(Some(e.ts)));
        let lo = starts.fold(f64::INFINITY, f64::min);
        let hi = ends.fold(f64::NEG_INFINITY, f64::max);
        (lo.is_finite() && hi.is_finite()).then_some((lo, hi.max(lo + 1e-3)))
    }

    pub fn wall_secs(&self) -> f64 {
        self.span().map(|(a, b)| b - a).unwrap_or(0.0)
    }
}

/// "t2" before "t12": compare runs of digits as numbers (real plans use ids like t1..t13).
pub fn natural_cmp(a: &str, b: &str) -> std::cmp::Ordering {
    fn chunks(s: &str) -> Vec<(bool, String)> {
        let mut out: Vec<(bool, String)> = Vec::new();
        for c in s.chars() {
            let d = c.is_ascii_digit();
            match out.last_mut() {
                Some((kind, buf)) if *kind == d => buf.push(c),
                _ => out.push((d, c.to_string())),
            }
        }
        out
    }
    let (ca, cb) = (chunks(a), chunks(b));
    for (x, y) in ca.iter().zip(cb.iter()) {
        let o = match (x.0, y.0) {
            (true, true) => {
                let (xs, ys) = (x.1.trim_start_matches('0'), y.1.trim_start_matches('0'));
                xs.len().cmp(&ys.len()).then_with(|| xs.cmp(ys))
            }
            _ => x.1.cmp(&y.1),
        };
        if o.is_ne() {
            return o;
        }
    }
    ca.len().cmp(&cb.len())
}

/// Every `*.jsonl` under the trace dir, newest first.
pub fn list_runs(dir: &Path) -> Vec<(PathBuf, SystemTime)> {
    let mut out: Vec<(PathBuf, SystemTime)> = fs::read_dir(dir)
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| e.path().extension().is_some_and(|x| x == "jsonl"))
        .filter_map(|e| Some((e.path(), e.metadata().ok()?.modified().ok()?)))
        .collect();
    out.sort_by(|a, b| b.1.cmp(&a.1));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn derives_tasks_and_verdict() {
        let text = r#"{"run_id":"r","ts":1,"kind":"plan","caller":"gold","callee":"plan","ok":true,"mode":"gold","project_id":"p0","output":"2"}
{"run_id":"r","ts":1,"kind":"route","caller":"dispatch","callee":"spec-database","task_id":"t1","domain":"database","dep_level":0}
{"run_id":"r","ts":2,"kind":"task","caller":"dispatch","callee":"spec-database","ok":true,"task_id":"t1","domain":"database","dep_level":0,"t_start":1.0,"t_end":1.5,"output":"ok"}
{"run_id":"r","ts":2,"kind":"route","caller":"dispatch","callee":"spec-auth","task_id":"t2","domain":"auth","dep_level":1}
{"run_id":"r","ts":3,"kind":"final","caller":"dispatch","callee":"integrator","ok":true,"output":"pass","t_start":1.0,"t_end":3.0}
{"run_id":"r","ts":3,"kind":"#;
        let run = Run::from_text(text);
        assert_eq!(run.bad_lines, 1);
        assert_eq!(run.planned_tasks(), Some(2));
        let t = run.tasks();
        assert_eq!(t.len(), 2);
        assert_eq!(t[0].status, Status::Ok);
        assert_eq!(t[1].status, Status::Running);
        assert_eq!(run.verdict(), "pass");
        assert_eq!(run.passed(), Some(true));
    }

    /// Exactly what `TraceEvent.model_dump_json()` writes: every field present, unset ones null.
    #[test]
    fn parses_pydantic_lines_with_nulls() {
        let line = r#"{"run_id":"cli-proj-dev-0","ts":1794022633.12,"kind":"route","caller":"dispatcher","callee":"spec-auth","model":null,"input_chars":0,"input_tokens":0,"output_tokens":0,"latency_ms":0.0,"attempt":1,"ok":true,"error":null,"mode":"gold","project_id":"proj-dev-0","task_id":"auth-session","domain":"auth","dep_level":1,"adapter":"spec-auth","t_start":null,"t_end":null,"output":null}"#;
        let run = Run::from_text(line);
        assert_eq!(run.bad_lines, 0);
        let t = run.tasks();
        assert_eq!((t[0].id.as_str(), t[0].level, t[0].status), ("auth-session", 1, Status::Running));
        assert_eq!(run.project_id(), Some("proj-dev-0"));
    }

    #[test]
    fn task_ids_sort_naturally() {
        let mut ids = vec!["t12", "t5", "t1", "auth-b", "auth-a"];
        ids.sort_by(|a, b| natural_cmp(a, b));
        assert_eq!(ids, ["auth-a", "auth-b", "t1", "t5", "t12"]);
    }
}
