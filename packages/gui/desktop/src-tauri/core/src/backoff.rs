//! Restart delays and the restart policy of the sidecar supervisor.

pub const STABLE_MS: u64 = 60_000;
pub const WINDOW_MS: u64 = 300_000;
pub const MAX_RESTARTS: usize = 5;
pub const DELAY_CAP_MS: u64 = 30_000;

/// 500, 1000, 2000, 4000, 8000, 16000, then 30000.
pub fn delay_ms(attempt: u32) -> u64 {
    if attempt >= 6 {
        DELAY_CAP_MS
    } else {
        500u64 << attempt
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Decision {
    Restart { delay_ms: u64 },
    Failed,
}

/// A run of at least 60 s resets the attempt counter; more than 5 exits within 300 s make the state `failed`
/// (sticky until `reset`, which `sidecar_restart` calls).
#[derive(Debug, Default)]
pub struct Policy {
    attempt: u32,
    exits: Vec<u64>,
    failed: bool,
}

impl Policy {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn reset(&mut self) {
        *self = Self::default();
    }

    pub fn attempts(&self) -> u32 {
        self.attempt
    }

    pub fn on_exit(&mut self, started_ms: u64, exited_ms: u64) -> Decision {
        if self.failed {
            return Decision::Failed;
        }
        if exited_ms.saturating_sub(started_ms) >= STABLE_MS {
            self.attempt = 0;
        }
        self.exits.retain(|&t| exited_ms.saturating_sub(t) <= WINDOW_MS);
        self.exits.push(exited_ms);
        if self.exits.len() > MAX_RESTARTS {
            self.failed = true;
            return Decision::Failed;
        }
        let delay = delay_ms(self.attempt);
        self.attempt += 1;
        Decision::Restart { delay_ms: delay }
    }
}
