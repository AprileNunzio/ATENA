use std::fmt;

pub const HEAD_LIMIT: usize = 16 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Target {
    pub tunnel: bool,
    pub host: String,
    pub port: u16,
    pub forwarded: Vec<u8>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ParseError;

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("malformed proxy request")
    }
}

impl std::error::Error for ParseError {}

#[must_use]
pub fn head_end(buffer: &[u8]) -> Option<usize> {
    buffer
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .and_then(|i| i.checked_add(4))
}

pub fn parse(head: &[u8]) -> Result<Target, ParseError> {
    let text = std::str::from_utf8(head).map_err(|_| ParseError)?;
    let (line, rest) = text.split_once("\r\n").ok_or(ParseError)?;
    let parts: Vec<&str> = line.split_ascii_whitespace().collect();
    let [method, target, version] = parts.as_slice() else {
        return Err(ParseError);
    };
    if !version.starts_with("HTTP/1.") || !method.bytes().all(|b| b.is_ascii_alphabetic()) {
        return Err(ParseError);
    }
    if method.eq_ignore_ascii_case("CONNECT") {
        let (host, port) = split_authority(target)?;
        return Ok(Target {
            tunnel: true,
            host,
            port,
            forwarded: Vec::new(),
        });
    }
    let (host, port, path) = split_absolute_url(target)?;
    let mut forwarded =
        format!("{} {path} {version}\r\n", method.to_ascii_uppercase()).into_bytes();
    for header in rest.split("\r\n").filter(|h| !h.is_empty()) {
        let lower = header.to_ascii_lowercase();
        if !lower.starts_with("proxy-") && !lower.starts_with("connection:") {
            forwarded.extend_from_slice(header.as_bytes());
            forwarded.extend_from_slice(b"\r\n");
        }
    }
    forwarded.extend_from_slice(b"Connection: close\r\n\r\n");
    Ok(Target {
        tunnel: false,
        host,
        port,
        forwarded,
    })
}

fn split_authority(authority: &str) -> Result<(String, u16), ParseError> {
    if authority.contains('@') || authority.is_empty() {
        return Err(ParseError);
    }
    let (host, port) = match authority.rsplit_once(':') {
        Some((host, port)) if !host.contains(':') || host.ends_with(']') => (host, Some(port)),
        _ => (authority, None),
    };
    let port = match port {
        Some(raw) if !raw.is_empty() && raw.bytes().all(|b| b.is_ascii_digit()) => {
            raw.parse().map_err(|_| ParseError)?
        }
        Some(_) => return Err(ParseError),
        None => 0,
    };
    let host = host
        .trim_start_matches('[')
        .trim_end_matches(']')
        .to_ascii_lowercase();
    if host.is_empty() || host.len() > 253 {
        return Err(ParseError);
    }
    Ok((host, port))
}

fn split_absolute_url(target: &str) -> Result<(String, u16, String), ParseError> {
    let scheme_end = target.find("://").ok_or(ParseError)?;
    let (scheme, rest) = (
        target.get(..scheme_end).ok_or(ParseError)?,
        target
            .get(scheme_end.saturating_add(3)..)
            .ok_or(ParseError)?,
    );
    if !scheme.eq_ignore_ascii_case("http") {
        return Err(ParseError);
    }
    let rest = rest.split_once('#').map_or(rest, |(before, _)| before);
    let path_start = rest.find(['/', '?']).unwrap_or(rest.len());
    let (authority, tail) = rest.split_at(path_start);
    let (host, port) = split_authority(authority)?;
    let path = match tail {
        "" => "/".to_owned(),
        t if t.starts_with('?') => format!("/{t}"),
        t => t.to_owned(),
    };
    Ok((host, if port == 0 { 80 } else { port }, path))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn connect() {
        let target = parse(b"CONNECT api.example.com:443 HTTP/1.1\r\nHost: x\r\n\r\n");
        assert_eq!(
            target.map(|t| (t.tunnel, t.host, t.port)),
            Ok((true, "api.example.com".to_owned(), 443))
        );
    }

    #[test]
    fn absolute_url_becomes_origin_form_without_proxy_headers() {
        let raw = b"GET http://API.example.com/v1/x?y=1#frag HTTP/1.1\r\nHost: api.example.com\r\nProxy-Connection: keep-alive\r\nConnection: keep-alive\r\nAccept: */*\r\n\r\n";
        let Ok(target) = parse(raw) else {
            unreachable!("valid request rejected");
        };
        assert_eq!(
            (target.tunnel, target.host.as_str(), target.port),
            (false, "api.example.com", 80)
        );
        let forwarded = String::from_utf8_lossy(&target.forwarded);
        assert!(forwarded.starts_with("GET /v1/x?y=1 HTTP/1.1\r\n"));
        assert!(!forwarded.contains("Proxy-"));
        assert!(!forwarded.contains("keep-alive"));
        assert!(forwarded.ends_with("Accept: */*\r\nConnection: close\r\n\r\n"));
    }

    #[test]
    fn explicit_port_and_query_only_path() {
        let target = parse(b"GET http://a.example.com:8080?q=1 HTTP/1.0\r\n\r\n");
        assert_eq!(target.as_ref().map(|t| t.port), Ok(8080));
        assert!(target.is_ok_and(|t| t.forwarded.starts_with(b"GET /?q=1 HTTP/1.0\r\n")));
    }

    #[test]
    fn rejects_malformed_and_non_http() {
        for head in [
            &b"garbage\r\n\r\n"[..],
            b"GET /relative HTTP/1.1\r\n\r\n",
            b"GET ftp://x.com/ HTTP/1.1\r\n\r\n",
            b"A B\r\n\r\n",
            b"CONNECT a.com:x HTTP/1.1\r\n\r\n",
            b"CONNECT a.com:99999 HTTP/1.1\r\n\r\n",
            b"GET http://user:pw@a.com/ HTTP/1.1\r\n\r\n",
            b"GET http://a.com/ SPDY/3\r\n\r\n",
            b"\xff\xfe http://a.com/ HTTP/1.1\r\n\r\n",
        ] {
            assert_eq!(
                parse(head),
                Err(ParseError),
                "{}",
                String::from_utf8_lossy(head)
            );
        }
    }

    #[test]
    fn finds_the_end_of_the_head() {
        assert_eq!(head_end(b"GET / HTTP/1.1\r\n\r\nbody"), Some(18));
        assert_eq!(head_end(b"GET / HTTP/1.1\r\n"), None);
    }
}
