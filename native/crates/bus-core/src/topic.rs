use std::fmt;

pub const MAX_DEPTH: usize = 8;
pub const MAX_SEGMENT_LEN: usize = 40;
pub const MAX_ORIGIN_LEN: usize = 64;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TopicError {
    InvalidTopic,
    InvalidPattern,
}

impl fmt::Display for TopicError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::InvalidTopic => "invalid topic",
            Self::InvalidPattern => "invalid topic pattern",
        })
    }
}

impl std::error::Error for TopicError {}

fn segment_byte(b: u8) -> bool {
    b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-'
}

fn valid_segment(segment: &str) -> bool {
    (1..=MAX_SEGMENT_LEN).contains(&segment.len()) && segment.bytes().all(segment_byte)
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Topic(Box<[Box<str>]>);

impl Topic {
    pub fn parse(raw: &str) -> Result<Self, TopicError> {
        let segments: Vec<Box<str>> = raw.split('.').map(Box::from).collect();
        if segments.len() > MAX_DEPTH || !segments.iter().all(|s| valid_segment(s)) {
            return Err(TopicError::InvalidTopic);
        }
        Ok(Self(segments.into_boxed_slice()))
    }

    #[must_use]
    pub fn segments(&self) -> &[Box<str>] {
        &self.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Segment {
    Literal(Box<str>),
    Star,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Pattern {
    segments: Box<[Segment]>,
    tail: bool,
}

impl Pattern {
    pub fn parse(raw: &str) -> Result<Self, TopicError> {
        if raw == ">" {
            return Ok(Self {
                segments: Box::new([]),
                tail: true,
            });
        }
        let mut parts: Vec<&str> = raw.split('.').collect();
        let tail = parts.last() == Some(&">");
        if tail {
            parts.pop();
        }
        if parts.is_empty() || parts.len() > MAX_DEPTH {
            return Err(TopicError::InvalidPattern);
        }
        let segments = parts
            .into_iter()
            .map(|part| match part {
                "*" => Ok(Segment::Star),
                literal if valid_segment(literal) => Ok(Segment::Literal(Box::from(literal))),
                _ => Err(TopicError::InvalidPattern),
            })
            .collect::<Result<Box<[Segment]>, TopicError>>()?;
        Ok(Self { segments, tail })
    }

    #[must_use]
    pub fn segments(&self) -> &[Segment] {
        &self.segments
    }

    #[must_use]
    pub fn tail(&self) -> bool {
        self.tail
    }

    #[must_use]
    pub fn matches(&self, topic: &Topic) -> bool {
        let have = topic.segments();
        let fixed = self.segments.len();
        let length_ok = if self.tail {
            have.len() > fixed
        } else {
            have.len() == fixed
        };
        length_ok
            && self
                .segments
                .iter()
                .zip(have)
                .all(|(want, got)| match want {
                    Segment::Star => true,
                    Segment::Literal(literal) => literal == got,
                })
    }
}

#[must_use]
pub fn valid_topic(raw: &str) -> bool {
    Topic::parse(raw).is_ok()
}

#[must_use]
pub fn valid_pattern(raw: &str) -> bool {
    Pattern::parse(raw).is_ok()
}

#[must_use]
pub fn valid_origin(raw: &str) -> bool {
    (1..=MAX_ORIGIN_LEN).contains(&raw.len()) && raw.bytes().all(|b| segment_byte(b) || b == b'.')
}

#[must_use]
pub fn matches(pattern: &str, topic: &str) -> bool {
    match (Pattern::parse(pattern), Topic::parse(topic)) {
        (Ok(p), Ok(t)) => p.matches(&t),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wildcards() {
        assert!(matches("nvr.event.*", "nvr.event.garden"));
        assert!(!matches("nvr.event.*", "nvr.event.garden.extra"));
        assert!(matches("nvr.>", "nvr.event.garden.extra"));
        assert!(!matches("nvr.>", "nvr"));
        assert!(matches(">", "a.b"));
        assert!(matches(">", "a"));
        assert!(matches("a.b", "a.b"));
        assert!(!matches("a.b", "a.c"));
        assert!(!matches("a.b", "a"));
    }

    #[test]
    fn pattern_validation() {
        for good in [
            "nvr.>",
            "a.*.c",
            ">",
            "system.module.nvr",
            "*",
            "a.b.c.d.e.f.g.h.>",
        ] {
            assert!(valid_pattern(good), "{good}");
        }
        for bad in [
            "",
            "nvr.>.x",
            "NVR",
            "a..b",
            "a.b c",
            "../etc",
            ".>",
            "a.>.>",
            "a.b.c.d.e.f.g.h.i",
            "a.**",
        ] {
            assert!(!valid_pattern(bad), "{bad}");
        }
    }

    #[test]
    fn topic_validation() {
        assert!(valid_topic("home.light-1.on_off"));
        assert!(valid_topic(&"x".repeat(MAX_SEGMENT_LEN)));
        for bad in [
            "",
            "Bad",
            "a..b",
            "a.*",
            "a.>",
            ".a",
            "a.",
            "a.b.c.d.e.f.g.h.i",
            "è",
        ] {
            assert!(!valid_topic(bad), "{bad}");
        }
        assert!(!valid_topic(&"x".repeat(MAX_SEGMENT_LEN + 1)));
    }

    #[test]
    fn origin_validation() {
        assert!(valid_origin("supervisor"));
        assert!(valid_origin("node.kitchen-1"));
        assert!(!valid_origin(""));
        assert!(!valid_origin("Upper"));
        assert!(!valid_origin(&"o".repeat(MAX_ORIGIN_LEN + 1)));
    }
}
