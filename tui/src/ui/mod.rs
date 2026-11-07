//! Frame layout: header, tab bar, runs sidebar + active view, footer, help overlay.

mod arms;
mod deliverable;
mod log;
mod pipeline;
mod tasks;
pub mod theme;
mod timeline;

use crate::app::{App, Focus, Tab};
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
    match app.tab {
        Tab::Pipeline => pipeline::draw(f, main, app),
        Tab::Tasks => tasks::draw(f, main, app),
        Tab::Timeline => timeline::draw(f, main, app),
        Tab::Deliverable => deliverable::draw(f, main, app),
        Tab::Log => log::draw(f, main, app),
        Tab::Arms => arms::draw(f, main, app),
    }
    draw_footer(f, footer, app);
    if app.show_help {
        draw_help(f, app);
    }
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
    let id = if run.id.is_empty() { "—".to_string() } else { run.id.clone() };
    let narrow = inner.width < 120;
    let id = if narrow { clip(&id, (inner.width as usize).saturating_sub(34).max(8)) } else { id };
    let mut info = vec![Span::styled(id, theme::title())];
    if !narrow {
        info.push(Span::styled(format!("  {}", run.mode()), dim()));
    }
    info.push(Span::styled(format!("  {:.2}s  ", run.wall_secs()), dim()));
    info.push(verdict_span(app));
    let info = Line::from(info).alignment(Alignment::Right);
    let right_w = (info.width() as u16 + 1).min(inner.width.saturating_sub(10));
    let [left, right] = Layout::horizontal([Constraint::Min(10), Constraint::Length(right_w)]).areas(inner);

    let logo = if left.width < 70 {
        Line::from(Span::styled(" ✦ NOVA ", Style::new().fg(TEXT).bg(BG_ACCENT).bold()))
    } else {
        Line::from(vec![
        Span::styled(" ✦ NOVA ", Style::new().fg(TEXT).bg(BG_ACCENT).bold()),
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
            Line::from(Span::styled("no traces yet", dim())),
            Line::default(),
            Line::from(vec![Span::styled("r", key()), Span::raw(" run a project")]),
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
            // Only the selected run is parsed every tick; mark it with its verdict.
            let badge = if i == app.run_sel {
                match app.run.passed() {
                    Some(true) => Span::styled("✔ ", Style::new().fg(OK)),
                    Some(false) => Span::styled("✘ ", Style::new().fg(FAIL)),
                    None => Span::styled(format!("{} ", app.spinner()), Style::new().fg(RUN)),
                }
            } else {
                Span::styled("  ", dim())
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
    let mut spans = vec![
        Span::styled(" next run ", Style::new().fg(TEXT).bg(BORDER)),
        Span::raw(" project "),
        Span::styled(o.project.to_string(), theme::title()),
        Span::styled("  split ", dim()),
        Span::styled(o.split.clone(), theme::title()),
        Span::styled("  gold plan ", dim()),
        onoff(o.gold),
        Span::styled("  parallel ", dim()),
        onoff(o.parallel),
        Span::raw("   "),
    ];
    if app.job_running() {
        spans.push(Span::styled(format!("{} ", app.spinner()), Style::new().fg(RUN)));
    }
    spans.push(Span::styled(app.status.clone(), dim()));
    f.render_widget(Paragraph::new(Line::from(spans)), top);

    let hints = [
        ("r", "run"), ("+/-", "project"), ("g", "gold"), ("p", "parallel"), ("s", "split"),
        ("x", "stop"), ("tab/1-6", "view"), ("h/l", "focus"), ("j/k", "move"), ("d", "demo"), ("?", "help"), ("q", "quit"),
    ];
    let mut line = vec![Span::raw(" ")];
    for (k, v) in hints {
        line.push(Span::styled(k, key()));
        line.push(Span::styled(format!(" {v}  "), dim()));
    }
    f.render_widget(Paragraph::new(Line::from(line)), bottom);
}

fn draw_help(f: &mut Frame, app: &App) {
    let area = centered(f.area(), 64, 25);
    f.render_widget(Clear, area);
    let row = |k: &str, v: &str| Line::from(vec![Span::styled(format!("  {k:<10}"), key()), Span::raw(v.to_string())]);
    let text = vec![
        Line::from(Span::styled("NOVA TUI", theme::title())),
        Line::from(Span::styled("watches .slm/traces + out/arch, drives `uv run slm run`", dim())),
        Line::default(),
        row("r", "run the pipeline with the options in the footer"),
        row("+ / -", "next / previous generated project"),
        row("g", "toggle gold plan vs manager SLM plan"),
        row("p", "toggle parallel dispatch per dependency level"),
        row("s", "toggle split dev / test"),
        row("x", "stop the running job"),
        row("1-6 / tab", "switch view (6 = architecture arms)"),
        row("[ / ]", "previous / next out/arch run in Arms"),
        row("o", "Arms: grade by spec checks or the run check"),
        row("h / l", "focus runs list / main view"),
        row("j / k", "move selection (pgup/pgdn jump)"),
        row("d", "toggle demo mode (no python needed)"),
        row("R", "replay the demo from the start"),
        row("q / esc", "quit"),
        Line::default(),
        Line::from(Span::styled(format!("root: {}", app.root.display()), dim())),
        Line::from(Span::styled("press any key to close", dim())),
    ];
    let p = Paragraph::new(text).block(panel("help", true)).wrap(Wrap { trim: false });
    f.render_widget(p, area);
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
                assert!(s.contains("NOVA"));
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
