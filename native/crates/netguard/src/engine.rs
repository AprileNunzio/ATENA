use serde::Serialize;

use crate::detect::{Alert, Detector, Thresholds};
use crate::flows::{FlowRow, FlowTable, Talker};
use std::collections::HashSet;

use crate::packet::{self, Packet, Payload};

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
    pub ignored: u64,
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
    ignored: u64,
    own: HashSet<[u8; 6]>,
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
            ignored: 0,
            own: HashSet::new(),
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
        if !self.relevant(&parsed) {
            self.ignored = self.ignored.saturating_add(1);
            return Vec::new();
        }
        if let Payload::Ip(ip) = &parsed.payload {
            self.flows.record(ip, parsed.length, now_ms);
        }
        let outgoing = self.own.contains(&parsed.src_mac);
        self.detector.inspect_from(&parsed, now_ms, outgoing)
    }

    pub fn own_macs(&mut self, macs: &[[u8; 6]]) {
        for mac in macs {
            self.own.insert(*mac);
            self.detector.trust_mac(*mac);
        }
    }

    fn relevant(&self, packet: &Packet) -> bool {
        if packet.src_mac == [0; 6] && packet.dst_mac == [0; 6] {
            return false;
        }
        if let Payload::Ip(ip) = &packet.payload {
            if ip.src.is_loopback() || ip.dst.is_loopback() {
                return false;
            }
        }
        let group = packet.dst_mac.first().is_some_and(|b| b & 1 == 1);
        self.own.is_empty()
            || group
            || self.own.contains(&packet.src_mac)
            || self.own.contains(&packet.dst_mac)
    }

    pub fn summary(&mut self, now_ms: u64, limit: usize) -> Summary {
        self.flows.expire(now_ms);
        Summary {
            at_ms: now_ms,
            packets: self.packets,
            bytes: self.bytes,
            undecoded: self.undecoded,
            ignored: self.ignored,
            flows: self.flows.len(),
            dropped_flows: self.flows.dropped(),
            top_flows: self.flows.top(limit),
            top_talkers: self.flows.talkers(limit),
        }
    }
}
