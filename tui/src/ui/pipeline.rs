//! The hero view: brief -> manager -> dispatcher -> four specialist lanes -> integrator -> verdict.

use super::theme::*;
use super::{clip, panel};
use crate::app::{App, Focus};
use crate::trace::{DOMAINS, Status, adapter_of};
use ratatui::Frame;
use ratatui::layout::{Alignment, Constraint, Layout, Rect};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, Gauge, Paragraph};

pub fn draw(f: &mut Frame, area: Rect, app: &App) {
    let focused = app.focus == Focus::Main;
    let outer = panel("Pipeline", focused);
    let inner = outer.inner(area);
    f.render_widget(outer, area);

    let [flow, lanes, cards] = Layout::vertical([
        Constraint::Length(5),
        Constraint::Min(6),
        Constraint::Length(6),
    ])
    .areas(inner);
    draw_flow(f, flow, app);
    draw_lanes(f, lanes, app);
    draw_cards(f, cards, app);
}

struct Stage {
    name: &'static str,
    lines: [String; 2],
    color: Color,
}

fn draw_flow(f: &mut Frame, area: Rect, app: &App) {
    let run = &app.run;
    let tasks = run.tasks();
    let done = tasks.iter().filter(|t| matches!(t.status, Status::Ok | Status::Fail)).count();
    let planned = run.planned_tasks();
    let stats = run.llm_stats();
    let empty = run.events.is_empty();

    let state = |started: bool, finished: bool, failed: bool| -> Color {
        match (started, finished, failed) {
            (_, true, true) => FAIL,
            (_, true, false) => OK,
            (true, false, _) => RUN,
            _ => DIM,
        }
    };

    let plan = run.plan();
    let manager_ms = stats.get("manager").map(|s| s.avg_ms()).unwrap_or(0.0);
    let fin = run.final_event();
    let stages = [
        Stage {
            name: "BRIEF",
            lines: [
                run.project_id().map(|p| clip(p, 14)).unwrap_or_else(|| "—".into()),
                format!("mode {}", run.mode()),
            ],
            color: if empty { DIM } else { OK },
        },
        Stage {
            name: "MANAGER",
            lines: [
                planned.map(|n| format!("{n} tasks")).unwrap_or_else(|| "planning…".into()),
                if plan.is_some_and(|p| p.caller == "gold") { "gold plan".into() } else { format!("{manager_ms:.0} ms") },
            ],
            color: state(!empty, plan.is_some(), plan.is_some_and(|p| !p.ok)),
        },
        Stage {
            name: "DISPATCH",
            lines: [
                format!("{done}/{} settled", planned.unwrap_or(tasks.len())),
                format!("{} levels", if tasks.is_empty() { 0 } else { run.max_level() + 1 }),
            ],
            color: state(!tasks.is_empty(), fin.is_some(), false),
        },
        Stage {
            name: "INTEGRATOR",
            lines: [
                format!("{} ok", tasks.iter().filter(|t| t.status == Status::Ok).count()),
                format!("{} failed", tasks.iter().filter(|t| t.status == Status::Fail).count()),
            ],
            color: state(fin.is_some(), fin.is_some(), fin.is_some_and(|e| !e.ok)),
        },
        Stage {
            name: "DELIVERABLE",
            lines: [
                match run.passed() {
                    Some(true) => "PASS".into(),
                    Some(false) => "FAIL".into(),
                    None => "…".into(),
                },
                clip(run.verdict().trim_start_matches("fail:"), 14),
            ],
            color: match run.passed() {
                Some(true) => OK,
                Some(false) => FAIL,
                None => DIM,
            },
        },
    ];

    // too narrow for five boxes: one status line per stage instead
    if area.width < 100 {
        let mut lines = Vec::new();
        for s in &stages {
            lines.push(Line::from(vec![
                Span::styled(format!(" {:<12}", s.name), Style::new().fg(s.color).bold()),
                Span::styled(format!("{}  ", s.lines[0]), title()),
                Span::styled(s.lines[1].clone(), dim()),
            ]));
        }
        f.render_widget(Paragraph::new(lines), area);
        return;
    }

    let mut cons = Vec::new();
    for i in 0..stages.len() {
        cons.push(Constraint::Fill(1));
        if i + 1 < stages.len() {
            cons.push(Constraint::Length(3));
        }
    }
    let cells = Layout::horizontal(cons).split(area);
    for (i, s) in stages.iter().enumerate() {
        let r = cells[i * 2];
        let b = Block::new()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::new().fg(s.color))
            .title(Span::styled(format!(" {} ", s.name), Style::new().fg(s.color).bold()))
            .title_alignment(Alignment::Center);
        let p = Paragraph::new(vec![
            Line::from(Span::styled(s.lines[0].clone(), title())),
            Line::from(Span::styled(s.lines[1].clone(), dim())),
        ])
        .alignment(Alignment::Center)
        .block(b);
        f.render_widget(p, r);
        if i + 1 < stages.len() {
            let a = cells[i * 2 + 1];
            let arrow_color = if s.color == DIM { BORDER } else { s.color };
            let y = Rect { y: a.y + a.height / 2, height: 1, ..a };
            f.render_widget(Paragraph::new(Span::styled("━▶", Style::new().fg(arrow_color))).alignment(Alignment::Center), y);
        }
    }
}

fn draw_lanes(f: &mut Frame, area: Rect, app: &App) {
    let tasks = app.run.tasks();
    let selected = tasks.get(app.task_sel).map(|t| t.id.clone());
    let cols = Layout::horizontal([Constraint::Fill(1); 4]).spacing(1).split(area);
    for (i, d) in DOMAINS.iter().enumerate() {
        let color = domain_color(d);
        let mine: Vec<_> = tasks.iter().filter(|t| t.domain == *d).collect();
        let running = mine.iter().any(|t| t.status == Status::Running);
        let title = Line::from(vec![
            Span::styled(format!(" {} ", domain_icon(d)), Style::new().fg(color)),
            Span::styled(format!("{d} "), Style::new().fg(color).bold()),
            if running { Span::styled(format!("{} ", app.spinner()), Style::new().fg(RUN)) } else { Span::raw("") },
        ]);
        let b = Block::new()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::new().fg(if running { color } else { BORDER }))
            .title(title)
            .title_bottom(Span::styled(format!(" {} ", adapter_of(d)), dim()));
        // border (2) + status icon (3) + optional " 1.2s" (5)
        let show_time = cols[i].width >= 24;
        let w = (cols[i].width as usize).saturating_sub(if show_time { 10 } else { 5 }).max(4);
        let mut lines = Vec::new();
        let mut last_level = None;
        for t in &mine {
            if last_level != Some(t.level) {
                lines.push(Line::from(Span::styled(format!("L{}", t.level), dim())));
                last_level = Some(t.level);
            }
            let sc = status_color(t.status);
            let icon = if t.status == Status::Running { app.spinner() } else { status_icon(t.status) };
            let mut style = Style::new().fg(TEXT);
            if selected.as_deref() == Some(t.id.as_str()) {
                style = style.bg(Color::Rgb(45, 40, 80)).bold();
            }
            lines.push(Line::from(vec![
                Span::styled(format!(" {icon} "), Style::new().fg(sc)),
                Span::styled(clip(&app.task_label(&t.id), w), style),
                Span::styled(if show_time { t.secs().map(|s| format!(" {s:.1}s")).unwrap_or_default() } else { String::new() }, dim()),
            ]));
        }
        if mine.is_empty() {
            lines.push(Line::from(Span::styled(" idle", dim())));
        }
        f.render_widget(Paragraph::new(lines).block(b), cols[i]);
    }
}

fn draw_cards(f: &mut Frame, area: Rect, app: &App) {
    let stats = app.run.llm_stats();
    let tasks = app.run.tasks();
    let cols = Layout::horizontal([Constraint::Fill(1); 4]).spacing(1).split(area);
    for (i, d) in DOMAINS.iter().enumerate() {
        let a = adapter_of(d);
        let s = stats.get(&a).cloned().unwrap_or_default();
        let mine: Vec<_> = tasks.iter().filter(|t| t.domain == *d).collect();
        let ok = mine.iter().filter(|t| t.status == Status::Ok).count();
        let settled = mine.iter().filter(|t| matches!(t.status, Status::Ok | Status::Fail)).count();
        let color = domain_color(d);
        let b = Block::new()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::new().fg(BORDER))
            .title(Span::styled(format!(" {a} "), Style::new().fg(color).bold()));
        let inner = b.inner(cols[i]);
        f.render_widget(b, cols[i]);
        let [l1, l2, g] = Layout::vertical([Constraint::Length(1); 3]).areas(inner);
        f.render_widget(
            Paragraph::new(Line::from(vec![
                Span::styled(format!("{} calls", s.calls), title()),
                Span::styled(format!("  {:.0} ms avg", s.avg_ms()), dim()),
            ])),
            l1,
        );
        f.render_widget(
            Paragraph::new(Line::from(vec![
                Span::styled(format!("{}↓ {}↑ tok", s.in_tokens, s.out_tokens), dim()),
                if s.failures > 0 { Span::styled(format!("  {} retries", s.failures), Style::new().fg(FAIL)) } else { Span::raw("") },
            ])),
            l2,
        );
        let ratio = if settled == 0 { 0.0 } else { ok as f64 / settled as f64 };
        let gauge = Gauge::default()
            .gauge_style(Style::new().fg(if ratio >= 1.0 { OK } else if settled == 0 { BORDER } else { RUN }).bg(Color::Rgb(35, 35, 50)))
            .ratio(ratio)
            .label(Span::styled(format!("{ok}/{settled} pass"), Style::new().fg(TEXT).bold()));
        f.render_widget(gauge, g);
    }
}
