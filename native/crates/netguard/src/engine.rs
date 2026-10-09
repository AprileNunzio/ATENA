use serde::Serialize;

use crate::detect::{Alert, Detector, Thresholds};
use crate::flows::{FlowRow, FlowTable, Talker};
use crate::packet::{self, Payload};

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Event {
    Alert(Alert),
    Summary(Summary),
}

#[derive(Debug, Clone, Serialize)]
pub struct Summary {
    pub at_ms: u64,
    pub packets: u64,
    pub bytes: u64,
    pub undecoded: u64,
    pub flows: usize,
    pub dropped_flows: u64,
    pub top_flows: Vec<FlowRow>,
    pub top_talkers: Vec<Talker>,
}

#[derive(Debug)]
pub struct Engine {
    detector: Detector,
    flows: FlowTable,
    packets: u64,
    bytes: u64,
    undecoded: u64,
    last_prune: u64,
}

impl Engine {
    #[must_use]
    pub fn new(limits: Thresholds, max_flows: usize, idle_ms: u64) -> Self {
        Self {
            detector: Detector::new(limits),
            flows: FlowTable::new(max_flows, idle_ms),
            packets: 0,
            bytes: 0,
            undecoded: 0,
            last_prune: 0,
        }
    }

    pub fn detector(&mut self) -> &mut Detector {
        &mut self.detector
    }

    pub fn feed(&mut self, frame: &[u8], now_ms: u64) -> Vec<Alert> {
        self.packets = self.packets.saturating_add(1);
        self.bytes = self
            .bytes
            .saturating_add(u64::try_from(frame.len()).unwrap_or(u64::MAX));
        if now_ms.saturating_sub(self.last_prune) >= 1_000 {
            self.detector.prune(now_ms);
            self.last_prune = now_ms;
        }
        let Some(parsed) = packet::parse(frame) else {
            self.undecoded = self.undecoded.saturating_add(1);
            return Vec::new();
        };
        if let Payload::Ip(ip) = &parsed.payload {
            self.flows.record(ip, parsed.length, now_ms);
        }
        self.detector.inspect(&parsed, now_ms)
    }

    pub fn summary(&mut self, now_ms: u64, limit: usize) -> Summary {
        self.flows.expire(now_ms);
        Summary {
            at_ms: now_ms,
            packets: self.packets,
            bytes: self.bytes,
            undecoded: self.undecoded,
            flows: self.flows.len(),
            dropped_flows: self.flows.dropped(),
            top_flows: self.flows.top(limit),
            top_talkers: self.flows.talkers(limit),
        }
    }
}
