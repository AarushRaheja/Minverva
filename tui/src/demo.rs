//! A synthetic run that replays over a few seconds, so the UI can be demoed (or developed)
//! without Python, uv or a GPU. Shape matches what `slm run` writes: plan -> route/llm/task per
//! task, level by level -> final.

use crate::trace::{Run, TraceEvent};
use std::time::Instant;

struct T {
    id: &'static str,
    domain: &'static str,
    level: u32,
    secs: f64,
    ok: bool,
}

const TASKS: &[T] = &[
    T { id: "db-users", domain: "database", level: 0, secs: 0.9, ok: true },
    T { id: "db-orders", domain: "database", level: 0, secs: 1.1, ok: true },
    T { id: "db-line_item", domain: "database", level: 0, secs: 0.8, ok: true },
    T { id: "auth-session", domain: "auth", level: 1, secs: 1.3, ok: true },
    T { id: "auth-oauth", domain: "auth", level: 2, secs: 1.0, ok: true },
    T { id: "net-orders-rest", domain: "network", level: 2, secs: 1.4, ok: true },
    T { id: "net-line_item-rest", domain: "network", level: 2, secs: 1.2, ok: false },
    T { id: "auth-guards", domain: "auth", level: 2, secs: 0.7, ok: true },
    T { id: "net-orders-client", domain: "network", level: 3, secs: 0.9, ok: true },
    T { id: "fe-orders-page", domain: "frontend", level: 4, secs: 1.6, ok: true },
    T { id: "fe-orders-form", domain: "frontend", level: 4, secs: 1.2, ok: true },
    T { id: "fe-shell", domain: "frontend", level: 5, secs: 1.0, ok: true },
];

pub struct Demo {
    started: Instant,
    offset: f64,
    events: Vec<TraceEvent>,
}

const T0: f64 = 1_800_000_000.0;
const RUN: &str = "demo-orders-0";
const PROJECT: &str = "dev-0000-orders";

fn ev(kind: &str, ts: f64) -> TraceEvent {
    TraceEvent {
        run_id: RUN.into(),
        ts,
        kind: kind.into(),
        caller: "dispatch".into(),
        ok: true,
        attempt: 1,
        mode: Some("specialists".into()),
        project_id: Some(PROJECT.into()),
        ..Default::default()
    }
}

impl Demo {
    pub fn new() -> Demo {
        let mut events = Vec::new();
        let mut t = T0;
        // manager plans
        let mut llm = ev("llm", t + 0.8);
        llm.callee = "manager".into();
        llm.model = Some("Qwen3-1.7B+manager".into());
        llm.input_tokens = 612;
        llm.output_tokens = 488;
        llm.latency_ms = 800.0;
        events.push(llm);
        t += 0.8;
        let mut plan = ev("plan", t);
        plan.callee = "manager".into();
        plan.adapter = Some("manager".into());
        plan.output = Some(TASKS.len().to_string());
        events.push(plan);

        let levels = TASKS.iter().map(|x| x.level).max().unwrap_or(0);
        for level in 0..=levels {
            let start = t + 0.05;
            let mut end = start;
            for (i, task) in TASKS.iter().filter(|x| x.level == level).enumerate() {
                let adapter = format!("spec-{}", task.domain);
                let s = start + i as f64 * 0.04;
                let mut r = ev("route", s);
                r.callee = adapter.clone();
                r.task_id = Some(task.id.into());
                r.domain = Some(task.domain.into());
                r.dep_level = Some(level);
                r.adapter = Some(adapter.clone());
                r.t_start = Some(s);
                events.push(r);
                let e = s + task.secs;
                let mut l = ev("llm", e - 0.01);
                l.callee = adapter.clone();
                l.model = Some(format!("Qwen3-0.6B+{adapter}"));
                l.input_tokens = 900 + 37 * i as u64;
                l.output_tokens = 300 + (task.secs * 210.0) as u64;
                l.latency_ms = task.secs * 1000.0;
                l.task_id = Some(task.id.into());
                l.domain = Some(task.domain.into());
                events.push(l);
                let mut k = ev("task", e);
                k.callee = adapter.clone();
                k.task_id = Some(task.id.into());
                k.domain = Some(task.domain.into());
                k.dep_level = Some(level);
                k.adapter = Some(adapter);
                k.t_start = Some(s);
                k.t_end = Some(e);
                k.ok = task.ok;
                if task.ok {
                    k.output = Some("ok".into());
                } else {
                    let msg = "missing provide token: @router.get(\"/api/line_items/{item_id}\")";
                    k.output = Some(msg.into());
                    k.error = Some(msg.into());
                }
                events.push(k);
                end = end.max(e);
            }
            t = end;
        }
        let mut f = ev("final", t + 0.3);
        f.callee = "integrator".into();
        f.t_start = Some(T0);
        f.t_end = Some(t + 0.3);
        f.output = Some("fail:endpoint GET /api/line_items/{item_id}".into());
        events.push(f);
        events.sort_by(|a, b| a.ts.total_cmp(&b.ts));
        Demo { started: Instant::now(), offset: 0.0, events }
    }

    pub fn restart(&mut self) {
        self.started = Instant::now();
        self.offset = 0.0;
    }

    /// Jump ahead (tests, screenshots and `--print`).
    pub fn skip(&mut self, secs: f64) {
        self.offset += secs;
    }

    /// The run as a live trace would look right now.
    pub fn snapshot(&self) -> Run {
        let now = T0 + self.offset + self.started.elapsed().as_secs_f64();
        let mut run = Run { id: RUN.into(), ..Default::default() };
        run.events = self.events.iter().filter(|e| e.ts <= now).cloned().collect();
        run
    }
}
