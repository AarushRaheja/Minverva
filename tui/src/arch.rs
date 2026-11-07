//! Reads what `python -m slm.arch run` writes: out/arch/<run>/results.jsonl (one row per arm x project)
//! and, when present, runchecks.jsonl (the run-check grade that `report --score run` uses).
//! The summary mirrors `slm/arch/__main__.py::summarize` minus the bootstrap CIs.

use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

/// The arm every other arm is compared against, same default as `slm.arch report`.
pub const REF_ARM: &str = "mgr-G4";

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct Row {
    pub arm: String,
    pub project_id: String,
    pub template_id: Option<String>,
    pub gold_pass: bool,
    pub gold_task_rate: f64,
    pub first_fail: Option<String>,
    pub plan_valid: Option<bool>,
    pub plan_recall: Option<f64>,
    pub n_tasks: u32,
    pub calls: u32,
    pub tok_in: u64,
    pub tok_out: u64,
    pub wall_s: f64,
    pub crit_tok_out: u64,
    pub crit_s: f64,
    pub error: Option<String>,
    pub by_domain: BTreeMap<String, f64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
struct RunCheck {
    arm: String,
    project_id: String,
    rate: f64,
    passed: bool,
    by_group: BTreeMap<String, f64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Score {
    /// The integrator's contract checks (results.jsonl as written).
    Spec,
    /// The run check: the project is actually executed (runchecks.jsonl).
    Run,
}

impl Score {
    pub fn label(self) -> &'static str {
        match self {
            Score::Spec => "spec checks",
            Score::Run => "run check",
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct ArmSummary {
    pub arm: String,
    pub n: usize,
    pub gold_pass: f64,
    pub task_rate: f64,
    pub plan_recall: Option<f64>,
    pub p50_s: f64,
    pub p90_s: f64,
    pub crit_tok: f64,
    pub calls: f64,
    pub tok_out: f64,
    pub errors: usize,
    pub by_domain: BTreeMap<String, f64>,
    /// most common first failing checks, (check, count)
    pub first_fails: Vec<(String, usize)>,
    /// paired against REF_ARM on shared projects
    pub d_task_vs_ref: Option<f64>,
    pub d_wall_vs_ref: Option<f64>,
}

#[derive(Debug, Clone, Default)]
pub struct ArchRun {
    pub name: String,
    pub rows: Vec<Row>,
    pub has_runchecks: bool,
    checks: Vec<RunCheck>,
}

fn read_jsonl<T: for<'de> Deserialize<'de>>(path: &Path) -> Vec<T> {
    fs::read_to_string(path)
        .unwrap_or_default()
        .lines()
        .filter(|l| !l.trim().is_empty())
        .filter_map(|l| serde_json::from_str(l).ok())
        .collect()
}

impl ArchRun {
    pub fn load(dir: &Path) -> ArchRun {
        let checks: Vec<RunCheck> = read_jsonl(&dir.join("runchecks.jsonl"));
        ArchRun {
            name: dir.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default(),
            rows: read_jsonl(&dir.join("results.jsonl")),
            has_runchecks: !checks.is_empty(),
            checks,
        }
    }

    /// Rows under the chosen grade. Like `with_run_scores`, a row with no run check is left out.
    pub fn scored(&self, score: Score) -> Vec<Row> {
        if score == Score::Spec || !self.has_runchecks {
            return self.rows.clone();
        }
        let by_key: BTreeMap<(&str, &str), &RunCheck> =
            self.checks.iter().map(|c| ((c.arm.as_str(), c.project_id.as_str()), c)).collect();
        self.rows
            .iter()
            .filter_map(|r| {
                let c = by_key.get(&(r.arm.as_str(), r.project_id.as_str()))?;
                let mut r = r.clone();
                r.gold_pass = c.passed;
                r.gold_task_rate = c.rate;
                r.by_domain = c.by_group.clone();
                Some(r)
            })
            .collect()
    }
}

/// Every out/arch/<run>/ that has a results.jsonl, newest first.
pub fn list_arch_runs(root: &Path) -> Vec<PathBuf> {
    let mut dirs: Vec<(PathBuf, std::time::SystemTime)> = fs::read_dir(root.join("out/arch"))
        .into_iter()
        .flatten()
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.join("results.jsonl").is_file())
        .filter_map(|p| {
            let t = fs::metadata(p.join("results.jsonl")).and_then(|m| m.modified()).ok()?;
            Some((p, t))
        })
        .collect();
    dirs.sort_by(|a, b| b.1.cmp(&a.1));
    dirs.into_iter().map(|(p, _)| p).collect()
}

fn mean(xs: impl IntoIterator<Item = f64>) -> Option<f64> {
    let (mut s, mut n) = (0.0, 0usize);
    for x in xs {
        s += x;
        n += 1;
    }
    (n > 0).then(|| s / n as f64)
}

/// Same convention as slm/bench/stats.py::percentile (linear between closest ranks).
pub fn percentile(xs: &[f64], q: f64) -> f64 {
    if xs.is_empty() {
        return 0.0;
    }
    let mut v = xs.to_vec();
    v.sort_by(f64::total_cmp);
    let k = (v.len() - 1) as f64 * q / 100.0;
    let (lo, hi) = (k.floor() as usize, k.ceil() as usize);
    v[lo] + (v[hi] - v[lo]) * (k - lo as f64)
}

/// One summary per arm, best first (gold pass, then task pass).
pub fn summarize(rows: &[Row]) -> Vec<ArmSummary> {
    let mut by_arm: BTreeMap<&str, Vec<&Row>> = BTreeMap::new();
    for r in rows {
        by_arm.entry(r.arm.as_str()).or_default().push(r);
    }
    let reference: BTreeMap<&str, &Row> =
        by_arm.get(REF_ARM).map(|rs| rs.iter().map(|r| (r.project_id.as_str(), *r)).collect()).unwrap_or_default();

    let mut out: Vec<ArmSummary> = by_arm
        .iter()
        .map(|(arm, rs)| {
            let walls: Vec<f64> = rs.iter().map(|r| r.wall_s).collect();
            let mut doms: BTreeMap<String, Vec<f64>> = BTreeMap::new();
            let mut fails: BTreeMap<String, usize> = BTreeMap::new();
            for r in rs {
                for (d, v) in &r.by_domain {
                    doms.entry(d.clone()).or_default().push(*v);
                }
                if let Some(f) = r.first_fail.as_deref().filter(|_| !r.gold_pass) {
                    // "endpoint GET /api/x" and "endpoint GET /api/y" are one kind of failure
                    let key = f.split_whitespace().next().unwrap_or(f).to_string();
                    *fails.entry(key).or_default() += 1;
                }
            }
            let mut first_fails: Vec<(String, usize)> = fails.into_iter().collect();
            first_fails.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
            first_fails.truncate(4);

            let paired: Vec<(&Row, &Row)> =
                rs.iter().filter_map(|r| reference.get(r.project_id.as_str()).map(|b| (*r, *b))).collect();
            let compare = *arm != REF_ARM && paired.len() >= 2;
            ArmSummary {
                arm: arm.to_string(),
                n: rs.len(),
                gold_pass: mean(rs.iter().map(|r| r.gold_pass as u8 as f64)).unwrap_or(0.0),
                task_rate: mean(rs.iter().map(|r| r.gold_task_rate)).unwrap_or(0.0),
                plan_recall: mean(rs.iter().filter_map(|r| r.plan_recall)),
                p50_s: percentile(&walls, 50.0),
                p90_s: percentile(&walls, 90.0),
                crit_tok: mean(rs.iter().map(|r| r.crit_tok_out as f64)).unwrap_or(0.0),
                calls: mean(rs.iter().map(|r| r.calls as f64)).unwrap_or(0.0),
                tok_out: mean(rs.iter().map(|r| r.tok_out as f64)).unwrap_or(0.0),
                errors: rs.iter().filter(|r| r.error.as_deref().is_some_and(|e| !e.is_empty())).count(),
                by_domain: doms.into_iter().map(|(d, v)| (d, mean(v).unwrap_or(0.0))).collect(),
                first_fails,
                d_task_vs_ref: compare.then(|| mean(paired.iter().map(|(a, b)| a.gold_task_rate - b.gold_task_rate))).flatten(),
                d_wall_vs_ref: compare.then(|| mean(paired.iter().map(|(a, b)| a.wall_s / b.wall_s.max(1e-6)))).flatten(),
            }
        })
        .collect();
    out.sort_by(|a, b| b.gold_pass.total_cmp(&a.gold_pass).then(b.task_rate.total_cmp(&a.task_rate)).then(a.arm.cmp(&b.arm)));
    out
}

/// A small made-up results table so the Arms view has something to show in --demo.
pub fn demo_run() -> ArchRun {
    // arm, per-project (gold_pass, task_rate, wall_s, calls, tok_out, crit_tok, first_fail)
    let arms: &[(&str, f64, f64, u32, u64, u64)] = &[
        ("gold-G4", 1.00, 38.0, 12, 5200, 900),
        ("mgr-G4", 0.82, 61.0, 13, 6100, 1300),
        ("mgr-G4-repair", 0.90, 88.0, 17, 7900, 1700),
        ("mgr-G1", 0.71, 140.0, 13, 6000, 5900),
        ("mono", 0.58, 172.0, 1, 5600, 5600),
        ("base-opus", 0.93, 95.0, 1, 7400, 7400),
    ];
    let projects = ["proj-dev-invoice_tracker", "proj-dev-issue_board", "proj-dev-stock_room", "proj-test-clinic", "proj-test-library"];
    let fails = ["endpoint", "imports_resolve", "guards_wired", "tables_defined"];
    let mut rows = Vec::new();
    for (ai, (arm, rate, wall, calls, tok, crit)) in arms.iter().enumerate() {
        for (pi, p) in projects.iter().enumerate() {
            // deterministic wiggle so projects differ
            let w = ((ai * 7 + pi * 3) % 5) as f64 / 25.0 - 0.08;
            let task = (rate + w).clamp(0.0, 1.0);
            let pass = task >= 0.86;
            let mut by_domain = BTreeMap::new();
            for (di, d) in ["database", "auth", "network", "frontend"].iter().enumerate() {
                let dv = (task + ((di + pi + ai) % 3) as f64 * 0.04 - 0.04).clamp(0.0, 1.0);
                by_domain.insert(d.to_string(), dv);
            }
            rows.push(Row {
                arm: arm.to_string(),
                project_id: p.to_string(),
                template_id: Some(p.trim_start_matches("proj-dev-").trim_start_matches("proj-test-").to_string()),
                gold_pass: pass,
                gold_task_rate: task,
                first_fail: (!pass).then(|| fails[(ai + pi) % fails.len()].to_string()),
                plan_valid: arm.starts_with("mgr").then_some(true),
                plan_recall: arm.starts_with("mgr").then_some(0.92),
                n_tasks: 12,
                calls: *calls,
                tok_in: tok * 3,
                tok_out: *tok,
                wall_s: wall * (1.0 + w),
                crit_tok_out: *crit,
                crit_s: wall * 0.6,
                error: None,
                by_domain,
            });
        }
    }
    ArchRun { name: "demo".into(), rows, has_runchecks: false, checks: Vec::new() }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(arm: &str, p: &str, pass: bool, rate: f64, wall: f64) -> Row {
        Row { arm: arm.into(), project_id: p.into(), gold_pass: pass, gold_task_rate: rate, wall_s: wall, ..Default::default() }
    }

    #[test]
    fn summary_and_paired_deltas() {
        let rows = vec![
            row("mgr-G4", "a", true, 1.0, 10.0),
            row("mgr-G4", "b", false, 0.5, 20.0),
            row("mono", "a", false, 0.5, 30.0),
            row("mono", "b", false, 0.25, 40.0),
        ];
        let s = summarize(&rows);
        assert_eq!(s[0].arm, "mgr-G4");
        assert_eq!(s[0].gold_pass, 0.5);
        assert_eq!(s[0].d_task_vs_ref, None);
        let mono = &s[1];
        assert!((mono.task_rate - 0.375).abs() < 1e-9);
        assert!((mono.d_task_vs_ref.unwrap() + 0.375).abs() < 1e-9);
        assert!((mono.d_wall_vs_ref.unwrap() - 2.5).abs() < 1e-9);
        assert_eq!(percentile(&[1.0, 2.0, 3.0, 4.0], 50.0), 2.5);
    }

    #[test]
    fn runcheck_rescoring_drops_unchecked_rows() {
        let dir = std::env::temp_dir().join(format!("nova-arch-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(
            dir.join("results.jsonl"),
            "{\"arm\":\"mono\",\"project_id\":\"a\",\"gold_pass\":true,\"gold_task_rate\":1.0,\"wall_s\":1}\n\
             {\"arm\":\"mono\",\"project_id\":\"b\",\"gold_pass\":true,\"gold_task_rate\":1.0,\"wall_s\":1}\n",
        )
        .unwrap();
        fs::write(dir.join("runchecks.jsonl"), "{\"arm\":\"mono\",\"project_id\":\"a\",\"rate\":0.5,\"passed\":false,\"by_group\":{}}\n").unwrap();
        let run = ArchRun::load(&dir);
        assert!(run.has_runchecks);
        assert_eq!(run.scored(Score::Spec).len(), 2);
        let r = run.scored(Score::Run);
        assert_eq!(r.len(), 1);
        assert!(!r[0].gold_pass);
        fs::remove_dir_all(&dir).ok();
    }
}
