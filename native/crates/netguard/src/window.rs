use std::collections::{HashMap, VecDeque};
use std::hash::Hash;

const BUCKETS: u64 = 20;
const MAX_DISTINCT: usize = 4_096;

#[derive(Debug, Default)]
pub struct Counter {
    window: u64,
    bucket: u64,
    slots: VecDeque<(u64, u64)>,
    total: u64,
    last: u64,
}

impl Counter {
    #[must_use]
    pub fn new(window_ms: u64) -> Self {
        let window = window_ms.max(1);
        Self {
            window,
            bucket: (window / BUCKETS).max(1),
            ..Self::default()
        }
    }

    pub fn add(&mut self, value: u64, now_ms: u64) -> u64 {
        self.evict(now_ms);
        let slot = now_ms.checked_div(self.bucket).unwrap_or(now_ms);
        match self.slots.back_mut() {
            Some((at, sum)) if *at == slot => *sum = sum.saturating_add(value),
            _ => self.slots.push_back((slot, value)),
        }
        self.total = self.total.saturating_add(value);
        self.last = self.last.max(now_ms);
        self.total
    }

    fn evict(&mut self, now_ms: u64) {
        let oldest = now_ms
            .saturating_sub(self.window)
            .checked_div(self.bucket)
            .unwrap_or(0);
        while let Some((slot, sum)) = self.slots.front().copied() {
            if slot >= oldest {
                break;
            }
            self.total = self.total.saturating_sub(sum);
            self.slots.pop_front();
        }
    }

    #[must_use]
    pub fn stale(&self, now_ms: u64, idle_ms: u64) -> bool {
        now_ms.saturating_sub(self.last) > idle_ms
    }
}

#[derive(Debug)]
pub struct Distinct<T> {
    window: u64,
    seen: HashMap<T, u64>,
    order: VecDeque<(u64, T)>,
    last: u64,
}

impl<T: Eq + Hash + Copy> Distinct<T> {
    #[must_use]
    pub fn new(window_ms: u64) -> Self {
        Self {
            window: window_ms.max(1),
            seen: HashMap::new(),
            order: VecDeque::new(),
            last: 0,
        }
    }

    pub fn add(&mut self, value: T, now_ms: u64) -> u64 {
        let oldest = now_ms.saturating_sub(self.window);
        while let Some((at, item)) = self.order.front().copied() {
            if at >= oldest && self.order.len() < MAX_DISTINCT {
                break;
            }
            self.order.pop_front();
            if self.seen.get(&item) == Some(&at) {
                self.seen.remove(&item);
            }
        }
        self.seen.insert(value, now_ms);
        self.order.push_back((now_ms, value));
        self.last = self.last.max(now_ms);
        u64::try_from(self.seen.len()).unwrap_or(u64::MAX)
    }

    #[must_use]
    pub fn stale(&self, now_ms: u64, idle_ms: u64) -> bool {
        now_ms.saturating_sub(self.last) > idle_ms
    }
}
