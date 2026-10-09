use std::collections::HashMap;
use std::net::IpAddr;

use serde::Serialize;

use crate::packet::{Ip, TCP, UDP};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
pub struct FlowKey {
    pub src: IpAddr,
    pub dst: IpAddr,
    pub protocol: u8,
    pub src_port: u16,
    pub dst_port: u16,
}

impl FlowKey {
    #[must_use]
    pub fn of(ip: &Ip) -> Self {
        let ports = ip.protocol == TCP || ip.protocol == UDP;
        Self {
            src: ip.src,
            dst: ip.dst,
            protocol: ip.protocol,
            src_port: if ports { ip.src_port } else { 0 },
            dst_port: if ports { ip.dst_port } else { 0 },
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct FlowStats {
    pub packets: u64,
    pub bytes: u64,
    pub first_ms: u64,
    pub last_ms: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct FlowRow {
    #[serde(flatten)]
    pub key: FlowKey,
    #[serde(flatten)]
    pub stats: FlowStats,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct Talker {
    pub host: IpAddr,
    pub bytes_out: u64,
    pub bytes_in: u64,
    pub flows: u64,
}

#[derive(Debug)]
pub struct FlowTable {
    flows: HashMap<FlowKey, FlowStats>,
    capacity: usize,
    idle_ms: u64,
    dropped: u64,
}

impl FlowTable {
    #[must_use]
    pub fn new(capacity: usize, idle_ms: u64) -> Self {
        Self {
            flows: HashMap::with_capacity(capacity.min(65_536)),
            capacity: capacity.max(1),
            idle_ms,
            dropped: 0,
        }
    }

    pub fn record(&mut self, ip: &Ip, length: u32, now_ms: u64) {
        let key = FlowKey::of(ip);
        if !self.flows.contains_key(&key) && self.flows.len() >= self.capacity {
            self.expire(now_ms);
            if self.flows.len() >= self.capacity {
                self.dropped = self.dropped.saturating_add(1);
                return;
            }
        }
        let stats = self.flows.entry(key).or_insert(FlowStats {
            packets: 0,
            bytes: 0,
            first_ms: now_ms,
            last_ms: now_ms,
        });
        stats.packets = stats.packets.saturating_add(1);
        stats.bytes = stats.bytes.saturating_add(u64::from(length));
        stats.last_ms = stats.last_ms.max(now_ms);
    }

    pub fn expire(&mut self, now_ms: u64) -> usize {
        let before = self.flows.len();
        let idle = self.idle_ms;
        self.flows
            .retain(|_, s| now_ms.saturating_sub(s.last_ms) <= idle);
        before.saturating_sub(self.flows.len())
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.flows.len()
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.flows.is_empty()
    }

    #[must_use]
    pub fn dropped(&self) -> u64 {
        self.dropped
    }

    #[must_use]
    pub fn top(&self, limit: usize) -> Vec<FlowRow> {
        let mut rows: Vec<FlowRow> = self
            .flows
            .iter()
            .map(|(k, s)| FlowRow { key: *k, stats: *s })
            .collect();
        rows.sort_by_key(|row| std::cmp::Reverse(row.stats.bytes));
        rows.truncate(limit);
        rows
    }

    #[must_use]
    pub fn talkers(&self, limit: usize) -> Vec<Talker> {
        let mut hosts: HashMap<IpAddr, Talker> = HashMap::new();
        for (key, stats) in &self.flows {
            let out = hosts.entry(key.src).or_insert(Talker {
                host: key.src,
                bytes_out: 0,
                bytes_in: 0,
                flows: 0,
            });
            out.bytes_out = out.bytes_out.saturating_add(stats.bytes);
            out.flows = out.flows.saturating_add(1);
            let into = hosts.entry(key.dst).or_insert(Talker {
                host: key.dst,
                bytes_out: 0,
                bytes_in: 0,
                flows: 0,
            });
            into.bytes_in = into.bytes_in.saturating_add(stats.bytes);
        }
        let mut rows: Vec<Talker> = hosts.into_values().collect();
        rows.sort_by(|a, b| {
            b.bytes_out
                .saturating_add(b.bytes_in)
                .cmp(&a.bytes_out.saturating_add(a.bytes_in))
        });
        rows.truncate(limit);
        rows
    }
}
