//! Gantt chart of every task from t_start/t_end, plus how many specialists ran at once.
//! This is the "faster than an LLM" picture: parallel levels show up as stacked bars.

use super::theme::*;
use super::{clip, panel};
use crate::app::{App, Focus};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Paragraph, Sparkline};

const LABEL: usize = 22;

pub fn draw(f: &mut Frame, area: Rect, app: &App) {
    let block = panel("Timeline", app.focus == Focus::Main);
    let inner = block.inner(area);
    f.render_widget(block, area);
    let [axis, bars, spark_label, spark] = Layout::vertical([
        Constraint::Length(1),
        Constraint::Min(3),
        Constraint::Length(1),
        Constraint::Length(4),
    ])
    .areas(inner);

    let Some((t0, t1)) = app.run.span() else {
        f.render_widget(Paragraph::new(Span::styled("no timing data yet", dim())), bars);
        return;
    };
    // While a run is live, stretch the axis to "now" so bars grow left to right.
    let t1 = if app.run.final_event().is_none() { t1.max(t0 + 1.0) } else { t1 };
    let width = (inner.width as usize).saturating_sub(LABEL + 2).max(10);
    let scale = |t: f64| (((t - t0) / (t1 - t0)) * width as f64).round().clamp(0.0, width as f64) as usize;

    // axis
    let mut ticks = vec![' '; width + 1];
    let mut tick_line = String::new();
    for k in 0..=4 {
        let x = k * width / 4;
        ticks[x.min(width)] = '┼';
    }
    let labels: Vec<String> = (0..=4).map(|k| format!("{:.1}s", (t1 - t0) * k as f64 / 4.0)).collect();
    tick_line.push_str(&" ".repeat(LABEL));
    let mut pos = 0usize;
    for (k, l) in labels.iter().enumerate() {
        let x = k * width / 4;
        let x = x.saturating_sub(if k == 4 { l.len() } else { 0 });
        if x >= pos {
            tick_line.push_str(&" ".repeat(x - pos));
            tick_line.push_str(l);
            pos = x + l.len();
        }
    }
    f.render_widget(Paragraph::new(Span::styled(tick_line, dim())), axis);

    let tasks = app.run.tasks();
    let mut lines = Vec::new();
    // manager / plan row
    if let Some(p) = app.run.plan() {
        let end = scale(p.ts);
        lines.push(bar_line("manager plan", domain_color("manager"), 0, end.max(1), width, false, false));
    }
    let now = app.run.events.iter().map(|e| e.ts).fold(t0, f64::max);
    for (i, t) in tasks.iter().enumerate() {
        let s = scale(t.t_start.unwrap_or(t0));
        let e = scale(t.t_end.unwrap_or(now)).max(s + 1);
        lines.push(bar_line(
            &t.id,
            domain_color(&t.domain),
            s,
            e,
            width,
            i == app.task_sel,
            t.status == crate::trace::Status::Fail,
        ));
    }
    if let Some(fin) = app.run.final_event() {
        let x = scale(fin.t_end.unwrap_or(fin.ts)).min(width);
        let color = if app.run.passed() == Some(true) { OK } else { FAIL };
        let verdict = clip(&app.run.verdict(), 40);
        let mut spans = vec![Span::styled(format!("{:<LABEL$}", "integrator"), dim())];
        // label on the left of the marker so it never runs off the edge
        let pad = x.saturating_sub(verdict.chars().count() + 2);
        spans.push(Span::raw(" ".repeat(pad)));
        spans.push(Span::styled(format!("{verdict} "), Style::new().fg(color)));
        spans.push(Span::styled("◆", Style::new().fg(color).bold()));
        lines.push(Line::from(spans));
    }
    // keep the selected task visible
    let h = bars.height as usize;
    let sel_line = app.task_sel + 1;
    let scroll = sel_line.saturating_sub(h.saturating_sub(1));
    f.render_widget(Paragraph::new(lines).scroll((scroll as u16, 0)), bars);

    // concurrency: specialists in flight per column
    let mut conc = vec![0u64; width];
    for t in &tasks {
        let s = scale(t.t_start.unwrap_or(t0));
        let e = scale(t.t_end.unwrap_or(now)).max(s + 1).min(width);
        for c in conc.iter_mut().take(e).skip(s) {
            *c += 1;
        }
    }
    let peak = conc.iter().copied().max().unwrap_or(0);
    let serial: f64 = tasks.iter().filter_map(|t| t.secs()).sum();
    let wall = app.run.wall_secs();
    let speedup = if wall > 0.0 { serial / wall } else { 0.0 };
    f.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled(format!("{:<LABEL$}", "in flight"), dim()),
            Span::styled(format!("peak {peak} specialists"), title()),
            Span::styled(format!("   serial sum {serial:.2}s  wall {wall:.2}s  "), dim()),
            Span::styled(format!("{speedup:.2}x from parallel dispatch"), Style::new().fg(OK).bold()),
        ])),
        spark_label,
    );
    let [_, sp] = Layout::horizontal([Constraint::Length(LABEL as u16), Constraint::Min(1)]).areas(spark);
    f.render_widget(Sparkline::default().data(&conc).style(Style::new().fg(BG_ACCENT)), sp);
}

fn bar_line(label: &str, color: Color, s: usize, e: usize, width: usize, selected: bool, failed: bool) -> Line<'static> {
    let lab_style = if selected { Style::new().fg(TEXT).bg(Color::Rgb(45, 40, 80)).bold() } else { Style::new().fg(TEXT) };
    let e = e.min(width);
    let bar_color = if failed { FAIL } else { color };
    Line::from(vec![
        Span::styled(format!("{:<LABEL$}", clip(label, LABEL - 1)), lab_style),
        Span::styled("·".repeat(s), Style::new().fg(Color::Rgb(50, 50, 65))),
        Span::styled("█".repeat(e.saturating_sub(s)), Style::new().fg(bar_color)),
        Span::styled(if failed { " ✘" } else { "" }, Style::new().fg(FAIL)),
    ])
}
