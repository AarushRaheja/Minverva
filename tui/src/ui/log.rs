//! stdout/stderr of the job started from the TUI (`minerva build` with `r`, `slm run` with `T`).

use super::panel;
use super::theme::*;
use crate::app::{App, Focus};
use ratatui::Frame;
use ratatui::layout::Rect;
use ratatui::style::{Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;

pub fn draw(f: &mut Frame, area: Rect, app: &App) {
    let title = if app.job_running() { format!("Log {}", app.spinner()) } else { "Log".into() };
    let block = panel(&title, app.focus == Focus::Main);
    if app.log.is_empty() {
        let p = Paragraph::new(vec![
            Line::from(Span::styled("nothing yet", dim())),
            Line::from(vec![Span::styled("r", key()), Span::styled(" starts a Minerva build; its output appears here", dim())]),
            Line::from(vec![Span::styled("T", key()), Span::styled(" runs the older `slm run` with the footer's options", dim())]),
        ])
        .block(block);
        f.render_widget(p, area);
        return;
    }
    let lines: Vec<Line> = app
        .log
        .iter()
        .map(|l| {
            let style = if l.starts_with("$ ") {
                Style::new().fg(BG_ACCENT).bold()
            } else if l.contains("PASS") {
                Style::new().fg(OK).bold()
            } else if l.contains("FAIL") || l.contains("Error") || l.contains("Traceback") {
                Style::new().fg(FAIL)
            } else if l.starts_with("──") {
                dim()
            } else {
                Style::new().fg(TEXT)
            };
            Line::from(Span::styled(l.clone(), style))
        })
        .collect();
    // Follow the tail; j/k scroll back from it.
    let h = area.height.saturating_sub(2) as usize;
    let bottom = lines.len().saturating_sub(h);
    let scroll = bottom.saturating_sub(app.log_scroll as usize) as u16;
    f.render_widget(Paragraph::new(lines).block(block).scroll((scroll, 0)), area);
}
