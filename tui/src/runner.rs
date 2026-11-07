//! Launches `uv run minerva build ...` (or the older `uv run slm run ...`) in the repo root and streams its output.
//!
//! The job gets its own process group, so stopping it reaches uv, python and everything they started (the audit's
//! node and Postgres processes, Modal's client). Stop is SIGINT first, so `minerva build` unwinds: its `app.run()`
//! contexts close (ephemeral Modal apps stop) and it writes a `run_end` "stopped" event. It escalates to SIGTERM, then
//! SIGKILL, if the group is still alive.

use std::io::{BufRead, BufReader};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{Receiver, channel};
use std::thread;
use std::time::{Duration, Instant};

/// Options for the older four-specialist run (`slm run`).
#[derive(Debug, Clone)]
pub struct RunOpts {
    pub project: u32,
    pub split: String,
    pub gold: bool,
    pub parallel: bool,
}

impl Default for RunOpts {
    fn default() -> Self {
        RunOpts { project: 0, split: "dev".into(), gold: true, parallel: true }
    }
}

impl RunOpts {
    pub fn args(&self) -> Vec<String> {
        let mut a = vec![
            "run".into(),
            "slm".into(),
            "run".into(),
            "--project".into(),
            self.project.to_string(),
            "--split".into(),
            self.split.clone(),
        ];
        a.push(if self.gold { "--gold" } else { "--no-gold" }.into());
        a.push(if self.parallel { "--parallel" } else { "--no-parallel" }.into());
        a
    }
}

/// Options for `minerva build`. `out` set means: resume that run directory.
#[derive(Debug, Clone, PartialEq)]
pub struct BuildOpts {
    pub what: String,
    pub look: String,
    pub engine: String,
    pub architect: String,
    pub max_repairs: u32,
    pub budget_usd: f64,
    pub out: Option<PathBuf>,
}

impl BuildOpts {
    pub fn args(&self) -> Vec<String> {
        let mut a: Vec<String> = vec!["run".into(), "minerva".into(), "build".into(), self.what.clone()];
        if !self.look.trim().is_empty() {
            a.extend(["--look".into(), self.look.clone()]);
        }
        a.extend([
            "--engine".into(),
            self.engine.clone(),
            "--architect".into(),
            self.architect.clone(),
            "--max-repairs".into(),
            self.max_repairs.to_string(),
            "--budget-usd".into(),
            format!("{:.2}", self.budget_usd),
        ]);
        if let Some(out) = &self.out {
            a.extend(["--out".into(), out.display().to_string()]);
        }
        a
    }
}

#[derive(Debug, Clone)]
pub enum JobKind {
    Slm(RunOpts),
    Build(BuildOpts),
}

impl JobKind {
    pub fn args(&self) -> Vec<String> {
        match self {
            JobKind::Slm(o) => o.args(),
            JobKind::Build(o) => o.args(),
        }
    }

    /// For display: `uv run minerva build "Track invoices" --engine offline ...`
    pub fn command_line(&self) -> String {
        let quoted: Vec<String> = self
            .args()
            .into_iter()
            .map(|a| if a.contains(' ') || a.is_empty() { format!("{a:?}") } else { a })
            .collect();
        format!("uv {}", quoted.join(" "))
    }
}

pub enum Msg {
    Line(String),
    /// `slm run` prints `trace: <path>` as its last line.
    Trace(PathBuf),
    /// `minerva build` prints `run: <dir>` as its first line.
    RunDir(PathBuf),
}

pub struct Job {
    pub child: Child,
    pub rx: Receiver<Msg>,
    pub kind: JobKind,
    /// when stop was asked for, and the signal last sent
    pub stopping: Option<(Instant, &'static str)>,
}

impl Job {
    pub fn spawn(root: &Path, kind: JobKind) -> std::io::Result<Job> {
        let mut child = Command::new("uv")
            .args(kind.args())
            .current_dir(root)
            .env("PYTHONUNBUFFERED", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .process_group(0)
            .spawn()?;
        let (tx, rx) = channel();
        if let Some(out) = child.stdout.take() {
            let tx = tx.clone();
            let root = root.to_path_buf();
            thread::spawn(move || {
                for line in BufReader::new(out).lines().map_while(Result::ok) {
                    if let Some(p) = line.strip_prefix("trace: ") {
                        let _ = tx.send(Msg::Trace(root.join(p.trim())));
                    } else if let Some(p) = line.strip_prefix("run: ") {
                        let _ = tx.send(Msg::RunDir(root.join(p.trim())));
                    }
                    let _ = tx.send(Msg::Line(line));
                }
            });
        }
        if let Some(err) = child.stderr.take() {
            let tx = tx.clone();
            thread::spawn(move || {
                for line in BufReader::new(err).lines().map_while(Result::ok) {
                    let _ = tx.send(Msg::Line(line));
                }
            });
        }
        Ok(Job { child, rx, kind, stopping: None })
    }

    /// Some(code) once the process exited (None inside: killed by a signal).
    pub fn poll_exit(&mut self) -> Option<Option<i32>> {
        match self.child.try_wait() {
            Ok(Some(status)) => Some(status.code()),
            Ok(None) => None,
            Err(_) => Some(None),
        }
    }

    fn signal_group(&self, sig: &str) {
        // The child leads its own process group (process_group(0)), so -pid names the whole group.
        let _ = Command::new("kill")
            .args([format!("-{sig}"), "--".into(), format!("-{}", self.child.id())])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }

    /// Ask the job to stop: SIGINT to its whole group. Call `escalate` on every tick afterwards.
    pub fn stop(&mut self) {
        if self.stopping.is_none() {
            self.signal_group("INT");
            self.stopping = Some((Instant::now(), "INT"));
        }
    }

    /// SIGTERM after 20 s, SIGKILL after 40 s, if the group is still running.
    pub fn escalate(&mut self) {
        let Some((since, sent)) = self.stopping else { return };
        let next = match sent {
            "INT" if since.elapsed() > Duration::from_secs(20) => "TERM",
            "TERM" if since.elapsed() > Duration::from_secs(40) => "KILL",
            _ => return,
        };
        self.signal_group(next);
        self.stopping = Some((since, next));
    }

    /// After a stopped job's leader exited: anything left in its group (a child that ignores Ctrl-C) gets SIGTERM.
    /// Only after a stop, so a finished job's group id is never signalled once it could have been reused.
    pub fn reap_group(&self) {
        if self.stopping.is_some() {
            self.signal_group("TERM");
        }
    }

    /// Stop and wait up to `wait` for the group to exit, then kill it. For quitting the TUI.
    pub fn stop_and_wait(&mut self, wait: Duration) {
        self.stop();
        let start = Instant::now();
        while start.elapsed() < wait {
            if self.poll_exit().is_some() {
                self.reap_group();
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        self.signal_group("KILL");
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn opts() -> BuildOpts {
        BuildOpts {
            what: "Track invoices".into(),
            look: "Warm, editorial".into(),
            engine: "offline".into(),
            architect: "thinking".into(),
            max_repairs: 1,
            budget_usd: 3.0,
            out: None,
        }
    }

    #[test]
    fn build_args_carry_every_option() {
        let a = opts().args();
        assert_eq!(&a[..4], ["run", "minerva", "build", "Track invoices"]);
        let joined = a.join(" ");
        for part in ["--look Warm, editorial", "--engine offline", "--architect thinking", "--max-repairs 1", "--budget-usd 3.00"] {
            assert!(joined.contains(part), "{part} missing from {joined}");
        }
        assert!(!joined.contains("--out"));
        let resumed = BuildOpts { look: String::new(), out: Some(PathBuf::from("runs/x")), ..opts() };
        let joined = resumed.args().join(" ");
        assert!(joined.ends_with("--out runs/x") && !joined.contains("--look"));
        assert!(JobKind::Build(opts()).command_line().starts_with("uv run minerva build \"Track invoices\""));
    }

    #[test]
    fn slm_args_are_unchanged() {
        assert_eq!(
            RunOpts::default().args().join(" "),
            "run slm run --project 0 --split dev --gold --parallel"
        );
    }

    /// stop() reaches the whole process group: a grandchild started by the job is gone afterwards.
    #[test]
    fn stop_reaches_the_process_group() {
        let mut child = Command::new("sh")
            .args(["-c", "sleep 30 & echo $!; wait"])
            .stdout(Stdio::piped())
            .process_group(0)
            .spawn()
            .unwrap();
        let mut line = String::new();
        BufReader::new(child.stdout.take().unwrap()).read_line(&mut line).unwrap();
        let grandchild: u32 = line.trim().parse().unwrap();
        let (_tx, rx) = channel();
        let mut job = Job { child, rx, kind: JobKind::Slm(RunOpts::default()), stopping: None };
        job.stop_and_wait(Duration::from_secs(5));
        thread::sleep(Duration::from_millis(200));
        let alive = Command::new("kill").args(["-0", &grandchild.to_string()]).status().unwrap().success();
        assert!(!alive, "the grandchild survived the stop");
    }
}
