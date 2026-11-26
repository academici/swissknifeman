//! Batching of subscription frames before they go through the Tauri `Channel`.

use std::collections::VecDeque;

pub const MAX_FRAMES: usize = 50;
pub const MAX_AGE_MS: u64 = 50;
pub const QUEUE_LIMIT: usize = 1000;

/// A due batch. `dropped` is the number of frames discarded by overflow since the previous batch; the app sends it as
/// the report frame `{"dropped": N}` before the frames.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Batch {
    pub frames: Vec<String>,
    pub dropped: u64,
}

#[derive(Debug)]
pub struct Batcher {
    max_frames: usize,
    max_age_ms: u64,
    queue_limit: usize,
    queue: VecDeque<(u64, String)>,
    dropped: u64,
}

impl Default for Batcher {
    fn default() -> Self {
        Self::new(MAX_FRAMES, MAX_AGE_MS, QUEUE_LIMIT)
    }
}

impl Batcher {
    pub fn new(max_frames: usize, max_age_ms: u64, queue_limit: usize) -> Self {
        Batcher { max_frames, max_age_ms, queue_limit, queue: VecDeque::new(), dropped: 0 }
    }

    pub fn push(&mut self, frame: String, now_ms: u64) {
        if self.queue.len() >= self.queue_limit {
            self.queue.pop_front();
            self.dropped += 1;
        }
        self.queue.push_back((now_ms, frame));
    }

    /// A batch of up to `max_frames` frames when the queue holds that many or its oldest frame is `max_age_ms` old.
    pub fn poll(&mut self, now_ms: u64) -> Option<Batch> {
        let oldest = self.queue.front()?.0;
        if self.queue.len() < self.max_frames && now_ms.saturating_sub(oldest) < self.max_age_ms {
            return None;
        }
        let take = self.max_frames.min(self.queue.len());
        let frames: Vec<String> = self.queue.drain(..take).map(|(_, f)| f).collect();
        let dropped = std::mem::take(&mut self.dropped);
        Some(Batch { frames, dropped })
    }
}
