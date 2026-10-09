use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

pub const TCP: u8 = 6;
pub const UDP: u8 = 17;
pub const ICMP: u8 = 1;
pub const ICMP6: u8 = 58;

const ETH_HEADER: usize = 14;
const VLAN_TAG: usize = 4;
const IPV6_HEADER: usize = 40;
const DNS_HEADER: usize = 12;
const MAX_DNS_NAME: usize = 253;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct TcpFlags(pub u8);

impl TcpFlags {
    #[must_use]
    pub fn syn(self) -> bool {
        self.0 & 0x02 != 0
    }

    #[must_use]
    pub fn ack(self) -> bool {
        self.0 & 0x10 != 0
    }

    #[must_use]
    pub fn rst(self) -> bool {
        self.0 & 0x04 != 0
    }

    #[must_use]
    pub fn opening(self) -> bool {
        self.syn() && !self.ack()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Arp {
    pub operation: u16,
    pub sender_mac: [u8; 6],
    pub sender_ip: Ipv4Addr,
    pub target_ip: Ipv4Addr,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ip {
    pub src: IpAddr,
    pub dst: IpAddr,
    pub protocol: u8,
    pub src_port: u16,
    pub dst_port: u16,
    pub flags: TcpFlags,
    pub dns_query: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Payload {
    Ip(Ip),
    Arp(Arp),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Packet {
    pub src_mac: [u8; 6],
    pub length: u32,
    pub payload: Payload,
}

fn slice(buf: &[u8], start: usize, len: usize) -> Option<&[u8]> {
    buf.get(start..start.checked_add(len)?)
}

fn byte(buf: &[u8], at: usize) -> Option<u8> {
    buf.get(at).copied()
}

fn u16_at(buf: &[u8], at: usize) -> Option<u16> {
    let raw = slice(buf, at, 2)?;
    Some(u16::from_be_bytes([*raw.first()?, *raw.get(1)?]))
}

fn mac_at(buf: &[u8], at: usize) -> Option<[u8; 6]> {
    slice(buf, at, 6)?.try_into().ok()
}

fn ipv4_at(buf: &[u8], at: usize) -> Option<Ipv4Addr> {
    let raw: [u8; 4] = slice(buf, at, 4)?.try_into().ok()?;
    Some(Ipv4Addr::from(raw))
}

fn ipv6_at(buf: &[u8], at: usize) -> Option<Ipv6Addr> {
    let raw: [u8; 16] = slice(buf, at, 16)?.try_into().ok()?;
    Some(Ipv6Addr::from(raw))
}

#[must_use]
pub fn parse(frame: &[u8]) -> Option<Packet> {
    let src_mac = mac_at(frame, 6)?;
    let mut ethertype = u16_at(frame, 12)?;
    let mut offset = ETH_HEADER;
    while ethertype == 0x8100 || ethertype == 0x88a8 {
        ethertype = u16_at(frame, offset.checked_add(2)?)?;
        offset = offset.checked_add(VLAN_TAG)?;
    }
    let body = frame.get(offset..)?;
    let payload = match ethertype {
        0x0800 => Payload::Ip(ipv4(body)?),
        0x86dd => Payload::Ip(ipv6(body)?),
        0x0806 => Payload::Arp(arp(body)?),
        _ => return None,
    };
    let length = u32::try_from(frame.len()).unwrap_or(u32::MAX);
    Some(Packet {
        src_mac,
        length,
        payload,
    })
}

fn ipv4(body: &[u8]) -> Option<Ip> {
    let first = byte(body, 0)?;
    if first >> 4 != 4 {
        return None;
    }
    let header = usize::from(first & 0x0f).checked_mul(4)?;
    if header < 20 {
        return None;
    }
    let protocol = byte(body, 9)?;
    let src = IpAddr::V4(ipv4_at(body, 12)?);
    let dst = IpAddr::V4(ipv4_at(body, 16)?);
    let fragment = u16_at(body, 6)? & 0x1fff;
    let transport = if fragment == 0 {
        body.get(header..)
    } else {
        None
    };
    Some(transport_layer(
        src,
        dst,
        protocol,
        transport.unwrap_or_default(),
    ))
}

fn ipv6(body: &[u8]) -> Option<Ip> {
    if byte(body, 0)? >> 4 != 6 {
        return None;
    }
    let protocol = byte(body, 6)?;
    let src = IpAddr::V6(ipv6_at(body, 8)?);
    let dst = IpAddr::V6(ipv6_at(body, 24)?);
    Some(transport_layer(
        src,
        dst,
        protocol,
        body.get(IPV6_HEADER..).unwrap_or_default(),
    ))
}

fn transport_layer(src: IpAddr, dst: IpAddr, protocol: u8, segment: &[u8]) -> Ip {
    let mut ip = Ip {
        src,
        dst,
        protocol,
        src_port: 0,
        dst_port: 0,
        flags: TcpFlags::default(),
        dns_query: None,
    };
    if protocol == TCP || protocol == UDP {
        ip.src_port = u16_at(segment, 0).unwrap_or(0);
        ip.dst_port = u16_at(segment, 2).unwrap_or(0);
    }
    if protocol == TCP {
        ip.flags = TcpFlags(byte(segment, 13).unwrap_or(0));
    }
    if protocol == UDP && ip.dst_port == 53 {
        ip.dns_query = segment.get(8..).and_then(dns_query);
    }
    ip
}

fn arp(body: &[u8]) -> Option<Arp> {
    if u16_at(body, 2)? != 0x0800 || byte(body, 4)? != 6 || byte(body, 5)? != 4 {
        return None;
    }
    Some(Arp {
        operation: u16_at(body, 6)?,
        sender_mac: mac_at(body, 8)?,
        sender_ip: ipv4_at(body, 14)?,
        target_ip: ipv4_at(body, 24)?,
    })
}

#[must_use]
pub fn dns_query(message: &[u8]) -> Option<String> {
    let flags = u16_at(message, 2)?;
    if flags & 0x8000 != 0 || u16_at(message, 4)? == 0 {
        return None;
    }
    let mut at = DNS_HEADER;
    let mut name = String::new();
    loop {
        let len = usize::from(byte(message, at)?);
        if len == 0 {
            break;
        }
        if len > 63 {
            return None;
        }
        let label = slice(message, at.checked_add(1)?, len)?;
        if !name.is_empty() {
            name.push('.');
        }
        name.extend(label.iter().map(|b| char::from(b.to_ascii_lowercase())));
        if name.len() > MAX_DNS_NAME {
            return None;
        }
        at = at.checked_add(len)?.checked_add(1)?;
    }
    (!name.is_empty()).then_some(name)
}
