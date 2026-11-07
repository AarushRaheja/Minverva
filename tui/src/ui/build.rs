//! Views for a Minerva build (a `runs/<id>/` folder): Pipeline, Tasks, Timeline and Report.
//! Deliverable and Log are shared with traces (deliverable.rs, log.rs).

use super::theme::*;
use super::{clip, panel};
use crate::app::{App, Focus};
use crate::build::{BackendTask, Build, Round, StageRow, State};
use crate::trace::Status;
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Cell, Gauge, Paragraph, Row, Table, TableState, Wrap};

const SELECTED: Color = Color::Rgb(45, 40, 80);

pub fn now() -> f64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}

pub fn secs(s: Option<f64>) -> String {
    match s.map(|s| s.max(0.0)) {
        Some(s) if s >= 60.0 => format!("{}m{:02}s", (s / 60.0) as u64, (s % 60.0) as u64),
        Some(s) if s >= 10.0 => format!("{s:.0}s"),
        Some(s) => format!("{s:.1}s"),
        None => String::new(),
    }
}

fn usd(row: &StageRow) -> Span<'static> {
    match (row.usd, row.estimate, row.status) {
        (Some(u), _, _) if u > 0.0 => Span::styled(format!("${u:.2}"), Style::new().fg(TEXT)),
        (_, Some(e), Status::Running) if e > 0.0 => Span::styled(format!("~${e:.2}"), Style::new().fg(RUN)),
        _ => Span::styled("", dim()),
    }
}

fn stage_color(stage: &str) -> Color {
    match stage {
        "plan" => domain_color("manager"),
        "backend" | "seams" | "preflight" => domain_color("network"),
        "intent" | "architect" | "critic" => domain_color("frontend"),
        "audit" | "verify" => domain_color("database"),
        _ => DIM,
    }
}

fn status_span(row: &StageRow, app: &App) -> Span<'static> {
    let (icon, color) = match row.status {
        Status::Running => (app.spinner(), RUN),
        s => (status_icon(s), status_color(s)),
    };
    Span::styled(format!("{icon} "), Style::new().fg(color))
}

/// Where a build's data goes, from the engines list when it is loaded, else from the engine name.
pub fn data_label(app: &App, engine: &str) -> String {
    if let Some(e) = app.engine_list().iter().find(|e| e.name == engine) {
        return e.data_goes_to.split(':').next().unwrap_or(&e.data_goes_to).to_string();
    }
    match engine {
        "offline" => "nowhere".into(),
        "modal" => "your Modal account".into(),
        other => other.to_string(),
    }
}

pub fn state_style(status: Status) -> Style {
    match status {
        Status::Ok => Style::new().fg(OK).reversed().bold(),
        Status::Fail => Style::new().fg(FAIL).reversed().bold(),
        Status::Running => Style::new().fg(RUN).reversed().bold(),
        Status::Pending => Style::new().fg(DIM).reversed(),
    }
}

// ---------------------------------------------------------------- Pipeline

pub fn draw_pipeline(f: &mut Frame, area: Rect, app: &App, b: &Build) {
    let wide = area.width >= 110;
    let [brief, body] = Layout::vertical([Constraint::Length(4), Constraint::Min(6)]).areas(area);
    draw_brief(f, brief, b);
    let (stages_area, card_area) = if wide {
        let [s, c] = Layout::horizontal([Constraint::Min(60), Constraint::Length(38)]).areas(body);
        (s, Some(c))
    } else {
        (body, None)
    };
    draw_stage_table(f, stages_area, app, b);
    if let Some(c) = card_area {
        draw_run_card(f, c, app, b);
    }
}

fn draw_brief(f: &mut Frame, area: Rect, b: &Build) {
    let w = area.width.saturating_sub(12) as usize;
    let look = if b.meta.look.is_empty() { "(default: clean product UI)".to_string() } else { b.meta.look.clone() };
    let lines = vec![
        Line::from(vec![Span::styled(" what  ", key()), Span::styled(clip(&b.meta.brief, w), Style::new().fg(TEXT))]),
        Line::from(vec![Span::styled(" look  ", Style::new().fg(domain_color("frontend")).bold()), Span::styled(clip(&look, w), dim())]),
    ];
    let title = b.plan_name.clone().map(|n| format!("Brief → {n}")).unwrap_or_else(|| "Brief".into());
    f.render_widget(Paragraph::new(lines).block(panel(&title, false)), area);
}

fn draw_stage_table(f: &mut Frame, area: Rect, app: &App, b: &Build) {
    let rows_data = b.stages();
    let narrow = area.width < 70;
    let detail_w = area.width.saturating_sub(if narrow { 24 } else { 40 }) as usize;
    let rows: Vec<Row> = rows_data
        .iter()
        .map(|r| {
            let label = Span::styled(r.label(), Style::new().fg(stage_color(&r.stage)).bold());
            let state = match (r.status, r.cached) {
                (Status::Ok, true) => Span::styled("reused", dim()),
                (Status::Ok, false) => Span::styled("ok", Style::new().fg(OK)),
                (Status::Fail, _) => Span::styled("failed", Style::new().fg(FAIL)),
                (Status::Running, _) => Span::styled("running", Style::new().fg(RUN)),
                (Status::Pending, _) => Span::styled("·", dim()),
            };
            let time = match r.status {
                Status::Running => secs(r.t_start.map(|t| (now() - t).max(0.0))),
                _ if r.cached => String::new(),
                _ => secs(r.seconds),
            };
            let detail = clip(&r.detail, detail_w.max(8));
            if narrow {
                Row::new(vec![
                    Cell::from(Line::from(vec![status_span(r, app), label])),
                    Cell::from(Span::styled(time, dim())),
                    Cell::from(Span::styled(detail, dim())),
                ])
            } else {
                Row::new(vec![
                    Cell::from(Line::from(vec![status_span(r, app), label])),
                    Cell::from(state),
                    Cell::from(Span::styled(time, dim())),
                    Cell::from(usd(r)),
                    Cell::from(Span::styled(detail, dim())),
                ])
            }
        })
        .collect();
    let widths: Vec<Constraint> = if narrow {
        vec![Constraint::Length(15), Constraint::Length(7), Constraint::Min(8)]
    } else {
        vec![Constraint::Length(16), Constraint::Length(8), Constraint::Length(7), Constraint::Length(7), Constraint::Min(10)]
    };
    let header = if narrow {
        Row::new(vec!["stage", "time", "detail"])
    } else {
        Row::new(vec!["stage", "state", "time", "$", "detail"])
    }
    .style(dim());
    let done = rows_data.iter().filter(|r| matches!(r.status, Status::Ok | Status::Fail)).count();
    let title = format!("Stages {done}/{}", rows_data.len());
    let table = Table::new(rows, widths)
        .header(header)
        .block(panel(&title, app.focus == Focus::Main))
        .row_highlight_style(Style::new().bg(SELECTED));
    let mut st = TableState::default().with_selected(Some(app.task_sel.min(rows_data.len().saturating_sub(1))));
    f.render_stateful_widget(table, area, &mut st);
}

fn draw_run_card(f: &mut Frame, area: Rect, app: &App, b: &Build) {
    let [info, gauge, rest] = Layout::vertical([Constraint::Length(10), Constraint::Length(3), Constraint::Min(3)]).areas(area);
    let engine = b.engine();
    let (label, status) = b.label();
    let lines = vec![
        Line::from(vec![Span::styled(format!(" {label} "), state_style(status))]),
        Line::default(),
        Line::from(vec![Span::styled("engine   ", dim()), Span::styled(engine.clone(), theme_title())]),
        Line::from(vec![Span::styled("started  ", dim()), Span::raw(clip(&b.meta.started_at.replace('T', " "), 19))]),
        Line::from(vec![Span::styled("data to  ", dim()), Span::styled(data_label(app, &engine), Style::new().fg(TEXT))]),
        Line::from(vec![Span::styled("elapsed  ", dim()), Span::raw(secs(Some(b.wall_secs(now()))))]),
        Line::from(vec![
            Span::styled("entities ", dim()),
            Span::raw(clip(&entities(b), area.width.saturating_sub(12) as usize)),
        ]),
        Line::from(vec![Span::styled("rounds   ", dim()), Span::raw(b.rounds.len().to_string())]),
    ];
    f.render_widget(Paragraph::new(lines).block(panel("Run", false)), info);
    let budget = b.budget();
    let ratio = if budget > 0.0 { (b.spent() / budget).clamp(0.0, 1.0) } else { 0.0 };
    let g = Gauge::default()
        .block(panel("Spend", false))
        .gauge_style(Style::new().fg(if ratio > 0.8 { FAIL } else { OK }).bg(Color::Rgb(35, 35, 50)))
        .ratio(ratio)
        .label(format!("${:.2} of ${:.2}", b.spent(), budget));
    f.render_widget(g, gauge);
    let detail = b.detail();
    let text = if detail.is_empty() { "—".to_string() } else { detail };
    f.render_widget(Paragraph::new(text).wrap(Wrap { trim: true }).style(dim()).block(panel("Detail", false)), rest);
}

fn theme_title() -> Style {
    super::theme::title()
}

fn entities(b: &Build) -> String {
    b.status
        .as_ref()
        .and_then(|s| s["entities"].as_array())
        .map(|a| a.iter().filter_map(|v| v.as_str()).collect::<Vec<_>>().join(", "))
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "—".into())
}

// ---------------------------------------------------------------- Tasks

pub enum TaskItem<'a> {
    Backend(&'a BackendTask),
    Round(&'a Round),
    Journey(&'a str, bool),
}

/// Rows of the Tasks view: the backend tasks the specialists wrote, the frontend rounds, the journey checks.
pub fn task_rows(b: &Build) -> Vec<TaskItem<'_>> {
    let mut rows: Vec<TaskItem> = b.tasks.iter().map(TaskItem::Backend).collect();
    rows.extend(b.rounds.iter().map(TaskItem::Round));
    rows.extend(b.journey.iter().map(|(id, ok)| TaskItem::Journey(id.as_str(), *ok)));
    rows
}

pub fn draw_tasks(f: &mut Frame, area: Rect, app: &App, b: &Build) {
    let [table_area, detail_area] = Layout::vertical([Constraint::Min(6), Constraint::Length(8)]).areas(area);
    let items = task_rows(b);
    if items.is_empty() {
        let msg = match b.state() {
            State::Running(stage) => format!("nothing written yet: the build is at {stage}"),
            _ => "no backend tasks, rounds or journey checks recorded for this build".into(),
        };
        f.render_widget(Paragraph::new(Span::styled(msg, dim())).block(panel("Tasks", app.focus == Focus::Main)), area);
        return;
    }
    let rows: Vec<Row> = items
        .iter()
        .map(|it| match it {
            TaskItem::Backend(t) => Row::new(vec![
                Cell::from(Span::styled(format!("{} ", status_icon(Status::Ok)), Style::new().fg(OK))),
                Cell::from(t.id.clone()),
                Cell::from(Span::styled(format!("{} {}", domain_icon(&t.domain), t.domain), Style::new().fg(domain_color(&t.domain)))),
                Cell::from(Span::styled(t.files.join(", "), dim())),
            ]),
            TaskItem::Round(r) => {
                let ok = r.audit_pass == Some(true);
                let (icon, color) = if ok { ("✔", OK) } else { ("✘", FAIL) };
                Row::new(vec![
                    Cell::from(Span::styled(format!("{icon} "), Style::new().fg(color))),
                    Cell::from(format!("round {}", r.round)),
                    Cell::from(Span::styled("▣ frontend", Style::new().fg(domain_color("frontend")))),
                    Cell::from(Span::styled(round_summary(r), dim())),
                ])
            }
            TaskItem::Journey(id, ok) => {
                let (icon, color) = if *ok { ("✔", OK) } else { ("✘", FAIL) };
                Row::new(vec![
                    Cell::from(Span::styled(format!("{icon} "), Style::new().fg(color))),
                    Cell::from(id.to_string()),
                    Cell::from(Span::styled("◎ verify", Style::new().fg(domain_color("database")))),
                    Cell::from(Span::styled(if *ok { "sign-up journey passed" } else { "sign-up journey failed" }, dim())),
                ])
            }
        })
        .collect();
    let sel = app.task_sel.min(items.len() - 1);
    let table = Table::new(rows, [Constraint::Length(2), Constraint::Length(16), Constraint::Length(12), Constraint::Min(10)])
        .header(Row::new(vec!["", "task", "domain", "output"]).style(dim()))
        .block(panel(&format!("Tasks ({})", items.len()), app.focus == Focus::Main))
        .row_highlight_style(Style::new().bg(SELECTED));
    let mut st = TableState::default().with_selected(Some(sel));
    f.render_stateful_widget(table, table_area, &mut st);

    let w = detail_area.width.saturating_sub(4) as usize;
    let lines: Vec<Line> = match &items[sel] {
        TaskItem::Backend(t) => {
            let mut l = vec![Line::from(vec![
                Span::styled(format!("{} ", t.id), theme_title()),
                Span::styled(format!("written by spec-{}", t.domain), dim()),
            ])];
            if let Some((_, s)) = b.domain_summaries.iter().find(|(d, _)| d == &t.domain) {
                l.push(Line::from(Span::styled(clip(s, w), Style::new().fg(TEXT))));
            }
            l.extend(t.files.iter().map(|p| Line::from(Span::styled(format!("  {p}"), dim()))));
            l
        }
        TaskItem::Round(r) => {
            let mut l = vec![Line::from(vec![
                Span::styled(format!("round {} ", r.round), theme_title()),
                Span::styled(format!("{} · {} tokens", secs(r.seconds), r.output_tokens.unwrap_or(0)), dim()),
            ])];
            if let Some(e) = &r.generation_error {
                l.push(Line::from(Span::styled(clip(&format!("generation: {e}"), w), Style::new().fg(FAIL))));
            }
            l.extend(r.build_errors.iter().map(|e| Line::from(Span::styled(clip(e, w), Style::new().fg(FAIL)))));
            if !r.failed_gates.is_empty() {
                l.push(Line::from(Span::styled(clip(&format!("failed gates: {}", r.failed_gates.join(", ")), w), dim())));
            }
            if !r.failed_tests.is_empty() {
                l.push(Line::from(Span::styled(clip(&format!("failed tests: {}", r.failed_tests.join(", ")), w), dim())));
            }
            if let Some(c) = &r.critic {
                l.push(Line::from(Span::styled(format!("critic: {c}"), dim())));
            }
            l
        }
        TaskItem::Journey(id, ok) => vec![
            Line::from(Span::styled(id.to_string(), theme_title())),
            Line::from(Span::styled(
                if *ok {
                    "sign up, create a row, reload, sign out, sign back in, find the row: passed"
                } else {
                    "the sign-up journey failed: see verify/evidence.json"
                },
                dim(),
            )),
        ],
    };
    f.render_widget(Paragraph::new(lines).block(panel("Selected", false)), detail_area);
}

fn round_summary(r: &Round) -> String {
    if let Some(e) = &r.generation_error {
        return format!("no usable source: {e}");
    }
    match r.audit_pass {
        Some(true) => format!("audit passed{}", r.critic.as_ref().map(|c| format!(", critic: {c}")).unwrap_or_default()),
        Some(false) if !r.build_errors.is_empty() => format!("the build failed: {}", r.build_errors[0]),
        Some(false) => format!("audit failed: {}", r.failed_gates.join(", ")),
        None => "not audited yet".into(),
    }
}

// ---------------------------------------------------------------- Timeline

pub fn draw_timeline(f: &mut Frame, area: Rect, app: &App, b: &Build) {
    let block = panel("Timeline", app.focus == Focus::Main);
    let inner = block.inner(area);
    f.render_widget(block, area);
    let rows = b.stages();
    let Some(t0) = b.events.first().map(|e| e.ts) else {
        f.render_widget(Paragraph::new(Span::styled("no events yet (runs from before events.jsonl have no timeline)", dim())), inner);
        return;
    };
    let span = b.wall_secs(now()).max(1.0);
    let [axis, bars, summary] = Layout::vertical([Constraint::Length(1), Constraint::Min(3), Constraint::Length(2)]).areas(inner);
    const LABEL: u16 = 16;
    const RIGHT: u16 = 14;
    let width = bars.width.saturating_sub(LABEL + RIGHT + 2).max(4) as f64;
    let ticks = format!("{:<w$}{}", format!("0s"), secs(Some(span)), w = (LABEL as usize + width as usize).saturating_sub(4));
    f.render_widget(Paragraph::new(Span::styled(ticks, dim())), axis);

    let visible = bars.height as usize;
    let sel = app.task_sel.min(rows.len().saturating_sub(1));
    let offset = sel.saturating_sub(visible.saturating_sub(1));
    let lines: Vec<Line> = rows
        .iter()
        .enumerate()
        .skip(offset)
        .take(visible)
        .map(|(i, r)| {
            let start = r.t_start.map(|t| ((t - t0) / span * width) as usize);
            let end = match r.status {
                Status::Running => Some(width as usize),
                _ => r.t_end.map(|t| ((t - t0) / span * width).ceil() as usize),
            };
            let mut bar = String::new();
            let color = match r.status {
                Status::Fail => FAIL,
                Status::Running => RUN,
                _ if r.cached => DIM,
                _ => stage_color(&r.stage),
            };
            if let (Some(s), Some(e)) = (start, end) {
                let s = s.min(width as usize);
                let e = e.max(s + 1).min(width as usize);
                bar.push_str(&" ".repeat(s));
                bar.push_str(&"█".repeat(e - s));
                bar.push_str(&" ".repeat((width as usize).saturating_sub(e)));
            } else {
                bar.push_str(&"·".repeat(width as usize));
            }
            let right = if r.cached { "reused".to_string() } else { format!("{:>6} {}", secs(r.seconds), usd(r).content) };
            let style = if i == sel { Style::new().bg(SELECTED) } else { Style::new() };
            Line::from(vec![
                Span::styled(format!("{:<w$}", clip(&r.label(), LABEL as usize - 1), w = LABEL as usize), Style::new().fg(stage_color(&r.stage))),
                Span::styled(bar, Style::new().fg(color)),
                Span::styled(format!(" {right}"), dim()),
            ])
            .style(style)
        })
        .collect();
    f.render_widget(Paragraph::new(lines), bars);

    let model: f64 = rows.iter().filter(|r| matches!(r.stage.as_str(), "plan" | "backend" | "intent" | "architect" | "critic"))
        .filter_map(|r| if r.cached { None } else { r.seconds })
        .sum();
    let sandbox: f64 = rows.iter().filter(|r| matches!(r.stage.as_str(), "preflight" | "audit" | "verify"))
        .filter_map(|r| r.seconds)
        .sum();
    let reused = rows.iter().filter(|r| r.cached).count();
    let text = vec![Line::from(vec![
        Span::styled("wall ", dim()),
        Span::styled(secs(Some(b.wall_secs(now()))), theme_title()),
        Span::styled("   model time ", dim()),
        Span::raw(secs(Some(model))),
        Span::styled("   audit time ", dim()),
        Span::raw(secs(Some(sandbox))),
        Span::styled("   spent ", dim()),
        Span::raw(format!("${:.2}", b.spent())),
        Span::styled(format!("   {reused} stages reused"), dim()),
    ])];
    f.render_widget(Paragraph::new(text), summary);
}

// ---------------------------------------------------------------- Report

pub fn draw_report(f: &mut Frame, area: Rect, app: &App, b: &Build) {
    let (label, status) = b.label();
    let block = panel("Report", app.focus == Focus::Main)
        .title_bottom(Line::from(vec![Span::raw(" "), Span::styled(format!(" {label} "), state_style(status)), Span::raw(" ")]).right_aligned());
    let Some(report) = &b.report else {
        let msg = match b.state() {
            State::Running(stage) => format!("REPORT.md is written when the build ends. Now: {stage}."),
            State::Stopped => "stopped before the report was written; e resumes it".into(),
            State::Error(e) => format!("the build crashed: {e}"),
            _ => "no REPORT.md in this run".into(),
        };
        f.render_widget(Paragraph::new(Span::styled(msg, dim())).wrap(Wrap { trim: true }).block(block), area);
        return;
    };
    f.render_widget(Paragraph::new(markdown(report)).wrap(Wrap { trim: false }).block(block).scroll((app.report_scroll, 0)), area);
}

/// Just enough markdown for REPORT.md: headings, bold lines, bullets, code spans left as they are.
pub fn markdown(text: &str) -> Vec<Line<'static>> {
    text.lines()
        .map(|l| {
            let t = l.trim_start();
            if let Some(h) = t.strip_prefix("# ") {
                Line::from(Span::styled(h.to_string(), Style::new().fg(BG_ACCENT).bold()))
            } else if let Some(h) = t.strip_prefix("## ") {
                Line::from(Span::styled(h.to_string(), theme_title()))
            } else if t.starts_with("**") {
                let s = t.replace("**", "");
                let color = if s.contains("FALLBACK") || s.contains("FAILED") { FAIL } else if s.contains("WORKS") || s.contains("VERIFIED") { OK } else { TEXT };
                Line::from(Span::styled(s, Style::new().fg(color).bold()))
            } else if t.starts_with("- ") {
                Line::from(vec![Span::styled(" • ", key()), Span::styled(l.replace("**", "").trim_start()[2..].to_string(), Style::new().fg(TEXT))])
            } else {
                Line::from(Span::styled(l.replace("**", ""), Style::new().fg(TEXT)))
            }
        })
        .collect()
}
