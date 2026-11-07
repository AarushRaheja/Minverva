//! The new-build dialog: what you want, how it should look, engine, Architect, repairs, budget. Then, for an engine
//! that costs money or sends data off this machine, a confirmation that says how much and where before anything runs.
//!
//! Engines, their prices and where they send data come from `uv run minerva engines --json` (minerva/engines.py),
//! so nothing about them is hard-coded here.

use crate::runner::BuildOpts;
use ratatui::crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::mpsc::{Receiver, channel};
use std::thread;

#[derive(Debug, Clone, Deserialize)]
pub struct EngineInfo {
    pub name: String,
    pub label: String,
    pub data_goes_to: String,
    pub leaves_machine: bool,
    pub costs_money: bool,
    pub available: bool,
    pub why: String,
    /// architect -> estimated $ for max_repairs 0..=3
    #[serde(default)]
    pub estimates: BTreeMap<String, Vec<f64>>,
}

impl EngineInfo {
    pub fn estimate(&self, architect: &str, max_repairs: u32) -> Option<f64> {
        self.estimates.get(architect)?.get(max_repairs as usize).copied()
    }
}

pub type EngineList = Result<Vec<EngineInfo>, String>;

/// Ask the pipeline for its engines in the background (uv startup takes a second); poll the receiver.
pub fn load_engines(root: &Path) -> Receiver<EngineList> {
    let (tx, rx) = channel();
    let root = root.to_path_buf();
    thread::spawn(move || {
        let out = Command::new("uv").args(["run", "minerva", "engines", "--json"]).current_dir(&root).output();
        let result = match out {
            Ok(o) if o.status.success() => parse_engines(&String::from_utf8_lossy(&o.stdout)),
            Ok(o) => Err(String::from_utf8_lossy(&o.stderr).lines().last().unwrap_or("minerva engines failed").to_string()),
            Err(e) => Err(format!("could not run uv: {e}")),
        };
        let _ = tx.send(result);
    });
    rx
}

pub fn parse_engines(json: &str) -> EngineList {
    serde_json::from_str(json).map_err(|e| e.to_string())
}

/// A one-line text field with a cursor, edited with the usual keys.
#[derive(Debug, Clone, Default)]
pub struct Input {
    pub text: String,
    /// cursor position in chars
    pub cursor: usize,
}

impl Input {
    pub fn new(text: &str) -> Input {
        Input { text: text.to_string(), cursor: text.chars().count() }
    }

    fn byte_at(&self, char_idx: usize) -> usize {
        self.text.char_indices().nth(char_idx).map(|(i, _)| i).unwrap_or(self.text.len())
    }

    /// Returns true if the key was an editing key.
    pub fn on_key(&mut self, key: KeyEvent) -> bool {
        let len = self.text.chars().count();
        let ctrl = key.modifiers.contains(KeyModifiers::CONTROL);
        match key.code {
            KeyCode::Char('u') if ctrl => {
                self.text.clear();
                self.cursor = 0;
            }
            KeyCode::Char('a') if ctrl => self.cursor = 0,
            KeyCode::Char('e') if ctrl => self.cursor = len,
            KeyCode::Char('w') if ctrl => {
                // delete the word before the cursor
                let chars: Vec<char> = self.text.chars().collect();
                let mut start = self.cursor;
                while start > 0 && chars[start - 1] == ' ' {
                    start -= 1;
                }
                while start > 0 && chars[start - 1] != ' ' {
                    start -= 1;
                }
                let (a, b) = (self.byte_at(start), self.byte_at(self.cursor));
                self.text.replace_range(a..b, "");
                self.cursor = start;
            }
            KeyCode::Char(c) if !ctrl => {
                let at = self.byte_at(self.cursor);
                self.text.insert(at, c);
                self.cursor += 1;
            }
            KeyCode::Backspace if self.cursor > 0 => {
                let (a, b) = (self.byte_at(self.cursor - 1), self.byte_at(self.cursor));
                self.text.replace_range(a..b, "");
                self.cursor -= 1;
            }
            KeyCode::Delete if self.cursor < len => {
                let (a, b) = (self.byte_at(self.cursor), self.byte_at(self.cursor + 1));
                self.text.replace_range(a..b, "");
            }
            KeyCode::Left => self.cursor = self.cursor.saturating_sub(1),
            KeyCode::Right => self.cursor = (self.cursor + 1).min(len),
            KeyCode::Home => self.cursor = 0,
            KeyCode::End => self.cursor = len,
            KeyCode::Backspace | KeyCode::Delete => {}
            _ => return false,
        }
        true
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Field {
    What,
    Look,
    Engine,
    Architect,
    Repairs,
    Budget,
}

impl Field {
    pub const ALL: [Field; 6] = [Field::What, Field::Look, Field::Engine, Field::Architect, Field::Repairs, Field::Budget];

    pub fn label(self) -> &'static str {
        match self {
            Field::What => "What",
            Field::Look => "Look",
            Field::Engine => "Engine",
            Field::Architect => "Architect",
            Field::Repairs => "Repairs",
            Field::Budget => "Budget $",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Step {
    Edit,
    Confirm,
}

pub enum Action {
    None,
    Cancel,
    Start(BuildOpts),
}

pub const ARCHITECTS: [&str; 2] = ["thinking", "instruct"];

pub struct BuildForm {
    pub what: Input,
    pub look: Input,
    pub budget: Input,
    pub engine: usize,
    pub architect: usize,
    pub max_repairs: u32,
    pub field: Field,
    pub step: Step,
    pub error: Option<String>,
    /// resuming this run directory: what, look and engine are fixed by its run.json
    pub resume: Option<PathBuf>,
    /// $ already spent by the run being resumed
    pub spent: f64,
}

impl BuildForm {
    pub fn new() -> BuildForm {
        BuildForm {
            what: Input::default(),
            look: Input::default(),
            budget: Input::new("3.00"),
            engine: 0,
            architect: 0,
            max_repairs: 1,
            field: Field::What,
            step: Step::Edit,
            error: None,
            resume: None,
            spent: 0.0,
        }
    }

    /// Resume a run: its brief, look and engine are fixed (minerva refuses a mismatch).
    pub fn resume(dir: PathBuf, meta: &crate::build::Meta, spent: f64, engines: &[EngineInfo]) -> BuildForm {
        let mut f = BuildForm::new();
        f.what = Input::new(&meta.brief);
        f.look = Input::new(&meta.look);
        f.engine = engines.iter().position(|e| e.name == meta.engine).unwrap_or(0);
        f.max_repairs = meta.max_repairs.min(3);
        f.budget = Input::new(&format!("{:.2}", if meta.budget_usd > 0.0 { meta.budget_usd } else { 3.0 }));
        f.field = Field::Architect;
        f.resume = Some(dir);
        f.spent = spent;
        f
    }

    pub fn locked(&self, field: Field) -> bool {
        self.resume.is_some() && matches!(field, Field::What | Field::Look | Field::Engine)
    }

    pub fn engine_info<'a>(&self, engines: &'a [EngineInfo]) -> Option<&'a EngineInfo> {
        engines.get(self.engine)
    }

    pub fn architect(&self) -> &'static str {
        ARCHITECTS[self.architect % ARCHITECTS.len()]
    }

    fn move_field(&mut self, delta: i32) {
        let i = Field::ALL.iter().position(|f| *f == self.field).unwrap_or(0) as i32;
        let n = Field::ALL.len() as i32;
        let mut next = i;
        for _ in 0..n {
            next = (next + delta).rem_euclid(n);
            if !self.locked(Field::ALL[next as usize]) {
                break;
            }
        }
        self.field = Field::ALL[next as usize];
    }

    fn cycle(&mut self, delta: i32, engines: &[EngineInfo]) {
        match self.field {
            Field::Engine if !engines.is_empty() => {
                self.engine = (self.engine as i32 + delta).rem_euclid(engines.len() as i32) as usize
            }
            Field::Architect => self.architect = (self.architect as i32 + delta).rem_euclid(ARCHITECTS.len() as i32) as usize,
            Field::Repairs => self.max_repairs = (self.max_repairs as i32 + delta).clamp(0, 3) as u32,
            _ => {}
        }
    }

    /// The options, or why they can't run yet.
    pub fn validate(&self, engines: &[EngineInfo]) -> Result<BuildOpts, String> {
        let what = self.what.text.trim();
        if what.is_empty() {
            return Err("say what you want built".into());
        }
        let engine = self.engine_info(engines).ok_or("no engines listed yet")?;
        if !engine.available {
            return Err(format!("{} is not ready: {}", engine.name, engine.why));
        }
        let budget: f64 = self.budget.text.trim().trim_start_matches('$').parse().map_err(|_| "budget must be a number")?;
        if budget <= 0.0 {
            return Err("budget must be above zero".into());
        }
        Ok(BuildOpts {
            what: what.to_string(),
            look: self.look.text.trim().to_string(),
            engine: engine.name.clone(),
            architect: self.architect().to_string(),
            max_repairs: self.max_repairs,
            budget_usd: budget,
            out: self.resume.clone(),
        })
    }

    pub fn needs_confirmation(&self, engines: &[EngineInfo]) -> bool {
        self.engine_info(engines).is_some_and(|e| e.costs_money || e.leaves_machine)
    }

    pub fn on_key(&mut self, key: KeyEvent, engines: &[EngineInfo]) -> Action {
        if self.step == Step::Confirm {
            return match key.code {
                KeyCode::Char('y') | KeyCode::Char('Y') => match self.validate(engines) {
                    Ok(opts) => Action::Start(opts),
                    Err(e) => {
                        self.step = Step::Edit;
                        self.error = Some(e);
                        Action::None
                    }
                },
                KeyCode::Char('n') | KeyCode::Esc | KeyCode::Backspace => {
                    self.step = Step::Edit;
                    Action::None
                }
                _ => Action::None,
            };
        }
        self.error = None;
        match key.code {
            KeyCode::Esc => return Action::Cancel,
            KeyCode::Enter => {
                return match self.validate(engines) {
                    Ok(opts) if !self.needs_confirmation(engines) => Action::Start(opts),
                    Ok(_) => {
                        self.step = Step::Confirm;
                        Action::None
                    }
                    Err(e) => {
                        self.error = Some(e);
                        Action::None
                    }
                };
            }
            KeyCode::Tab | KeyCode::Down => self.move_field(1),
            KeyCode::BackTab | KeyCode::Up => self.move_field(-1),
            _ => {
                if self.locked(self.field) {
                    return Action::None;
                }
                match self.field {
                    Field::What => {
                        self.what.on_key(key);
                    }
                    Field::Look => {
                        self.look.on_key(key);
                    }
                    Field::Budget => {
                        let ctrl = key.modifiers.contains(KeyModifiers::CONTROL);
                        if matches!(key.code, KeyCode::Char(c) if !ctrl && !(c.is_ascii_digit() || c == '.')) {
                            return Action::None;
                        }
                        self.budget.on_key(key);
                    }
                    _ => match key.code {
                        KeyCode::Left | KeyCode::Char('h') => self.cycle(-1, engines),
                        KeyCode::Right | KeyCode::Char('l') | KeyCode::Char(' ') => self.cycle(1, engines),
                        _ => {}
                    },
                }
            }
        }
        Action::None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn press(c: KeyCode) -> KeyEvent {
        KeyEvent::new(c, KeyModifiers::NONE)
    }

    fn engines() -> Vec<EngineInfo> {
        parse_engines(
            r#"[{"name": "offline", "label": "Offline", "data_goes_to": "nowhere", "leaves_machine": false,
                 "costs_money": false, "available": true, "why": "free",
                 "estimates": {"thinking": [0, 0, 0, 0], "instruct": [0, 0, 0, 0]}},
                {"name": "modal", "label": "Real models", "data_goes_to": "your Modal account", "leaves_machine": true,
                 "costs_money": true, "available": true, "why": "ok", "stage_usd": {"plan": 0.35},
                 "estimates": {"thinking": [0.88, 1.2, 1.52, 1.84], "instruct": [0.66, 0.76, 0.86, 0.96]}}]"#,
        )
        .unwrap()
    }

    fn type_text(f: &mut BuildForm, s: &str, e: &[EngineInfo]) {
        for c in s.chars() {
            f.on_key(press(KeyCode::Char(c)), e);
        }
    }

    #[test]
    fn input_edits_in_the_middle_and_handles_unicode() {
        let mut i = Input::new("café menu");
        i.on_key(press(KeyCode::Home));
        i.on_key(press(KeyCode::Right));
        i.on_key(press(KeyCode::Right));
        i.on_key(press(KeyCode::Right));
        i.on_key(press(KeyCode::Right));
        i.on_key(press(KeyCode::Backspace));
        assert_eq!(i.text, "caf menu");
        i.on_key(press(KeyCode::Char('é')));
        assert_eq!(i.text, "café menu");
        i.on_key(press(KeyCode::End));
        i.on_key(KeyEvent::new(KeyCode::Char('w'), KeyModifiers::CONTROL));
        assert_eq!(i.text, "café ");
    }

    #[test]
    fn offline_starts_on_enter_and_modal_asks_first() {
        let e = engines();
        let mut f = BuildForm::new();
        assert!(matches!(f.on_key(press(KeyCode::Enter), &e), Action::None));
        assert!(f.error.as_deref().unwrap().contains("what"));
        type_text(&mut f, "Track invoices", &e);
        f.on_key(press(KeyCode::Tab), &e);
        type_text(&mut f, "Warm", &e);
        match f.on_key(press(KeyCode::Enter), &e) {
            Action::Start(o) => assert_eq!((o.what.as_str(), o.look.as_str(), o.engine.as_str()), ("Track invoices", "Warm", "offline")),
            _ => panic!("offline should start at once"),
        }
        f.field = Field::Engine;
        f.on_key(press(KeyCode::Right), &e);
        assert_eq!(f.engine_info(&e).unwrap().name, "modal");
        assert!(matches!(f.on_key(press(KeyCode::Enter), &e), Action::None));
        assert_eq!(f.step, Step::Confirm);
        assert!(matches!(f.on_key(press(KeyCode::Char('n')), &e), Action::None));
        assert_eq!(f.step, Step::Edit);
        f.on_key(press(KeyCode::Enter), &e);
        match f.on_key(press(KeyCode::Char('y')), &e) {
            Action::Start(o) => assert_eq!((o.engine.as_str(), o.max_repairs, o.budget_usd), ("modal", 1, 3.0)),
            _ => panic!("y should start the confirmed build"),
        }
        assert_eq!(e[1].estimate("instruct", 2), Some(0.86));
    }

    #[test]
    fn resume_locks_brief_look_and_engine() {
        let e = engines();
        let meta = crate::build::Meta {
            brief: "Track invoices".into(),
            look: "Warm".into(),
            engine: "modal".into(),
            max_repairs: 1,
            budget_usd: 3.0,
            ..Default::default()
        };
        let mut f = BuildForm::resume(PathBuf::from("runs/x"), &meta, 0.42, &e);
        assert_eq!(f.field, Field::Architect);
        for _ in 0..6 {
            f.on_key(press(KeyCode::Tab), &e);
            assert!(!f.locked(f.field), "tab must skip locked fields");
        }
        f.on_key(press(KeyCode::Enter), &e);
        match f.on_key(press(KeyCode::Char('y')), &e) {
            Action::Start(o) => {
                assert_eq!(o.out, Some(PathBuf::from("runs/x")));
                assert_eq!(o.what, "Track invoices");
            }
            _ => panic!("resume should start after confirmation"),
        }
    }

    #[test]
    fn budget_takes_numbers_only_and_unready_engines_refuse() {
        let mut e = engines();
        let mut f = BuildForm::new();
        type_text(&mut f, "x", &e);
        f.field = Field::Budget;
        f.on_key(KeyEvent::new(KeyCode::Char('u'), KeyModifiers::CONTROL), &e);
        type_text(&mut f, "1a.5", &e);
        assert_eq!(f.budget.text, "1.5");
        e[0].available = false;
        e[0].why = "needs npm ci in harness/".into();
        f.on_key(press(KeyCode::Enter), &e);
        assert!(f.error.as_deref().unwrap().contains("npm ci"));
    }
}
