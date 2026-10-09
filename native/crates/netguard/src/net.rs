use std::fmt::Write;
use std::net::IpAddr;

#[must_use]
pub fn internal(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            v4.is_private()
                || v4.is_loopback()
                || v4.is_link_local()
                || v4.is_broadcast()
                || v4.is_multicast()
        }
        IpAddr::V6(v6) => {
            let first = v6.segments().first().copied().unwrap_or(0);
            v6.is_loopback()
                || v6.is_multicast()
                || first & 0xfe00 == 0xfc00
                || first & 0xffc0 == 0xfe80
        }
    }
}

#[must_use]
pub fn mac_text(mac: [u8; 6]) -> String {
    let mut out = String::with_capacity(17);
    for (i, b) in mac.iter().enumerate() {
        if i > 0 {
            out.push(':');
        }
        let _ = write!(out, "{b:02x}");
    }
    out
}

#[must_use]
pub fn parse_mac(text: &str) -> Option<[u8; 6]> {
    let parts: Vec<u8> = text
        .split([':', '-'])
        .map(|p| u8::from_str_radix(p, 16))
        .collect::<Result<_, _>>()
        .ok()?;
    parts.try_into().ok()
}
