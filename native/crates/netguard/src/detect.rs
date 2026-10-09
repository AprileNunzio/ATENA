use std::collections::{HashMap, HashSet};
use std::net::{IpAddr, Ipv4Addr};

use serde::{Deserialize, Serialize};

use crate::net::{internal, mac_text};
use crate::packet::{Arp, ICMP, ICMP6, Ip, Packet, Payload, TCP};
use crate::window::{Counter, Distinct};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Low,
    Medium,
    High,
    Critical,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    PortScan,
    HostSweep,
    SynFlood,
    BruteForce,
    ArpSpoof,
    DnsTunnel,
    IcmpFlood,
    Exfiltration,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Alert {
    pub kind: Kind,
    pub severity: Severity,
    pub src: String,
    pub dst: String,
    pub count: u64,
    pub detail: String,
    pub at_ms: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct Thresholds {
    pub scan_ports: u64,
    pub scan_window_ms: u64,
    pub sweep_hosts: u64,
    pub syn_per_second: u64,
    pub brute_attempts: u64,
    pub brute_window_ms: u64,
    pub auth_ports: Vec<u16>,
    pub dns_name_length: usize,
    pub dns_entropy: f64,
    pub icmp_per_second: u64,
    pub exfil_bytes: u64,
    pub exfil_window_ms: u64,
    pub cooldown_ms: u64,
}

impl Default for Thresholds {
    fn default() -> Self {
        Self {
            scan_ports: 25,
            scan_window_ms: 10_000,
            sweep_hosts: 25,
            syn_per_second: 300,
            brute_attempts: 15,
            brute_window_ms: 60_000,
            auth_ports: vec![
                21, 22, 23, 25, 110, 143, 445, 1433, 3306, 3389, 5432, 5900, 8006, 8080, 8443,
            ],
            dns_name_length: 70,
            dns_entropy: 4.0,
            icmp_per_second: 200,
            exfil_bytes: 500 * 1024 * 1024,
            exfil_window_ms: 600_000,
            cooldown_ms: 60_000,
        }
    }
}

#[derive(Debug, Default)]
pub struct Detector {
    limits: Thresholds,
    ports: HashMap<(IpAddr, IpAddr), Distinct<u16>>,
    hosts: HashMap<(IpAddr, u16), Distinct<IpAddr>>,
    syns: HashMap<IpAddr, Counter>,
    logins: HashMap<(IpAddr, IpAddr, u16), Counter>,
    icmp: HashMap<IpAddr, Counter>,
    outbound: HashMap<(IpAddr, IpAddr), Counter>,
    arp: HashMap<Ipv4Addr, [u8; 6]>,
    trusted_macs: HashSet<[u8; 6]>,
    raised: HashMap<(Kind, String), u64>,
}

impl Detector {
    #[must_use]
    pub fn new(limits: Thresholds) -> Self {
        Self {
            limits,
            ..Self::default()
        }
    }

    pub fn trust_mac(&mut self, mac: [u8; 6]) {
        self.trusted_macs.insert(mac);
    }

    pub fn inspect(&mut self, packet: &Packet, now_ms: u64) -> Vec<Alert> {
        self.inspect_from(packet, now_ms, false)
    }

    pub fn inspect_from(&mut self, packet: &Packet, now_ms: u64, outgoing: bool) -> Vec<Alert> {
        let mut alerts = Vec::new();
        match &packet.payload {
            Payload::Arp(arp) if !outgoing => self.arp_check(arp, now_ms, &mut alerts),
            Payload::Arp(_) => {}
            Payload::Ip(ip) if ip.src.is_loopback() || ip.dst.is_loopback() => {}
            Payload::Ip(ip) if outgoing => self.exfil_check(ip, packet.length, now_ms, &mut alerts),
            Payload::Ip(ip) => {
                self.scan_check(ip, now_ms, &mut alerts);
                self.flood_check(ip, now_ms, &mut alerts);
                self.brute_check(ip, now_ms, &mut alerts);
                self.dns_check(ip, now_ms, &mut alerts);
                self.exfil_check(ip, packet.length, now_ms, &mut alerts);
            }
        }
        alerts
    }

    pub fn prune(&mut self, now_ms: u64) {
        let scan = self.limits.scan_window_ms;
        let brute = self.limits.brute_window_ms;
        let exfil = self.limits.exfil_window_ms;
        self.ports.retain(|_, w| !w.stale(now_ms, scan));
        self.hosts.retain(|_, w| !w.stale(now_ms, scan));
        self.syns.retain(|_, w| !w.stale(now_ms, 1_000));
        self.icmp.retain(|_, w| !w.stale(now_ms, 1_000));
        self.logins.retain(|_, w| !w.stale(now_ms, brute));
        self.outbound.retain(|_, w| !w.stale(now_ms, exfil));
        let cooldown = self.limits.cooldown_ms;
        self.raised
            .retain(|_, at| now_ms.saturating_sub(*at) < cooldown);
    }

    fn raise(&mut self, alert: Alert, alerts: &mut Vec<Alert>) {
        let key = (alert.kind, alert.src.clone());
        if let Some(at) = self.raised.get(&key) {
            if alert.at_ms.saturating_sub(*at) < self.limits.cooldown_ms {
                return;
            }
        }
        self.raised.insert(key, alert.at_ms);
        alerts.push(alert);
    }

    fn scan_check(&mut self, ip: &Ip, now_ms: u64, alerts: &mut Vec<Alert>) {
        if ip.protocol != TCP || !ip.flags.opening() {
            return;
        }
        let window = self.limits.scan_window_ms;
        let ports = self
            .ports
            .entry((ip.src, ip.dst))
            .or_insert_with(|| Distinct::new(window))
            .add(ip.dst_port, now_ms);
        if ports >= self.limits.scan_ports {
            let severity = if ports >= self.limits.scan_ports.saturating_mul(4) {
                Severity::High
            } else {
                Severity::Medium
            };
            let detail = format!("{ports} porte diverse provate in {} s", window / 1000);
            self.raise(
                alert(
                    Kind::PortScan,
                    severity,
                    ip.src,
                    ip.dst,
                    ports,
                    detail,
                    now_ms,
                ),
                alerts,
            );
        }
        let hosts = self
            .hosts
            .entry((ip.src, ip.dst_port))
            .or_insert_with(|| Distinct::new(window))
            .add(ip.dst, now_ms);
        if hosts >= self.limits.sweep_hosts {
            let detail = format!("{hosts} dispositivi contattati sulla porta {}", ip.dst_port);
            self.raise(
                alert(
                    Kind::HostSweep,
                    Severity::Medium,
                    ip.src,
                    ip.dst,
                    hosts,
                    detail,
                    now_ms,
                ),
                alerts,
            );
        }
    }

    fn flood_check(&mut self, ip: &Ip, now_ms: u64, alerts: &mut Vec<Alert>) {
        if ip.protocol == TCP && ip.flags.opening() {
            let rate = self
                .syns
                .entry(ip.dst)
                .or_insert_with(|| Counter::new(1_000))
                .add(1, now_ms);
            if rate >= self.limits.syn_per_second {
                let detail = format!("{rate} SYN al secondo verso {}", ip.dst);
                self.raise(
                    alert(
                        Kind::SynFlood,
                        Severity::High,
                        ip.src,
                        ip.dst,
                        rate,
                        detail,
                        now_ms,
                    ),
                    alerts,
                );
            }
        }
        if ip.protocol == ICMP || ip.protocol == ICMP6 {
            let rate = self
                .icmp
                .entry(ip.src)
                .or_insert_with(|| Counter::new(1_000))
                .add(1, now_ms);
            if rate >= self.limits.icmp_per_second {
                let detail = format!("{rate} pacchetti ICMP al secondo");
                self.raise(
                    alert(
                        Kind::IcmpFlood,
                        Severity::Medium,
                        ip.src,
                        ip.dst,
                        rate,
                        detail,
                        now_ms,
                    ),
                    alerts,
                );
            }
        }
    }

    fn brute_check(&mut self, ip: &Ip, now_ms: u64, alerts: &mut Vec<Alert>) {
        if ip.protocol != TCP
            || !ip.flags.opening()
            || !self.limits.auth_ports.contains(&ip.dst_port)
        {
            return;
        }
        let window = self.limits.brute_window_ms;
        let tries = self
            .logins
            .entry((ip.src, ip.dst, ip.dst_port))
            .or_insert_with(|| Counter::new(window))
            .add(1, now_ms);
        if tries >= self.limits.brute_attempts {
            let severity = if internal(ip.src) {
                Severity::High
            } else {
                Severity::Critical
            };
            let detail = format!(
                "{tries} tentativi di accesso sulla porta {} in {} s",
                ip.dst_port,
                window / 1000
            );
            self.raise(
                alert(
                    Kind::BruteForce,
                    severity,
                    ip.src,
                    ip.dst,
                    tries,
                    detail,
                    now_ms,
                ),
                alerts,
            );
        }
    }

    fn dns_check(&mut self, ip: &Ip, now_ms: u64, alerts: &mut Vec<Alert>) {
        let Some(name) = ip.dns_query.as_deref() else {
            return;
        };
        let first = name.split('.').next().unwrap_or_default();
        let suspicious = name.len() >= self.limits.dns_name_length
            || (first.len() >= 24 && entropy(first) >= self.limits.dns_entropy);
        if suspicious {
            let detail = format!(
                "richiesta DNS anomala: {}",
                name.chars().take(120).collect::<String>()
            );
            self.raise(
                alert(
                    Kind::DnsTunnel,
                    Severity::Medium,
                    ip.src,
                    ip.dst,
                    1,
                    detail,
                    now_ms,
                ),
                alerts,
            );
        }
    }

    fn exfil_check(&mut self, ip: &Ip, length: u32, now_ms: u64, alerts: &mut Vec<Alert>) {
        if !internal(ip.src) || internal(ip.dst) {
            return;
        }
        let window = self.limits.exfil_window_ms;
        let sent = self
            .outbound
            .entry((ip.src, ip.dst))
            .or_insert_with(|| Counter::new(window))
            .add(u64::from(length), now_ms);
        if sent >= self.limits.exfil_bytes {
            let detail = format!(
                "{} MB inviati verso l'esterno in {} minuti",
                sent / 1_048_576,
                window / 60_000
            );
            self.raise(
                alert(
                    Kind::Exfiltration,
                    Severity::High,
                    ip.src,
                    ip.dst,
                    sent,
                    detail,
                    now_ms,
                ),
                alerts,
            );
        }
    }

    fn arp_check(&mut self, arp: &Arp, now_ms: u64, alerts: &mut Vec<Alert>) {
        if arp.sender_ip.is_unspecified() {
            return;
        }
        match self.arp.insert(arp.sender_ip, arp.sender_mac) {
            Some(previous)
                if previous != arp.sender_mac && !self.trusted_macs.contains(&arp.sender_mac) =>
            {
                let detail = format!(
                    "{} è passato da {} a {}",
                    arp.sender_ip,
                    mac_text(previous),
                    mac_text(arp.sender_mac)
                );
                let found = alert(
                    Kind::ArpSpoof,
                    Severity::Critical,
                    IpAddr::V4(arp.sender_ip),
                    IpAddr::V4(arp.target_ip),
                    1,
                    detail,
                    now_ms,
                );
                self.raise(
                    Alert {
                        src: mac_text(arp.sender_mac),
                        ..found
                    },
                    alerts,
                );
            }
            _ => {}
        }
    }
}

fn alert(
    kind: Kind,
    severity: Severity,
    src: IpAddr,
    dst: IpAddr,
    count: u64,
    detail: String,
    at_ms: u64,
) -> Alert {
    Alert {
        kind,
        severity,
        src: src.to_string(),
        dst: dst.to_string(),
        count,
        detail,
        at_ms,
    }
}

#[must_use]
pub fn entropy(text: &str) -> f64 {
    let mut counts = [0_u32; 256];
    let mut total = 0_u32;
    for b in text.bytes() {
        if let Some(slot) = counts.get_mut(usize::from(b)) {
            *slot = slot.saturating_add(1);
            total = total.saturating_add(1);
        }
    }
    if total == 0 {
        return 0.0;
    }
    let n = f64::from(total);
    counts
        .iter()
        .filter(|c| **c > 0)
        .map(|c| f64::from(*c) / n)
        .map(|p| -p * p.log2())
        .sum()
}
