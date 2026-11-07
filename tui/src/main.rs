//! nova-tui: the terminal UI for Minerva builds and the NOVA manager SLM + four specialists pipeline.
//!
//!   cargo run --release -- [--root <repo>] [--build <runs/dir>] [--trace <file.jsonl>] [--demo]
//!
//! Key `r` starts `uv run minerva build "<what>" --look "<how>"` (offline, or real models on Modal after a cost and
//! privacy confirmation) and follows it live from its run directory's `events.jsonl`. It also watches
//! `<root>/.slm/traces/*.jsonl` (`slm run`, key `T`) and compares the architecture arms recorded by
//! `python -m slm.arch run` (out/arch/<run>/results.jsonl, view 6).

mod app;
mod arch;
mod build;
mod demo;
mod form;
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
    build: Option<PathBuf>,
    demo: bool,
    /// `--print <view|all>`: render once as plain text and exit (CI, agents, bug reports)
    print: Option<String>,
    /// `--size WxH` for --print
    size: Option<(u16, u16)>,
}

fn usage() -> ! {
    println!(
        "nova-tui: watch and drive the NOVA SLM pipeline\n\n\
         usage: nova-tui [--root <repo root>] [--build <runs/dir>] [--trace <trace.jsonl>] [--demo] [--print <view|all>]\n\n\
         --root   repo root holding runs/, .slm/traces and out/ (default: auto-detect)\n\
         --build  open one Minerva run directory instead of the newest run\n\
         --trace  open one trace file instead of the newest\n\
         --demo   replay a synthetic run (no python needed)\n\
         --print  render pipeline|tasks|timeline|deliverable|log|arms|report|all as text and exit\n\
         --size   frame size for --print, e.g. 80x24 (default: 150x44 or the terminal, if larger)"
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
    let mut args = Args { root: PathBuf::new(), trace: None, build: None, demo: false, print: None, size: None };
    let mut root = None;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--root" => root = it.next().map(PathBuf::from),
            "--trace" => args.trace = it.next().map(PathBuf::from),
            "--build" => args.build = it.next().map(PathBuf::from),
            "--demo" => args.demo = true,
            "--print" => args.print = Some(it.next().unwrap_or_else(|| "all".into())),
            "--size" => {
                args.size = it.next().and_then(|v| {
                    let (w, h) = v.split_once('x')?;
                    Some((w.parse().ok()?, h.parse().ok()?))
                })
            }
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
    if let Some(b) = &args.build {
        args.build = Some(b.canonicalize().unwrap_or_else(|_| b.clone()));
    }
    args
}

fn main() -> Result<()> {
    let args = parse_args();
    let mut app = App::new(args.root, args.build.or(args.trace), args.demo);
    if let Some(view) = &args.print {
        if let Some(d) = &mut app.demo {
            d.skip(60.0); // show the finished demo run, not frame zero
        }
        app.refresh();
        return print_views(&mut app, view, args.size);
    }
    let mut terminal = ratatui::init();
    let res = run(&mut terminal, &mut app);
    ratatui::restore();
    if let Some(job) = &mut app.job {
        eprintln!("stopping the running build (Ctrl-C to it, then up to 15 s to save what finished)...");
        job.stop_and_wait(Duration::from_secs(15));
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

/// Render views to stdout without a terminal, e.g. `nova-tui --print arms`.
fn print_views(app: &mut App, view: &str, size: Option<(u16, u16)>) -> Result<()> {
    use ratatui::{Terminal, backend::TestBackend};
    let tabs: Vec<app::Tab> = app::Tab::ALL
        .into_iter()
        .filter(|t| view == "all" || t.title().eq_ignore_ascii_case(view))
        .collect();
    if tabs.is_empty() {
        anyhow::bail!("unknown view {view:?}; use pipeline, tasks, timeline, deliverable, log, arms, report or all");
    }
    // at least 150x44 so a report is readable; larger if the terminal running it is larger
    let (w, h) = size.unwrap_or_else(|| crossterm_size().map(|(w, h)| (w.max(150), h.max(44))).unwrap_or((150, 44)));
    use std::io::Write;
    let mut out = std::io::stdout().lock();
    for tab in tabs {
        app.tab = tab;
        let mut t = Terminal::new(TestBackend::new(w, h))?;
        t.draw(|f| ui::draw(f, app))?;
        let buf = t.backend().buffer();
        for y in 0..h {
            let line: String = (0..w).map(|x| buf[(x, y)].symbol()).collect();
            if writeln!(out, "{}", line.trim_end()).is_err() {
                return Ok(()); // reader went away (`| head`), not an error
            }
        }
    }
    Ok(())
}

fn crossterm_size() -> Option<(u16, u16)> {
    ratatui::crossterm::terminal::size().ok()
}
