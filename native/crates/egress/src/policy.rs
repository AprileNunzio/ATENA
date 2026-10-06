use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

pub const MAX_HOST_LEN: usize = 253;

#[must_use]
pub fn valid_host_pattern(pattern: &str) -> bool {
    let name = pattern.strip_prefix("*.").unwrap_or(pattern);
    let labels: Vec<&str> = name.split('.').collect();
    (1..=MAX_HOST_LEN).contains(&name.len())
        && labels.len() >= 2
        && labels.iter().all(|label| valid_label(label))
        && labels
            .last()
            .is_some_and(|tld| tld.bytes().any(|b| b.is_ascii_lowercase()))
}

fn valid_label(label: &str) -> bool {
    (1..=63).contains(&label.len())
        && label
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        && !label.starts_with('-')
        && !label.ends_with('-')
}

#[must_use]
pub fn host_matches(host: &str, patterns: &[String]) -> bool {
    let host = host.trim_end_matches('.').to_ascii_lowercase();
    patterns
        .iter()
        .any(|pattern| match pattern.strip_prefix('*') {
            Some(suffix) => host.len() > suffix.len() && host.ends_with(suffix),
            None => host == *pattern,
        })
}

#[must_use]
pub fn is_public(address: IpAddr) -> bool {
    match address {
        IpAddr::V4(v4) => public_v4(v4),
        IpAddr::V6(v6) => public_v6(v6),
    }
}

fn in_v4(address: Ipv4Addr, network: [u8; 4], prefix: u32) -> bool {
    let mask = u32::MAX
        .checked_shl(32_u32.saturating_sub(prefix))
        .unwrap_or(0);
    u32::from(address) & mask == u32::from(Ipv4Addr::from(network)) & mask
}

fn public_v4(address: Ipv4Addr) -> bool {
    const BLOCKED: [([u8; 4], u32); 17] = [
        ([0, 0, 0, 0], 8),
        ([10, 0, 0, 0], 8),
        ([100, 64, 0, 0], 10),
        ([127, 0, 0, 0], 8),
        ([169, 254, 0, 0], 16),
        ([172, 16, 0, 0], 12),
        ([192, 0, 0, 0], 24),
        ([192, 0, 2, 0], 24),
        ([192, 31, 196, 0], 24),
        ([192, 52, 193, 0], 24),
        ([192, 88, 99, 0], 24),
        ([192, 168, 0, 0], 16),
        ([192, 175, 48, 0], 24),
        ([198, 18, 0, 0], 15),
        ([198, 51, 100, 0], 24),
        ([203, 0, 113, 0], 24),
        ([224, 0, 0, 0], 3),
    ];
    !BLOCKED
        .iter()
        .any(|(network, prefix)| in_v4(address, *network, *prefix))
}

fn in_v6(address: Ipv6Addr, network: [u16; 8], prefix: u32) -> bool {
    let mask = u128::MAX
        .checked_shl(128_u32.saturating_sub(prefix))
        .unwrap_or(0);
    u128::from(address) & mask == u128::from(Ipv6Addr::from(network)) & mask
}

fn embedded_v4(address: Ipv6Addr) -> Option<Ipv4Addr> {
    let [.., a, b, c, d] = address.octets();
    let tail = Ipv4Addr::new(a, b, c, d);
    let mapped = address.to_ipv4_mapped().is_some();
    let nat64 = in_v6(address, [0x64, 0xff9b, 0, 0, 0, 0, 0, 0], 96)
        || in_v6(address, [0x64, 0xff9b, 1, 0, 0, 0, 0, 0], 48);
    (mapped || nat64).then_some(tail)
}

fn public_v6(address: Ipv6Addr) -> bool {
    const BLOCKED: [([u16; 8], u32); 5] = [
        ([0x2001, 0, 0, 0, 0, 0, 0, 0], 23),
        ([0x2001, 0x0db8, 0, 0, 0, 0, 0, 0], 32),
        ([0x2002, 0, 0, 0, 0, 0, 0, 0], 16),
        ([0x3fff, 0, 0, 0, 0, 0, 0, 0], 20),
        ([0x5f00, 0, 0, 0, 0, 0, 0, 0], 16),
    ];
    if let Some(v4) = embedded_v4(address) {
        return public_v4(v4);
    }
    in_v6(address, [0x2000, 0, 0, 0, 0, 0, 0, 0], 3)
        && !BLOCKED
            .iter()
            .any(|(network, prefix)| in_v6(address, *network, *prefix))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn patterns(raw: &[&str]) -> Vec<String> {
        raw.iter().map(|p| (*p).to_owned()).collect()
    }

    #[test]
    fn exact_and_wildcard_hosts() {
        assert!(host_matches(
            "api.example.com",
            &patterns(&["api.example.com"])
        ));
        assert!(host_matches(
            "API.Example.com.",
            &patterns(&["api.example.com"])
        ));
        assert!(host_matches(
            "a.b.example.com",
            &patterns(&["*.example.com"])
        ));
        assert!(!host_matches("example.com", &patterns(&["*.example.com"])));
        assert!(!host_matches(
            "evilexample.com",
            &patterns(&["*.example.com"])
        ));
        assert!(!host_matches(
            "api.example.com.evil.net",
            &patterns(&["api.example.com"])
        ));
        assert!(!host_matches("anything.org", &[]));
    }

    #[test]
    fn host_pattern_validation() {
        for good in ["api.example.com", "*.github.com", "a-b.co.uk"] {
            assert!(valid_host_pattern(good), "{good}");
        }
        for bad in [
            "localhost",
            "127.0.0.1",
            "*.com",
            "a b.com",
            "x.com/p",
            "*",
            "a..com",
            "-a.com",
            "",
            "A.com",
        ] {
            assert!(!valid_host_pattern(bad), "{bad}");
        }
    }

    #[test]
    fn only_global_addresses_are_public() {
        for good in [
            "93.184.216.34",
            "1.1.1.1",
            "2606:4700:4700::1111",
            "::ffff:93.184.216.34",
        ] {
            assert!(
                is_public(good.parse().unwrap_or(IpAddr::V4(Ipv4Addr::UNSPECIFIED))),
                "{good}"
            );
        }
        for bad in [
            "127.0.0.1",
            "10.0.0.5",
            "192.168.1.9",
            "172.16.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "255.255.255.255",
            "224.0.0.1",
            "198.18.0.1",
            "::1",
            "::",
            "fe80::1",
            "fc00::1",
            "ff02::1",
            "2001:db8::1",
            "::ffff:127.0.0.1",
            "64:ff9b::a00:1",
            "2002:a00:1::1",
        ] {
            assert!(
                !is_public(bad.parse().unwrap_or(IpAddr::V4(Ipv4Addr::UNSPECIFIED))),
                "{bad}"
            );
        }
    }
}
