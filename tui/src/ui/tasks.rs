//! Every task the dispatcher routed, with its specialist, level, latency and failure reason.

use super::theme::*;
use super::{clip, panel};
use crate::app::{App, Focus};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Cell, Paragraph, Row, Table, TableState, Wrap};

pub fn draw(f: &mut Frame, area: Rect, app: &App) {
    let [top, detail] = Layout::vertical([Constraint::Min(6), Constraint::Length(7)]).areas(area);
    let tasks = app.run.tasks();
    let rows = tasks.iter().map(|t| {
        let c = domain_color(&t.domain);
        let sc = status_color(t.status);
        Row::new(vec![
            Cell::from(Span::styled(status_icon(t.status), Style::new().fg(sc))),
            Cell::from(Span::styled(format!("L{}", t.level), dim())),
            Cell::from(app.task_label(&t.id)),
            Cell::from(Line::from(vec![
                Span::styled(format!("{} ", domain_icon(&t.domain)), Style::new().fg(c)),
                Span::styled(t.domain.clone(), Style::new().fg(c)),
            ])),
            Cell::from(Span::styled(t.adapter.clone(), dim())),
            Cell::from(t.secs().map(|s| format!("{s:>6.2}s")).unwrap_or_else(|| "     …".into())),
            Cell::from(Span::styled(
                if t.detail == "ok" { String::new() } else { clip(&t.detail, 60) },
                Style::new().fg(FAIL),
            )),
        ])
    });
    let table = Table::new(
        rows,
        [
            Constraint::Length(2),
            Constraint::Length(3),
            Constraint::Length(22),
            Constraint::Length(11),
            Constraint::Length(14),
            Constraint::Length(8),
            Constraint::Min(10),
        ],
    )
    .header(
        Row::new(["", "lvl", "task", "domain", "adapter", "time", "detail"])
            .style(Style::new().fg(DIM).bold())
            .bottom_margin(1),
    )
    .row_highlight_style(Style::new().bg(Color::Rgb(45, 40, 80)).bold())
    .highlight_symbol("▌")
    .block(panel(&format!("Tasks ({})", tasks.len()), app.focus == Focus::Main));
    let mut state = TableState::default().with_selected((!tasks.is_empty()).then_some(app.task_sel));
    f.render_stateful_widget(table, top, &mut state);

    let body = match tasks.get(app.task_sel) {
        None => vec![Line::from(Span::styled("no tasks in this run yet", dim()))],
        Some(t) => vec![
            Line::from(vec![
                Span::styled(app.task_label(&t.id), title()),
                Span::styled(format!("  {} → {}  level {}", t.domain, t.adapter, t.level), dim()),
            ]),
            Line::from(vec![
                Span::styled("status ", dim()),
                Span::styled(t.status.label(), Style::new().fg(status_color(t.status)).bold()),
                Span::styled(t.secs().map(|s| format!("   took {s:.3}s")).unwrap_or_default(), dim()),
            ]),
            Line::from(Span::styled(
                app.task_info.get(&t.id).map(|(_, d)| d.clone()).unwrap_or_default(),
                Style::new().fg(TEXT),
            )),
            Line::from(Span::styled(
                if t.detail.is_empty() || t.detail == "ok" { "all contract checks passed".to_string() } else { t.detail.clone() },
                Style::new().fg(if t.detail.is_empty() || t.detail == "ok" { OK } else { FAIL }),
            )),
        ],
    };
    f.render_widget(Paragraph::new(body).wrap(Wrap { trim: false }).block(panel("Selected task", false)), detail);
}
