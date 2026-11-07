use crate::trace::Status;
use ratatui::style::{Color, Modifier, Style};

pub const BG_ACCENT: Color = Color::Rgb(124, 92, 255); // NOVA violet
pub const DIM: Color = Color::Rgb(110, 110, 130);
pub const TEXT: Color = Color::Rgb(220, 220, 235);
pub const OK: Color = Color::Rgb(80, 220, 140);
pub const FAIL: Color = Color::Rgb(255, 95, 110);
pub const RUN: Color = Color::Rgb(255, 200, 70);
pub const BORDER: Color = Color::Rgb(70, 70, 95);
pub const BORDER_FOCUS: Color = BG_ACCENT;

pub fn domain_color(domain: &str) -> Color {
    match domain {
        "database" => Color::Rgb(90, 170, 255),
        "auth" => Color::Rgb(255, 140, 80),
        "network" => Color::Rgb(80, 220, 200),
        "frontend" => Color::Rgb(240, 110, 210),
        "manager" => BG_ACCENT,
        _ => DIM,
    }
}

pub fn domain_icon(domain: &str) -> &'static str {
    match domain {
        "database" => "◆",
        "auth" => "◈",
        "network" => "⇄",
        "frontend" => "▣",
        _ => "•",
    }
}

pub fn status_color(s: Status) -> Color {
    match s {
        Status::Pending => DIM,
        Status::Running => RUN,
        Status::Ok => OK,
        Status::Fail => FAIL,
    }
}

pub fn status_icon(s: Status) -> &'static str {
    match s {
        Status::Pending => "○",
        Status::Running => "◐",
        Status::Ok => "✔",
        Status::Fail => "✘",
    }
}

pub fn title() -> Style {
    Style::new().fg(TEXT).add_modifier(Modifier::BOLD)
}

pub fn dim() -> Style {
    Style::new().fg(DIM)
}

pub fn key() -> Style {
    Style::new().fg(BG_ACCENT).add_modifier(Modifier::BOLD)
}
