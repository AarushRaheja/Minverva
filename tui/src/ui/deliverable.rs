//! The file tree `slm run` wrote to out/deliverable/<project_id>/ with a code preview.

use super::theme::*;
use super::{clip, panel};
use crate::app::{App, Focus};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{List, ListItem, ListState, Paragraph};

fn file_color(path: &str) -> Color {
    if path.starts_with("src/database") || path.ends_with(".sql") {
        domain_color("database")
    } else if path.starts_with("src/auth") {
        domain_color("auth")
    } else if path.starts_with("src/network") {
        domain_color("network")
    } else if path.starts_with("src/frontend") {
        domain_color("frontend")
    } else {
        domain_color("manager") // integrator glue: app.py, main.py, requirements.txt
    }
}

pub fn draw(f: &mut Frame, area: Rect, app: &App) {
    let [list_area, preview] = Layout::horizontal([Constraint::Length(38), Constraint::Min(20)]).areas(area);
    let dir = app.deliverable_dir().map(|d| d.display().to_string()).unwrap_or_else(|| "—".into());

    if app.files.is_empty() {
        let msg = vec![
            Line::from(Span::styled("no files on disk for this run", dim())),
            Line::default(),
            Line::from(Span::styled(format!("looked in {dir}"), dim())),
            Line::from(vec![Span::styled("r", key()), Span::styled(" runs `slm run` which writes the tree there", dim())]),
        ];
        f.render_widget(Paragraph::new(msg).block(panel("Deliverable", app.focus == Focus::Main)), area);
        return;
    }

    let items: Vec<ListItem> = app
        .files
        .iter()
        .map(|p| {
            let s = p.to_string_lossy().into_owned();
            let depth = p.components().count().saturating_sub(1);
            let name = p.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            let parent = p.parent().map(|x| x.to_string_lossy().into_owned()).unwrap_or_default();
            ListItem::new(Line::from(vec![
                Span::styled("  ".repeat(depth.min(3)), dim()),
                Span::styled("▪ ", Style::new().fg(file_color(&s))),
                Span::raw(name),
                Span::styled(if parent.is_empty() { String::new() } else { format!("  {}", clip(&parent, 16)) }, dim()),
            ]))
        })
        .collect();
    let title = format!("Files ({})", app.files.len());
    let list = List::new(items)
        .block(panel(&title, app.focus == Focus::Main))
        .highlight_style(Style::new().bg(Color::Rgb(45, 40, 80)).bold())
        .highlight_symbol("▌");
    let mut st = ListState::default().with_selected(Some(app.file_sel));
    f.render_stateful_widget(list, list_area, &mut st);

    let rel = app.files.get(app.file_sel).map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
    let text = app.selected_file_text().unwrap_or_else(|| "(binary or unreadable)".into());
    let lines: Vec<Line> = text
        .lines()
        .enumerate()
        .map(|(i, l)| {
            Line::from(vec![
                Span::styled(format!("{:>4} │ ", i + 1), Style::new().fg(BORDER)),
                Span::styled(l.replace('\t', "    "), highlight(l)),
            ])
        })
        .collect();
    let verdict = super::verdict_span(app);
    let block = panel(&rel, false).title_bottom(Line::from(vec![Span::raw(" "), verdict, Span::raw(" ")]).right_aligned());
    f.render_widget(Paragraph::new(lines).block(block).scroll((app.preview_scroll, 0)), preview);
}

/// Tiny keyword tint, enough to make SQL/Python/TSX readable without a syntax engine.
fn highlight(line: &str) -> Style {
    let t = line.trim_start();
    if t.starts_with("--") || t.starts_with('#') || t.starts_with("//") {
        return Style::new().fg(DIM).italic();
    }
    const KW: [&str; 12] = ["CREATE", "def ", "async def", "export", "import", "from ", "class ", "@router", "return", "SELECT", "function", "const "];
    if KW.iter().any(|k| t.starts_with(k)) {
        return Style::new().fg(Color::Rgb(190, 170, 255));
    }
    Style::new().fg(TEXT)
}
