//! Architecture comparison from `python -m slm.arch run`: one row per arm, best first.
//! Answers the PLAN.md question at a glance: does the manager + specialists arm beat the monolith
//! and the hosted baselines, and what does it cost in wall clock and tokens?

use super::theme::*;
use super::{clip, panel};
use crate::app::{App, Focus};
use crate::arch::{REF_ARM, Score};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Cell, Paragraph, Row, Table, TableState, Wrap};

fn arm_color(arm: &str) -> Color {
    if arm.starts_with("gold") {
        DIM
    } else if arm.starts_with("base-") || arm.starts_with("opus") {
        domain_color("auth")
    } else if arm == "mono" {
        domain_color("frontend")
    } else {
        BG_ACCENT
    }
}

fn bar(frac: f64, width: usize) -> String {
    let cells = (frac.clamp(0.0, 1.0) * width as f64 * 8.0).round() as usize;
    let full = cells / 8;
    const PART: [&str; 8] = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"];
    let mut s = "█".repeat(full);
    if full < width {
        s.push_str(PART[cells % 8]);
    }
    s
}

fn pct(x: f64) -> String {
    format!("{:>3.0}%", x * 100.0)
}

pub fn draw(f: &mut Frame, area: Rect, app: &App) {
    let Some(run) = app.arch_run() else {
        let msg = vec![
            Line::from(Span::styled("no architecture results yet", dim())),
            Line::default(),
            Line::from(Span::styled("this view reads out/arch/<run>/results.jsonl, written by", dim())),
            Line::from(Span::styled("  uv run python -m slm.arch run --run a1 --arms mgr-G4,mono", title())),
            Line::default(),
            Line::from(vec![Span::styled("d", key()), Span::styled(" shows made-up demo numbers", dim())]),
        ];
        f.render_widget(Paragraph::new(msg).block(panel("Arms", app.focus == Focus::Main)), area);
        return;
    };
    let rows = run.scored(app.score);
    let summary = crate::arch::summarize(&rows);

    let [head, table_area, detail] =
        Layout::vertical([Constraint::Length(1), Constraint::Min(6), Constraint::Length(9)]).areas(area);

    // header: which run, which grade
    let mut spans = vec![
        Span::styled(" run ", Style::new().fg(TEXT).bg(BORDER)),
        Span::styled(format!(" {} ", run.name), title()),
    ];
    if app.arch_runs.len() > 1 {
        spans.push(Span::styled(format!("({}/{}) ", app.arch_sel + 1, app.arch_runs.len()), dim()));
        spans.push(Span::styled("[ ]", key()));
        spans.push(Span::styled(" switch  ", dim()));
    }
    spans.push(Span::styled(format!(" {} rows · {} arms  ", rows.len(), summary.len()), dim()));
    spans.push(Span::styled(" grade ", Style::new().fg(TEXT).bg(BORDER)));
    spans.push(Span::styled(format!(" {} ", app.score.label()), title()));
    if run.has_runchecks {
        spans.push(Span::styled("o", key()));
        spans.push(Span::styled(" toggle", dim()));
    } else if app.score == Score::Run {
        spans.push(Span::styled("(no runchecks.jsonl, showing spec)", dim()));
    }
    if app.demo.is_some() {
        spans.push(Span::styled("   demo numbers, not real results", Style::new().fg(RUN)));
    }
    f.render_widget(Paragraph::new(Line::from(spans)), head);

    let bar_w = (table_area.width as usize).saturating_sub(96).clamp(8, 36);
    let rows_ui = summary.iter().map(|s| {
        let c = arm_color(&s.arm);
        let is_ref = s.arm == REF_ARM;
        let delta = match s.d_task_vs_ref {
            Some(d) => Span::styled(format!("{:+.2}", d), Style::new().fg(if d >= 0.0 { OK } else { FAIL })),
            None if is_ref => Span::styled(" ref", dim()),
            None => Span::styled("   —", dim()),
        };
        Row::new(vec![
            Cell::from(Span::styled(s.arm.clone(), Style::new().fg(c).bold())),
            Cell::from(Span::styled(s.n.to_string(), dim())),
            Cell::from(Line::from(vec![
                Span::styled(pct(s.gold_pass), Style::new().fg(TEXT).bold()),
                Span::raw(" "),
                Span::styled(bar(s.gold_pass, bar_w), Style::new().fg(if s.gold_pass >= 0.999 { OK } else { c })),
            ])),
            Cell::from(Span::styled(pct(s.task_rate), Style::new().fg(TEXT))),
            Cell::from(delta),
            Cell::from(Span::styled(s.plan_recall.map(|x| format!("{x:.2}")).unwrap_or_else(|| "—".into()), dim())),
            Cell::from(format!("{:>5.0}s", s.p50_s)),
            Cell::from(Span::styled(
                s.d_wall_vs_ref.map(|x| format!("{x:.2}x")).unwrap_or_else(|| "—".into()),
                Style::new().fg(match s.d_wall_vs_ref {
                    Some(x) if x <= 1.0 => OK,
                    Some(_) => RUN,
                    None => DIM,
                }),
            )),
            Cell::from(format!("{:>8.0}", s.crit_tok)),
            Cell::from(Span::styled(format!("{:>4.1}", s.calls), dim())),
            Cell::from(Span::styled(format!("{:>6.0}", s.tok_out), dim())),
            Cell::from(Span::styled(
                if s.errors > 0 { s.errors.to_string() } else { String::new() },
                Style::new().fg(FAIL),
            )),
        ])
    });
    let table = Table::new(
        rows_ui,
        [
            Constraint::Length(16),
            Constraint::Length(3),
            Constraint::Length(bar_w as u16 + 6),
            Constraint::Length(5),
            Constraint::Length(6),
            Constraint::Length(6),
            Constraint::Length(7),
            Constraint::Length(7),
            Constraint::Length(9),
            Constraint::Length(5),
            Constraint::Length(8),
            Constraint::Length(4),
        ],
    )
    .header(
        Row::new(["arm", "n", "deliverable pass", "task", "Δ ref", "recall", "p50", "wall×", "crit tok", "calls", "out tok", "err"])
            .style(Style::new().fg(DIM).bold())
            .bottom_margin(1),
    )
    .row_highlight_style(Style::new().bg(Color::Rgb(45, 40, 80)))
    .highlight_symbol("▌")
    .block(panel(&format!("Arms (Δ and × are paired vs {REF_ARM})"), app.focus == Focus::Main));
    let mut st = TableState::default().with_selected((!summary.is_empty()).then_some(app.arm_sel.min(summary.len().saturating_sub(1))));
    f.render_stateful_widget(table, table_area, &mut st);

    // detail for the selected arm
    let Some(s) = summary.get(app.arm_sel.min(summary.len().saturating_sub(1))) else { return };
    let [doms, fails] = Layout::horizontal([Constraint::Fill(3), Constraint::Fill(2)]).areas(detail);
    let mut dl = Vec::new();
    for d in crate::trace::DOMAINS {
        let v = s.by_domain.get(d).copied();
        let color = domain_color(d);
        dl.push(Line::from(vec![
            Span::styled(format!(" {} {:<9}", domain_icon(d), d), Style::new().fg(color)),
            Span::styled(v.map(pct).unwrap_or_else(|| "   —".into()), Style::new().fg(TEXT).bold()),
            Span::raw(" "),
            Span::styled(bar(v.unwrap_or(0.0), (doms.width as usize).saturating_sub(22)), Style::new().fg(color)),
        ]));
    }
    dl.push(Line::default());
    dl.push(Line::from(Span::styled(
        format!(" p90 {:.0}s · {:.0} output tokens/project · {:.0} on the critical path", s.p90_s, s.tok_out, s.crit_tok),
        dim(),
    )));
    f.render_widget(Paragraph::new(dl).block(panel(&format!("{} · task pass by domain", s.arm), false)), doms);

    let mut fl = Vec::new();
    if s.first_fails.is_empty() {
        fl.push(Line::from(Span::styled("no failing projects", Style::new().fg(OK))));
    }
    for (check, n) in &s.first_fails {
        fl.push(Line::from(vec![
            Span::styled(format!("{n:>3}× "), Style::new().fg(FAIL).bold()),
            Span::styled(clip(check, 40), Style::new().fg(TEXT)),
        ]));
    }
    f.render_widget(
        Paragraph::new(fl).wrap(Wrap { trim: true }).block(panel("first failing check", false)),
        fails,
    );
}
