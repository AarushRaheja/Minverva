//! Launches `uv run slm run ...` in the repo root and streams its output back to the UI.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{Receiver, channel};
use std::thread;

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

    pub fn command_line(&self) -> String {
        format!("uv {}", self.args().join(" "))
    }
}

pub enum Msg {
    Line(String),
    /// The CLI prints `trace: <path>` as its last line; we jump to that run.
    Trace(PathBuf),
}

pub struct Job {
    pub child: Child,
    pub rx: Receiver<Msg>,
    pub opts: RunOpts,
}

impl Job {
    pub fn spawn(root: &Path, opts: RunOpts) -> std::io::Result<Job> {
        let mut child = Command::new("uv")
            .args(opts.args())
            .current_dir(root)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;
        let (tx, rx) = channel();
        if let Some(out) = child.stdout.take() {
            let tx = tx.clone();
            let root = root.to_path_buf();
            thread::spawn(move || {
                for line in BufReader::new(out).lines().map_while(Result::ok) {
                    if let Some(p) = line.strip_prefix("trace: ") {
                        let _ = tx.send(Msg::Trace(root.join(p.trim())));
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
        Ok(Job { child, rx, opts })
    }

    /// Ok(Some(code)) once the process exited.
    pub fn poll_exit(&mut self) -> Option<Option<i32>> {
        match self.child.try_wait() {
            Ok(Some(status)) => Some(status.code()),
            Ok(None) => None,
            Err(_) => Some(None),
        }
    }

    pub fn kill(&mut self) {
        let _ = self.child.kill();
    }
}
