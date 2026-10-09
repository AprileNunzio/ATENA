use std::net::{IpAddr, Ipv4Addr};

use crate::detect::{Detector, Kind, Severity, Thresholds, entropy};
use crate::engine::Engine;
use crate::flows::FlowTable;
use crate::packet::{self, Ip, Payload, TCP, UDP};
use crate::pcap::Reader;

const MAC_A: [u8; 6] = [0x02, 0, 0, 0, 0, 0x0a];
const MAC_B: [u8; 6] = [0x02, 0, 0, 0, 0, 0x0b];

fn ethernet(src_mac: [u8; 6], ethertype: u16, body: &[u8]) -> Vec<u8> {
    let mut frame = vec![0xff; 6];
    frame.extend_from_slice(&src_mac);
    frame.extend_from_slice(&ethertype.to_be_bytes());
    frame.extend_from_slice(body);
    frame
}

fn ipv4(src: [u8; 4], dst: [u8; 4], protocol: u8, transport: &[u8]) -> Vec<u8> {
    let total = u16::try_from(transport.len().saturating_add(20)).unwrap_or(u16::MAX);
    let mut header = vec![0x45, 0];
    header.extend_from_slice(&total.to_be_bytes());
    header.extend_from_slice(&[0, 0, 0x40, 0, 64, protocol, 0, 0]);
    header.extend_from_slice(&src);
    header.extend_from_slice(&dst);
    header.extend_from_slice(transport);
    header
}

fn tcp(src_port: u16, dst_port: u16, flags: u8) -> Vec<u8> {
    let mut segment = Vec::new();
    segment.extend_from_slice(&src_port.to_be_bytes());
    segment.extend_from_slice(&dst_port.to_be_bytes());
    segment.extend_from_slice(&[0, 0, 0, 1, 0, 0, 0, 0, 0x50, flags, 0xff, 0xff, 0, 0, 0, 0]);
    segment
}

fn dns(name: &str) -> Vec<u8> {
    let mut message = vec![0x12, 0x34, 0x01, 0x00, 0, 1, 0, 0, 0, 0, 0, 0];
    for label in name.split('.') {
        message.push(u8::try_from(label.len()).unwrap_or(0));
        message.extend_from_slice(label.as_bytes());
    }
    message.extend_from_slice(&[0, 0, 1, 0, 1]);
    let mut segment = Vec::new();
    segment.extend_from_slice(&40_000_u16.to_be_bytes());
    segment.extend_from_slice(&53_u16.to_be_bytes());
    segment.extend_from_slice(
        &u16::try_from(message.len().saturating_add(8))
            .unwrap_or(0)
            .to_be_bytes(),
    );
    segment.extend_from_slice(&[0, 0]);
    segment.extend_from_slice(&message);
    segment
}

fn arp(sender_mac: [u8; 6], sender_ip: [u8; 4]) -> Vec<u8> {
    let mut body = vec![0, 1, 0x08, 0x00, 6, 4, 0, 2];
    body.extend_from_slice(&sender_mac);
    body.extend_from_slice(&sender_ip);
    body.extend_from_slice(&[0; 6]);
    body.extend_from_slice(&[192, 168, 1, 50]);
    ethernet(sender_mac, 0x0806, &body)
}

fn syn(src: [u8; 4], dst: [u8; 4], port: u16) -> Vec<u8> {
    ethernet(
        MAC_A,
        0x0800,
        &ipv4(src, dst, TCP, &tcp(50_000, port, 0x02)),
    )
}

fn ip_of(frame: &[u8]) -> Option<Ip> {
    match packet::parse(frame)?.payload {
        Payload::Ip(ip) => Some(ip),
        Payload::Arp(_) => None,
    }
}

fn engine() -> Engine {
    Engine::new(Thresholds::default(), 1_000, 60_000)
}

#[test]
fn parses_tcp_over_vlan() {
    let inner = ipv4([10, 0, 0, 1], [10, 0, 0, 2], TCP, &tcp(1234, 443, 0x12));
    let mut body = vec![0x00, 0x05, 0x08, 0x00];
    body.extend_from_slice(&inner);
    let frame = ethernet(MAC_A, 0x8100, &body);
    let ip = ip_of(&frame);
    assert_eq!(
        ip.as_ref()
            .map(|ip| (ip.src_port, ip.dst_port, ip.flags.syn(), ip.flags.ack())),
        Some((1234, 443, true, true))
    );
    assert_eq!(
        ip.map(|ip| ip.dst),
        Some(IpAddr::V4(Ipv4Addr::new(10, 0, 0, 2)))
    );
}

#[test]
fn truncated_and_malformed_frames_never_panic() {
    let good = syn([10, 0, 0, 1], [10, 0, 0, 2], 22);
    for cut in 0..good.len() {
        let _ = packet::parse(good.get(..cut).unwrap_or_default());
    }
    assert!(packet::parse(&ethernet(MAC_A, 0x0800, &[0x4f; 3])).is_none());
    assert!(packet::dns_query(&[0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 200, 1]).is_none());
}

#[test]
fn reads_dns_query_names() {
    let frame = ethernet(
        MAC_A,
        0x0800,
        &ipv4([10, 0, 0, 5], [1, 1, 1, 1], UDP, &dns("Www.Example.com")),
    );
    assert_eq!(
        ip_of(&frame).and_then(|ip| ip.dns_query).as_deref(),
        Some("www.example.com")
    );
}

#[test]
fn port_scan_is_detected_once_per_cooldown() {
    let mut e = engine();
    let mut alerts = Vec::new();
    for port in 1..=60_u16 {
        alerts.extend(e.feed(
            &syn([203, 0, 113, 9], [192, 168, 1, 10], port),
            u64::from(port) * 10,
        ));
    }
    let scans: Vec<_> = alerts.iter().filter(|a| a.kind == Kind::PortScan).collect();
    assert_eq!(scans.len(), 1);
    assert_eq!(scans.first().map(|a| a.src.as_str()), Some("203.0.113.9"));
}

#[test]
fn normal_browsing_raises_nothing() {
    let mut e = engine();
    let mut alerts = Vec::new();
    for i in 0..200_u64 {
        alerts.extend(e.feed(&syn([192, 168, 1, 20], [142, 250, 1, 1], 443), i * 50));
        alerts.extend(e.feed(
            &ethernet(
                MAC_A,
                0x0800,
                &ipv4([192, 168, 1, 20], [1, 1, 1, 1], UDP, &dns("google.com")),
            ),
            i * 50,
        ));
    }
    assert!(alerts.is_empty(), "{alerts:?}");
}

#[test]
fn brute_force_from_internet_is_critical() {
    let mut e = engine();
    let mut found = None;
    for i in 0..20_u64 {
        if let Some(a) = e
            .feed(&syn([198, 51, 100, 7], [192, 168, 1, 10], 22), i * 1_000)
            .into_iter()
            .find(|a| a.kind == Kind::BruteForce)
        {
            found = Some(a);
        }
    }
    assert_eq!(found.map(|a| a.severity), Some(Severity::Critical));
}

#[test]
fn syn_flood_is_detected() {
    let mut e = engine();
    let mut kinds = Vec::new();
    for i in 0..400_u16 {
        let src = [
            100,
            64,
            u8::try_from(i / 256).unwrap_or(0),
            u8::try_from(i % 256).unwrap_or(0),
        ];
        kinds.extend(
            e.feed(&syn(src, [192, 168, 1, 10], 80), 5_000 + u64::from(i) / 2)
                .into_iter()
                .map(|a| a.kind),
        );
    }
    assert!(kinds.contains(&Kind::SynFlood));
}

#[test]
fn arp_spoofing_is_critical_unless_trusted() {
    let mut detector = Detector::new(Thresholds::default());
    let (Some(first), Some(second)) = (
        packet::parse(&arp(MAC_A, [192, 168, 1, 1])),
        packet::parse(&arp(MAC_B, [192, 168, 1, 1])),
    ) else {
        unreachable!("frame ARP di test non decodificati")
    };
    assert!(detector.inspect(&first, 0).is_empty());
    let alerts = detector.inspect(&second, 10);
    assert_eq!(
        alerts.first().map(|a| (a.kind, a.severity)),
        Some((Kind::ArpSpoof, Severity::Critical))
    );
    let mut trusting = Detector::new(Thresholds::default());
    trusting.trust_mac(MAC_B);
    assert!(trusting.inspect(&first, 0).is_empty());
    assert!(trusting.inspect(&second, 10).is_empty());
}

#[test]
fn dns_tunnelling_is_detected() {
    let mut e = engine();
    let name = "a9f3k2l1q8z7x6c5v4b3n2m1p0o9i8u7.y6t5r4e3w2q1.tunnel.example";
    let alerts = e.feed(
        &ethernet(
            MAC_A,
            0x0800,
            &ipv4([192, 168, 1, 30], [8, 8, 8, 8], UDP, &dns(name)),
        ),
        0,
    );
    assert_eq!(alerts.first().map(|a| a.kind), Some(Kind::DnsTunnel));
    assert!(entropy("aaaaaaaa") < 1.0 && entropy("a9f3k2l1q8z7x6c5") > 3.5);
}

#[test]
fn exfiltration_counts_bytes_towards_one_external_host() {
    let limits = Thresholds {
        exfil_bytes: 10_000,
        ..Thresholds::default()
    };
    let mut e = Engine::new(limits, 1_000, 60_000);
    let payload = vec![0_u8; 1_400];
    let mut kinds = Vec::new();
    for i in 0..10_u64 {
        let frame = ethernet(
            MAC_A,
            0x0800,
            &ipv4([192, 168, 1, 40], [203, 0, 113, 50], UDP, &payload),
        );
        kinds.extend(e.feed(&frame, i).into_iter().map(|a| a.kind));
    }
    assert!(kinds.contains(&Kind::Exfiltration));
}

#[test]
fn flow_table_is_bounded_and_ranks_talkers() {
    let mut table = FlowTable::new(2, 1_000);
    for (i, port) in [80_u16, 443, 8080].iter().enumerate() {
        let frame = syn([192, 168, 1, 2], [10, 0, 0, 1], *port);
        if let Some(ip) = ip_of(&frame) {
            table.record(&ip, 100, u64::try_from(i).unwrap_or(0));
        }
    }
    assert_eq!((table.len(), table.dropped()), (2, 1));
    let source = IpAddr::V4(Ipv4Addr::new(192, 168, 1, 2));
    let talkers = table.talkers(5);
    assert_eq!(
        talkers
            .iter()
            .find(|t| t.host == source)
            .map(|t| (t.bytes_out, t.flows)),
        Some((200, 2))
    );
    assert_eq!(table.expire(10_000), 2);
}

#[test]
fn replays_a_pcap_capture() {
    let mut file = vec![
        0xd4, 0xc3, 0xb2, 0xa1, 2, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xff, 0xff, 0, 0, 1, 0, 0, 0,
    ];
    let frame = syn([10, 0, 0, 1], [10, 0, 0, 2], 22);
    let size = u32::try_from(frame.len()).unwrap_or(0).to_le_bytes();
    file.extend_from_slice(&[10, 0, 0, 0, 0x40, 0x42, 0x0f, 0]);
    file.extend_from_slice(&size);
    file.extend_from_slice(&size);
    file.extend_from_slice(&frame);
    let reader = Reader::open(file.as_slice());
    assert!(reader.is_ok());
    let Ok(mut reader) = reader else { return };
    let record = reader.next_record().ok().flatten();
    assert_eq!(
        record.map(|r| (r.at_ms, r.data.len())),
        Some((11_000, frame.len()))
    );
    assert!(matches!(reader.next_record(), Ok(None)));
    assert!(Reader::open(&[0_u8; 24][..]).is_err());
}

const OWN: [u8; 6] = [0x02, 0, 0, 0, 0, 0x01];

fn frame_between(
    src_mac: [u8; 6],
    dst_mac: [u8; 6],
    src: [u8; 4],
    dst: [u8; 4],
    port: u16,
) -> Vec<u8> {
    let mut frame = ethernet(
        src_mac,
        0x0800,
        &ipv4(src, dst, TCP, &tcp(50_000, port, 0x02)),
    );
    if let Some(slot) = frame.get_mut(0..6) {
        slot.copy_from_slice(&dst_mac);
    }
    frame
}

#[test]
fn loopback_traffic_is_never_an_attack() {
    let mut e = engine();
    let mut alerts = Vec::new();
    for port in 1..=200_u16 {
        alerts.extend(e.feed(
            &frame_between([0; 6], [0; 6], [127, 0, 0, 1], [127, 0, 0, 1], port),
            u64::from(port),
        ));
    }
    assert!(alerts.is_empty(), "{alerts:?}");
    assert_eq!(e.summary(1_000, 5).ignored, 200);
}

#[test]
fn outgoing_scans_from_atena_itself_are_not_attacks() {
    let mut e = engine();
    e.own_macs(&[OWN]);
    let mut alerts = Vec::new();
    for port in 1..=200_u16 {
        alerts.extend(e.feed(
            &frame_between(OWN, MAC_B, [192, 168, 1, 10], [192, 168, 1, 20], port),
            u64::from(port),
        ));
    }
    assert!(alerts.is_empty(), "{alerts:?}");
}

#[test]
fn incoming_scans_are_still_detected_and_other_interfaces_ignored() {
    let mut e = engine();
    e.own_macs(&[OWN]);
    let mut incoming = Vec::new();
    let mut foreign = Vec::new();
    for port in 1..=60_u16 {
        incoming.extend(e.feed(
            &frame_between(MAC_A, OWN, [203, 0, 113, 9], [192, 168, 1, 10], port),
            u64::from(port),
        ));
        foreign.extend(e.feed(
            &frame_between(MAC_A, MAC_B, [172, 17, 0, 2], [172, 17, 0, 3], port),
            u64::from(port),
        ));
    }
    assert!(incoming.iter().any(|a| a.kind == Kind::PortScan));
    assert!(foreign.is_empty());
}
