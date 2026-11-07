//! Frame layout: header, tab bar, runs sidebar + active view, footer, help overlay.

mod arms;
mod build;
mod deliverable;
mod log;
mod pipeline;
mod tasks;
pub mod theme;
mod timeline;

use crate::app::{App, Focus, Tab};
use crate::form::{ARCHITECTS, BuildForm, Field, Input, Step};
use ratatui::Frame;
use ratatui::layout::{Alignment, Constraint, Flex, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, Clear, List, ListItem, ListState, Paragraph, Tabs, Wrap};
use theme::*;

pub fn draw(f: &mut Frame, app: &App) {
    let [header, tabs, body, footer] = Layout::vertical([
        Constraint::Length(3),
        Constraint::Length(1),
        Constraint::Min(8),
        Constraint::Length(2),
    ])
    .areas(f.area());

    draw_header(f, header, app);
    draw_tabs(f, tabs, app);

    // narrow terminals (80 cols) get a slimmer sidebar so the main view stays readable
    let side_w = if body.width < 120 { 20 } else { 30 };
    let [side, main] = Layout::horizontal([Constraint::Length(side_w), Constraint::Min(40)]).areas(body);
    draw_runs(f, side, app);
    match (app.tab, &app.build) {
        (Tab::Pipeline, Some(b)) => build::draw_pipeline(f, main, app, b),
        (Tab::Tasks, Some(b)) => build::draw_tasks(f, main, app, b),
        (Tab::Timeline, Some(b)) => build::draw_timeline(f, main, app, b),
        (Tab::Report, Some(b)) => build::draw_report(f, main, app, b),
        (Tab::Pipeline, None) => pipeline::draw(f, main, app),
        (Tab::Tasks, None) => tasks::draw(f, main, app),
        (Tab::Timeline, None) => timeline::draw(f, main, app),
        (Tab::Report, None) => draw_trace_report(f, main, app),
        (Tab::Deliverable, _) => deliverable::draw(f, main, app),
        (Tab::Log, _) => log::draw(f, main, app),
        (Tab::Arms, _) => arms::draw(f, main, app),
    }
    draw_footer(f, footer, app);
    if let Some(form) = &app.form {
        draw_form(f, app, form);
    }
    if app.show_help {
        draw_help(f, app);
    }
}

/// Rows of the Tasks view for a build (the selection moves over them).
pub fn build_task_count(b: &crate::build::Build) -> usize {
    build::task_rows(b).len()
}

fn draw_trace_report(f: &mut Frame, area: Rect, app: &App) {
    let text = vec![
        Line::from(Span::styled("Reports belong to Minerva builds (runs/<id>/REPORT.md).", dim())),
        Line::from(Span::styled("Select a build in the runs list, or press r to start one.", dim())),
    ];
    f.render_widget(Paragraph::new(text).block(panel("Report", app.focus == Focus::Main)), area);
}

pub fn panel(title: &str, focused: bool) -> Block<'static> {
    Block::new()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::new().fg(if focused { BORDER_FOCUS } else { BORDER }))
        .title(Span::styled(format!(" {title} "), title_style(focused)))
}

fn title_style(focused: bool) -> Style {
    if focused { Style::new().fg(BG_ACCENT).add_modifier(Modifier::BOLD) } else { theme::title() }
}

pub fn verdict_span(app: &App) -> Span<'static> {
    if let Some(b) = &app.build {
        let (label, status) = b.label();
        let label = if status == crate::trace::Status::Running { format!("{} {label}", app.spinner()) } else { label };
        return Span::styled(format!(" {label} "), build::state_style(status));
    }
    let v = app.run.verdict();
    if app.run.events.is_empty() {
        return Span::styled(" NO RUN ", Style::new().fg(DIM).reversed());
    }
    match app.run.passed() {
        Some(true) => Span::styled(" PASS ", Style::new().fg(OK).reversed().bold()),
        Some(false) if v == "error" => Span::styled(" ERROR ", Style::new().fg(FAIL).reversed().bold()),
        Some(false) => Span::styled(" FAIL ", Style::new().fg(FAIL).reversed().bold()),
        None => Span::styled(format!(" {} RUNNING ", app.spinner()), Style::new().fg(RUN).reversed().bold()),
    }
}

fn draw_header(f: &mut Frame, area: Rect, app: &App) {
    let block = Block::new()
        .borders(Borders::BOTTOM)
        .border_style(Style::new().fg(BORDER));
    let inner = block.inner(area);
    f.render_widget(block, area);
    let run = &app.run;
    let (id, mode, wall) = match &app.build {
        Some(b) => (b.id.clone(), b.engine(), b.wall_secs(build::now())),
        None => (run.id.clone(), run.mode().to_string(), run.wall_secs()),
    };
    let id = if id.is_empty() { "—".to_string() } else { id };
    let narrow = inner.width < 120;
    let id = if narrow { clip(&id, (inner.width as usize).saturating_sub(40).max(8)) } else { id };
    let mut info = vec![Span::styled(id, theme::title())];
    if !narrow {
        info.push(Span::styled(format!("  {mode}"), dim()));
    }
    let wall = if app.build.is_some() { build::secs(Some(wall)) } else { format!("{wall:.2}s") };
    info.push(Span::styled(format!("  {wall}  "), dim()));
    info.push(verdict_span(app));
    let info = Line::from(info).alignment(Alignment::Right);
    let right_w = (info.width() as u16 + 1).min(inner.width.saturating_sub(10));
    let [left, right] = Layout::horizontal([Constraint::Min(10), Constraint::Length(right_w)]).areas(inner);

    let logo = if left.width < 70 {
        Line::from(Span::styled(" ✦ MINERVA ", Style::new().fg(TEXT).bg(BG_ACCENT).bold()))
    } else if app.build.is_some() || (app.demo.is_none() && app.run.events.is_empty()) {
        Line::from(vec![
            Span::styled(" ✦ MINERVA ", Style::new().fg(TEXT).bg(BG_ACCENT).bold()),
            Span::raw("  "),
            Span::styled("what", key()),
            Span::styled(" → manager → ", dim()),
            Span::styled("◆◈⇄", Style::new().fg(domain_color("network"))),
            Span::styled(" backend → ", dim()),
            Span::styled("look", Style::new().fg(domain_color("frontend")).bold()),
            Span::styled(" → frontend → audit → project", dim()),
        ])
    } else {
        Line::from(vec![
        Span::styled(" ✦ MINERVA ", Style::new().fg(TEXT).bg(BG_ACCENT).bold()),
        Span::raw("  "),
        Span::styled("manager SLM", Style::new().fg(domain_color("manager")).bold()),
        Span::styled(" → ", dim()),
        Span::styled("◆", Style::new().fg(domain_color("database"))),
        Span::styled("◈", Style::new().fg(domain_color("auth"))),
        Span::styled("⇄", Style::new().fg(domain_color("network"))),
        Span::styled("▣", Style::new().fg(domain_color("frontend"))),
        Span::styled(" 4 specialists", dim()),
        Span::styled(" → integrator", dim()),
        ])
    };
    f.render_widget(Paragraph::new(vec![logo, Line::default()]), left);
    f.render_widget(Paragraph::new(info), right);
}

fn draw_tabs(f: &mut Frame, area: Rect, app: &App) {
    let titles = Tab::ALL.iter().enumerate().map(|(i, t)| {
        Line::from(vec![Span::styled(format!("{}", i + 1), key()), Span::raw(format!(" {}", t.title()))])
    });
    let idx = Tab::ALL.iter().position(|t| *t == app.tab).unwrap_or(0);
    let tabs = Tabs::new(titles)
        .select(idx)
        .style(dim())
        .highlight_style(Style::new().fg(TEXT).bg(BG_ACCENT).bold())
        .divider(Span::styled("│", Style::new().fg(BORDER)))
        .padding(" ", " ");
    f.render_widget(tabs, area);
}

fn draw_runs(f: &mut Frame, area: Rect, app: &App) {
    let focused = app.focus == Focus::Runs;
    let block = panel("Runs", focused);
    if app.demo.is_some() {
        let p = Paragraph::new(vec![
            Line::from(Span::styled("▶ demo-orders-0", Style::new().fg(BG_ACCENT).bold())),
            Line::from(Span::styled("  synthetic trace", dim())),
            Line::default(),
            Line::from(vec![Span::styled("d", key()), Span::styled(" real traces", dim())]),
            Line::from(vec![Span::styled("R", key()), Span::styled(" replay demo", dim())]),
        ])
        .block(block);
        f.render_widget(p, area);
        return;
    }
    if app.runs.is_empty() {
        let p = Paragraph::new(vec![
            Line::from(Span::styled("no runs yet", dim())),
            Line::default(),
            Line::from(vec![Span::styled("r", key()), Span::raw(" new build")]),
            Line::from(vec![Span::styled("T", key()), Span::raw(" slm run")]),
            Line::from(vec![Span::styled("d", key()), Span::raw(" demo mode")]),
        ])
        .wrap(Wrap { trim: true })
        .block(block);
        f.render_widget(p, area);
        return;
    }
    let items: Vec<ListItem> = app
        .runs
        .iter()
        .enumerate()
        .map(|(i, (p, _))| {
            let name = app.run_label(p);
            let is_build = App::is_build_path(p);
            // Only the selected run is parsed every tick; mark it with its verdict.
            let badge = if i == app.run_sel {
                let state = match &app.build {
                    Some(b) if is_build => match b.label().1 {
                        crate::trace::Status::Ok => Some(true),
                        crate::trace::Status::Fail => Some(false),
                        _ => None,
                    },
                    _ => app.run.passed(),
                };
                match state {
                    Some(true) => Span::styled("✔ ", Style::new().fg(OK)),
                    Some(false) => Span::styled("✘ ", Style::new().fg(FAIL)),
                    None => Span::styled(format!("{} ", app.spinner()), Style::new().fg(RUN)),
                }
            } else if is_build {
                Span::styled("◇ ", Style::new().fg(BG_ACCENT))
            } else {
                Span::styled("· ", dim())
            };
            ListItem::new(Line::from(vec![badge, Span::raw(name)]))
        })
        .collect();
    let list = List::new(items)
        .block(block)
        .highlight_style(Style::new().bg(ratatui::style::Color::Rgb(45, 40, 80)).bold())
        .highlight_symbol("▌");
    let mut state = ListState::default().with_selected(Some(app.run_sel));
    f.render_stateful_widget(list, area, &mut state);
}

fn draw_footer(f: &mut Frame, area: Rect, app: &App) {
    let [top, bottom] = Layout::vertical([Constraint::Length(1), Constraint::Length(1)]).areas(area);
    let o = &app.opts;
    let onoff = |b: bool| if b { Span::styled("on", Style::new().fg(OK)) } else { Span::styled("off", Style::new().fg(FAIL)) };
    let mut spans = if let Some(b) = &app.build {
        let engine = b.engine();
        vec![
            Span::styled(" build ", Style::new().fg(TEXT).bg(BORDER)),
            Span::raw(" "),
            Span::styled(engine.clone(), theme::title()),
            Span::styled("  $", dim()),
            Span::styled(format!("{:.2}", b.spent()), theme::title()),
            Span::styled(format!(" of ${:.2}", b.budget()), dim()),
            Span::styled("  data: ", dim()),
            Span::styled(build::data_label(app, &engine), theme::title()),
            Span::raw("   "),
        ]
    } else {
        vec![
            Span::styled(" T: slm run ", Style::new().fg(TEXT).bg(BORDER)),
            Span::raw(" project "),
            Span::styled(o.project.to_string(), theme::title()),
            Span::styled("  split ", dim()),
            Span::styled(o.split.clone(), theme::title()),
            Span::styled("  gold plan ", dim()),
            onoff(o.gold),
            Span::styled("  parallel ", dim()),
            onoff(o.parallel),
            Span::raw("   "),
        ]
    };
    if app.job_running() {
        spans.push(Span::styled(format!("{} ", app.spinner()), Style::new().fg(RUN)));
    }
    spans.push(Span::styled(app.status.clone(), dim()));
    f.render_widget(Paragraph::new(Line::from(spans)), top);

    let hints: &[(&str, &str)] = if app.build.is_some() {
        &[("r", "new build"), ("e", "resume"), ("x", "stop"), ("O", "open file"), ("tab/1-7", "view"), ("h/l", "focus"),
          ("j/k", "move"), ("J/K", "scroll"), ("?", "help"), ("q", "quit")]
    } else {
        &[("r", "new build"), ("T", "slm run"), ("+/-", "project"), ("g", "gold"), ("p", "parallel"), ("s", "split"),
          ("x", "stop"), ("tab/1-7", "view"), ("h/l", "focus"), ("j/k", "move"), ("d", "demo"), ("?", "help"), ("q", "quit")]
    };
    let mut line = vec![Span::raw(" ")];
    for (k, v) in hints {
        line.push(Span::styled(*k, key()));
        line.push(Span::styled(format!(" {v}  "), dim()));
    }
    f.render_widget(Paragraph::new(Line::from(line)), bottom);
}

fn draw_help(f: &mut Frame, app: &App) {
    let area = centered(f.area(), 72, 31);
    f.render_widget(Clear, area);
    let row = |k: &str, v: &str| Line::from(vec![Span::styled(format!("  {k:<10}"), key()), Span::raw(v.to_string())]);
    let text = vec![
        Line::from(Span::styled("MINERVA TUI", theme::title())),
        Line::from(Span::styled("drives `uv run minerva build`; watches runs/, .slm/traces and out/arch", dim())),
        Line::default(),
        row("r", "new build: what, look, engine (real models ask first)"),
        row("e", "resume the selected build (finished stages are reused)"),
        row("x", "stop the running job (Ctrl-C to it; it saves its stages)"),
        row("O", "open the selected file or screenshot (Deliverable)"),
        row("J / K", "scroll the file preview or the report"),
        row("1-7 / tab", "views: 6 = architecture arms, 7 = build report"),
        row("h / l", "focus runs list / main view"),
        row("j / k", "move selection (pgup/pgdn jump)"),
        row("T", "older flow: `slm run` with the footer's options"),
        row("+ / -", "slm run: next / previous generated project"),
        row("g / p / s", "slm run: gold plan / parallel / split"),
        row("[ / ]", "previous / next out/arch run in Arms"),
        row("o", "Arms: grade by spec checks or the run check"),
        row("d / R", "demo mode (no python needed) / replay it"),
        row("q / esc", "quit (asks first while a build runs)"),
        Line::default(),
        Line::from(Span::styled(format!("root: {}", app.root.display()), dim())),
        Line::from(Span::styled("press any key to close", dim())),
    ];
    let p = Paragraph::new(text).block(panel("help", true)).wrap(Wrap { trim: false });
    f.render_widget(p, area);
}

/// The text of an input with a visible cursor, scrolled so the cursor stays in view.
fn input_line(input: &Input, focused: bool, width: usize) -> Line<'static> {
    let chars: Vec<char> = input.text.chars().collect();
    let width = width.max(4);
    let start = input.cursor.saturating_sub(width.saturating_sub(1));
    let visible: String = chars.iter().skip(start).take(width).collect();
    if !focused {
        return Line::from(Span::styled(visible, Style::new().fg(TEXT)));
    }
    let at = input.cursor - start;
    let before: String = visible.chars().take(at).collect();
    let cur: String = visible.chars().nth(at).map(String::from).unwrap_or_else(|| " ".into());
    let after: String = visible.chars().skip(at + 1).collect();
    Line::from(vec![
        Span::styled(before, Style::new().fg(TEXT)),
        Span::styled(cur, Style::new().fg(TEXT).reversed()),
        Span::styled(after, Style::new().fg(TEXT)),
    ])
}

fn draw_form(f: &mut Frame, app: &App, form: &BuildForm) {
    let area = centered(f.area(), 80, 19);
    f.render_widget(Clear, area);
    let engines = app.engine_list();
    let engine = form.engine_info(engines);
    let field_w = area.width.saturating_sub(16) as usize;
    let mut lines: Vec<Line> = Vec::new();
    let title = match &form.resume {
        Some(dir) => format!("Resume {}", dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default()),
        None => "New build".into(),
    };

    if form.step == Step::Confirm {
        let e = engine.cloned();
        let est = e.as_ref().and_then(|e| e.estimate(form.architect(), form.max_repairs));
        lines.push(Line::from(Span::styled(
            if e.as_ref().is_some_and(|e| e.costs_money) { "Start a build on real models?" } else { "Start this build?" },
            theme::title(),
        )));
        lines.push(Line::default());
        lines.push(Line::from(vec![Span::styled("what      ", key()), Span::raw(clip(&form.what.text, field_w))]));
        let look = if form.look.text.trim().is_empty() { "(default: clean product UI)".to_string() } else { form.look.text.clone() };
        lines.push(Line::from(vec![Span::styled("look      ", key()), Span::raw(clip(&look, field_w))]));
        if let Some(e) = &e {
            lines.push(Line::from(vec![Span::styled("engine    ", key()), Span::raw(e.label.clone())]));
            lines.push(Line::default());
            lines.push(Line::from(vec![Span::styled("data goes to  ", dim()), Span::styled(clip(&e.data_goes_to, field_w), Style::new().fg(RUN))]));
        }
        lines.push(Line::from(vec![
            Span::styled("cost          ", dim()),
            Span::styled(
                match est {
                    Some(v) => format!("up to ${v:.2} (Architect {}, {} repair{})", form.architect(), form.max_repairs,
                                       if form.max_repairs == 1 { "" } else { "s" }),
                    None => "unknown".into(),
                },
                Style::new().fg(RUN).bold(),
            ),
        ]));
        lines.push(Line::from(vec![
            Span::styled("hard stop     ", dim()),
            Span::raw(format!("${} budget: no stage starts if its estimate would pass it", form.budget.text.trim())),
        ]));
        if form.resume.is_some() {
            lines.push(Line::from(vec![
                Span::styled("spent so far  ", dim()),
                Span::raw(format!("${:.2} (finished stages are reused, not paid again)", form.spent)),
            ]));
        }
        lines.push(Line::default());
        lines.push(Line::from(vec![
            Span::styled("y", key()), Span::styled(" start   ", dim()),
            Span::styled("n / esc", key()), Span::styled(" back", dim()),
        ]));
        f.render_widget(Paragraph::new(lines).block(panel(&title, true)), area);
        return;
    }

    let arrows = |field: Field, text: String| -> Line<'static> {
        let focused = form.field == field;
        let style = if form.locked(field) { dim() } else if focused { Style::new().fg(TEXT).bold() } else { Style::new().fg(TEXT) };
        if form.locked(field) {
            Line::from(Span::styled(text, style))
        } else {
            Line::from(vec![Span::styled("◂ ", dim()), Span::styled(text, style), Span::styled(" ▸", dim())])
        }
    };
    for field in Field::ALL {
        let focused = form.field == field;
        let label = Span::styled(
            format!("{} {:<10}", if focused { "▶" } else { " " }, field.label()),
            if focused { key() } else { dim() },
        );
        let value = match field {
            Field::What => input_line(&form.what, focused && !form.locked(field), field_w),
            Field::Look => {
                if form.look.text.is_empty() && !focused {
                    Line::from(Span::styled("(optional) how should it look?", dim()))
                } else {
                    input_line(&form.look, focused && !form.locked(field), field_w)
                }
            }
            Field::Engine => match (engine, &app.engines) {
                (Some(e), _) => {
                    let mut l = arrows(field, format!("{}: {}", e.name, e.label));
                    l.push_span(Span::styled(
                        if e.available { "  ready".to_string() } else { "  not ready".to_string() },
                        Style::new().fg(if e.available { OK } else { FAIL }),
                    ));
                    l
                }
                (None, Some(Err(err))) => Line::from(Span::styled(clip(&format!("could not list engines: {err}"), field_w), Style::new().fg(FAIL))),
                (None, _) => Line::from(Span::styled(format!("{} checking engines…", app.spinner()), dim())),
            },
            Field::Architect => arrows(field, ARCHITECTS[form.architect % ARCHITECTS.len()].to_string()),
            Field::Repairs => arrows(field, format!("{}", form.max_repairs)),
            Field::Budget => input_line(&form.budget, focused, 10),
        };
        let mut spans = vec![label];
        spans.extend(value.spans);
        lines.push(Line::from(spans));
        if field == Field::Look {
            lines.push(Line::default());
        }
    }
    lines.push(Line::default());
    if let Some(e) = engine {
        lines.push(Line::from(vec![Span::styled("  data goes to ", dim()), Span::styled(clip(&e.data_goes_to, field_w), Style::new().fg(TEXT))]));
        let cost = match e.estimate(form.architect(), form.max_repairs) {
            Some(v) if v > 0.0 => format!("up to ${v:.2} of a ${} budget", form.budget.text.trim()),
            _ => "free".into(),
        };
        lines.push(Line::from(vec![Span::styled("  cost         ", dim()), Span::styled(cost, Style::new().fg(TEXT))]));
        if !e.available {
            lines.push(Line::from(Span::styled(format!("  {}", clip(&e.why, field_w + 10)), Style::new().fg(FAIL))));
        }
    }
    if let Some(err) = &form.error {
        lines.push(Line::from(Span::styled(format!("  {err}"), Style::new().fg(FAIL).bold())));
    }
    let hint = Line::from(vec![
        Span::styled(" tab/↑↓", key()), Span::styled(" field  ", dim()),
        Span::styled("←→", key()), Span::styled(" change  ", dim()),
        Span::styled("enter", key()), Span::styled(" start  ", dim()),
        Span::styled("esc", key()), Span::styled(" cancel ", dim()),
    ]);
    let block = panel(&title, true).title_bottom(hint);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

pub fn centered(area: Rect, w: u16, h: u16) -> Rect {
    let [v] = Layout::vertical([Constraint::Length(h.min(area.height))]).flex(Flex::Center).areas(area);
    let [r] = Layout::horizontal([Constraint::Length(w.min(area.width))]).flex(Flex::Center).areas(v);
    r
}

/// Shorten to `n` chars with an ellipsis.
pub fn clip(s: &str, n: usize) -> String {
    if s.chars().count() <= n {
        s.to_string()
    } else {
        let mut out: String = s.chars().take(n.saturating_sub(1)).collect();
        out.push('…');
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app::App;
    use ratatui::{Terminal, backend::TestBackend};

    fn render(app: &App, w: u16, h: u16) -> String {
        let mut t = Terminal::new(TestBackend::new(w, h)).unwrap();
        t.draw(|f| draw(f, app)).unwrap();
        let buf = t.backend().buffer().clone();
        let mut out = String::new();
        for y in 0..h {
            for x in 0..w {
                out.push_str(buf[(x, y)].symbol());
            }
            out.push('\n');
        }
        out
    }

    /// Every view renders the finished demo run without panicking, at a small and a large size.
    #[test]
    fn all_views_render() {
        let mut app = App::new(std::env::temp_dir().join("nova-tui-test-root"), None, true);
        app.demo.as_mut().unwrap().skip(60.0);
        app.refresh();
        for tab in Tab::ALL {
            app.tab = tab;
            for (w, h) in [(80, 24), (160, 48)] {
                let s = render(&app, w, h);
                assert!(s.contains("MINERVA"));
            }
        }
        app.tab = Tab::Pipeline;
        let s = render(&app, 160, 48);
        assert!(s.contains("DELIVERABLE"));
        if let Ok(dir) = std::env::var("NOVA_SHOTS") {
            std::fs::create_dir_all(&dir).unwrap();
            // a small deliverable and a job log so those two views have something in the screenshots
            let tree = app.out_dir.join("dev-0000-orders");
            for (path, body) in [
                ("src/database/orders.sql", "-- spec-database\nCREATE TABLE orders (\n  id SERIAL PRIMARY KEY,\n  owner_id INTEGER NOT NULL REFERENCES users(id),\n  total_cents INTEGER NOT NULL,\n  status TEXT NOT NULL DEFAULT 'open',\n  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),\n  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()\n);\n"),
                ("src/database/users.sql", "CREATE TABLE users (\n  id SERIAL PRIMARY KEY,\n  email TEXT UNIQUE NOT NULL\n);\n"),
                ("src/auth/session.py", "def require_session(request):\n    ...\n"),
                ("src/network/orders_api.py", "@router.get(\"/api/orders\")\nasync def list_orders(user=Depends(require_session)):\n    ...\n"),
                ("src/frontend/OrdersPage.tsx", "export const route = \"/orders\"\nexport function OrdersPage() {}\n"),
                ("src/app.py", "from fastapi import FastAPI\n"),
            ] {
                let p = tree.join(path);
                std::fs::create_dir_all(p.parent().unwrap()).unwrap();
                std::fs::write(p, body).unwrap();
            }
            app.refresh();
            for l in [
                "$ uv run slm run --project 0 --split dev --gold --parallel",
                "dev-0000-orders: FAIL 14 files -> out/deliverable/dev-0000-orders",
                "  FAILED endpoint GET /api/line_items/{item_id} missing in src/network/line_item_api.py",
                "trace: .slm/traces/cli-dev-0000-orders.jsonl",
                "── run exited with code 0",
            ] {
                app.log.push_back(l.to_string());
            }
            for (i, tab) in Tab::ALL.iter().enumerate() {
                app.tab = *tab;
                app.task_sel = 6;
                app.arm_sel = 1;
                app.file_sel = 2;
                let mut t = Terminal::new(TestBackend::new(150, 44)).unwrap();
                t.draw(|f| draw(f, &app)).unwrap();
                let html = to_html(t.backend().buffer());
                std::fs::write(format!("{dir}/{}-{}.html", i + 1, tab.title().to_lowercase()), html).unwrap();
            }
        }
        if std::env::var("NOVA_PRINT").is_ok() {
            for tab in Tab::ALL {
                app.tab = tab;
                println!("{}", render(&app, 150, 44));
            }
        }
    }

    fn fixture(name: &str) -> std::path::PathBuf {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
    }

    fn build_app(name: &str) -> App {
        let root = std::env::temp_dir().join("nova-tui-build-root");
        App::new(root, Some(fixture(name)), false)
    }

    /// Every view renders a finished and a running Minerva build, at a small and a large size.
    #[test]
    fn build_views_render() {
        for name in ["build-finished", "build-running"] {
            let mut app = build_app(name);
            assert!(app.build.is_some(), "{name} should load as a build");
            for tab in Tab::ALL {
                app.tab = tab;
                for (w, h) in [(80, 24), (160, 48)] {
                    let s = render(&app, w, h);
                    assert!(s.contains("MINERVA"), "{name} {tab:?} {w}x{h}");
                }
            }
        }
        let mut app = build_app("build-finished");
        app.tab = Tab::Pipeline;
        let s = render(&app, 160, 48);
        for want in ["FALLBACK UI", "architect r1", "$0.58 of $3.00", "your Modal account", "restaurant owner"] {
            assert!(s.contains(want), "Pipeline is missing {want:?}:\n{s}");
        }
        app.tab = Tab::Tasks;
        let s = render(&app, 160, 48);
        assert!(s.contains("round 1") && s.contains("journey:desktop") && s.contains("src/auth/session.py"));
        app.tab = Tab::Report;
        assert!(render(&app, 160, 48).contains("Whole-stack journey"));
        app.tab = Tab::Deliverable;
        assert!(render(&app, 160, 48).contains("REPORT.md"));

        let mut app = build_app("build-running");
        app.tab = Tab::Pipeline;
        let s = render(&app, 160, 48);
        assert!(s.contains("RUNNING architect") && s.contains("reused") && s.contains("~$0.30"), "{s}");
        app.tab = Tab::Report;
        assert!(render(&app, 80, 24).contains("written when the build ends"));
    }

    /// The new-build dialog and its confirmation render, with engines from `minerva engines --json`.
    #[test]
    fn form_renders_edit_and_confirm() {
        let mut app = build_app("build-finished");
        app.engines = Some(crate::form::parse_engines(
            r#"[{"name": "modal", "label": "Real models on Modal", "data_goes_to": "your Modal account: open-weight models",
                 "leaves_machine": true, "costs_money": true, "available": true, "why": "ok",
                 "estimates": {"thinking": [0.88, 1.2, 1.52, 1.84], "instruct": [0.66, 0.76, 0.86, 0.96]}}]"#,
        ));
        let mut form = crate::form::BuildForm::new();
        form.what = Input::new("Track invoices for my clients");
        app.form = Some(form);
        for (w, h) in [(80, 24), (160, 48)] {
            let s = render(&app, w, h);
            assert!(s.contains("New build") && s.contains("Track invoices"), "{s}");
        }
        assert!(render(&app, 160, 48).contains("up to $1.20"));
        app.form.as_mut().unwrap().step = Step::Confirm;
        let s = render(&app, 160, 48);
        assert!(s.contains("Start a build on real models?") && s.contains("your Modal account") && s.contains("y start"), "{s}");
    }

    /// A terminal frame as colored HTML, for screenshots in PRs and docs (`NOVA_SHOTS=dir cargo test`).
    fn to_html(buf: &ratatui::buffer::Buffer) -> String {
        use ratatui::style::{Color, Modifier};
        fn css(c: Color, default: &str) -> String {
            match c {
                Color::Rgb(r, g, b) => format!("#{r:02x}{g:02x}{b:02x}"),
                Color::Reset => default.to_string(),
                other => format!("{other}").to_lowercase(),
            }
        }
        let mut out = String::from(
            "<pre style=\"background:#14141c;color:#dcdceb;font:13px/1.25 'JetBrains Mono',Menlo,monospace;padding:12px;margin:0;display:inline-block\">",
        );
        for y in 0..buf.area.height {
            for x in 0..buf.area.width {
                let c = &buf[(x, y)];
                let (mut fg, mut bg) = (css(c.fg, "#dcdceb"), css(c.bg, "transparent"));
                if c.modifier.contains(Modifier::REVERSED) {
                    std::mem::swap(&mut fg, &mut bg);
                    if fg == "transparent" {
                        fg = "#14141c".into();
                    }
                }
                let bold = if c.modifier.contains(Modifier::BOLD) { "font-weight:bold;" } else { "" };
                let sym = c.symbol().replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;");
                out.push_str(&format!("<span style=\"color:{fg};background:{bg};{bold}\">{sym}</span>"));
            }
            out.push('\n');
        }
        out.push_str("</pre>");
        out
    }
}
