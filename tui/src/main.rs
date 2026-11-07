//! nova-tui: a terminal UI for the NOVA manager SLM + four specialists pipeline.
//!
//!   cargo run --release -- [--root <repo>] [--trace <file.jsonl>] [--demo]
//!
//! It watches `<root>/.slm/traces/*.jsonl` (written by slm/trace.py), shows the selected run live,
//! can start `uv run slm run --project N` itself (key `r`), and compares the architecture arms
//! recorded by `python -m slm.arch run` (out/arch/<run>/results.jsonl, key `6`).

mod app;
mod arch;
mod demo;
mod runner;
mod trace;
mod ui;

use anyhow::Result;
use app::App;
use ratatui::crossterm::event::{self, Event, KeyEventKind};
use std::path::PathBuf;
use std::time::{Duration, Instant};

const TICK: Duration = Duration::from_millis(120);

struct Args {
    root: PathBuf,
    trace: Option<PathBuf>,
    demo: bool,
}

fn usage() -> ! {
    println!(
        "nova-tui: watch and drive the NOVA SLM pipeline\n\n\
         usage: nova-tui [--root <repo root>] [--trace <trace.jsonl>] [--demo]\n\n\
         --root   repo root holding .slm/traces and out/deliverable (default: auto-detect)\n\
         --trace  open one trace file instead of the newest\n\
         --demo   replay a synthetic run (no python needed)"
    );
    std::process::exit(0)
}

/// Walk up from cwd until we find the repo (pyproject.toml next to slm/).
fn find_root() -> PathBuf {
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for dir in cwd.ancestors() {
        if dir.join("pyproject.toml").exists() && dir.join("slm").is_dir() {
            return dir.to_path_buf();
        }
    }
    cwd
}

fn parse_args() -> Args {
    let mut args = Args { root: PathBuf::new(), trace: None, demo: false };
    let mut root = None;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--root" => root = it.next().map(PathBuf::from),
            "--trace" => args.trace = it.next().map(PathBuf::from),
            "--demo" => args.demo = true,
            "-h" | "--help" => usage(),
            other => {
                eprintln!("unknown argument {other:?}");
                usage()
            }
        }
    }
    args.root = root.unwrap_or_else(find_root);
    args.root = args.root.canonicalize().unwrap_or(args.root);
    if let Some(t) = &args.trace {
        args.trace = Some(t.canonicalize().unwrap_or_else(|_| t.clone()));
    }
    args
}

fn main() -> Result<()> {
    let args = parse_args();
    let mut app = App::new(args.root, args.trace, args.demo);
    let mut terminal = ratatui::init();
    let res = run(&mut terminal, &mut app);
    ratatui::restore();
    if let Some(job) = &mut app.job {
        job.kill();
    }
    res
}

fn run(terminal: &mut ratatui::DefaultTerminal, app: &mut App) -> Result<()> {
    let mut last = Instant::now();
    while !app.quit {
        terminal.draw(|f| ui::draw(f, app))?;
        let timeout = TICK.saturating_sub(last.elapsed());
        if event::poll(timeout)? {
            if let Event::Key(k) = event::read()? {
                if k.kind == KeyEventKind::Press {
                    app.on_key(k);
                }
            }
        }
        if last.elapsed() >= TICK {
            app.refresh();
            last = Instant::now();
        }
    }
    Ok(())
}
