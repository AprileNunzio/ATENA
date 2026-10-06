use std::collections::{BTreeSet, HashMap};
use std::fmt;

use crate::topic::{Pattern, Segment, Topic, TopicError};

pub const MAX_SUBSCRIPTIONS: usize = 1 << 16;

pub type SubscriptionId = u64;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RouterError {
    Topic(TopicError),
    CapacityExhausted,
}

impl fmt::Display for RouterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Topic(error) => error.fmt(f),
            Self::CapacityExhausted => f.write_str("subscription capacity exhausted"),
        }
    }
}

impl std::error::Error for RouterError {}

impl From<TopicError> for RouterError {
    fn from(error: TopicError) -> Self {
        Self::Topic(error)
    }
}

#[derive(Debug, Default)]
struct Node {
    literals: HashMap<Box<str>, Node>,
    star: Option<Box<Node>>,
    exact: BTreeSet<SubscriptionId>,
    tail: BTreeSet<SubscriptionId>,
}

impl Node {
    fn is_empty(&self) -> bool {
        self.literals.is_empty()
            && self.star.is_none()
            && self.exact.is_empty()
            && self.tail.is_empty()
    }

    fn insert(&mut self, segments: &[Segment], tail: bool, id: SubscriptionId) {
        match segments.split_first() {
            None if tail => {
                self.tail.insert(id);
            }
            None => {
                self.exact.insert(id);
            }
            Some((Segment::Literal(literal), rest)) => {
                self.literals
                    .entry(literal.clone())
                    .or_default()
                    .insert(rest, tail, id);
            }
            Some((Segment::Star, rest)) => {
                self.star
                    .get_or_insert_with(Box::default)
                    .insert(rest, tail, id);
            }
        }
    }

    fn remove(&mut self, segments: &[Segment], tail: bool, id: SubscriptionId) -> bool {
        match segments.split_first() {
            None if tail => self.tail.remove(&id),
            None => self.exact.remove(&id),
            Some((Segment::Literal(literal), rest)) => match self.literals.get_mut(literal) {
                Some(child) => {
                    let removed = child.remove(rest, tail, id);
                    if child.is_empty() {
                        self.literals.remove(literal);
                    }
                    removed
                }
                None => false,
            },
            Some((Segment::Star, rest)) => match self.star.as_deref_mut() {
                Some(child) => {
                    let removed = child.remove(rest, tail, id);
                    if child.is_empty() {
                        self.star = None;
                    }
                    removed
                }
                None => false,
            },
        }
    }

    fn collect(&self, segments: &[Box<str>], out: &mut BTreeSet<SubscriptionId>) {
        let Some((head, rest)) = segments.split_first() else {
            out.extend(&self.exact);
            return;
        };
        out.extend(&self.tail);
        if let Some(child) = self.literals.get(head) {
            child.collect(rest, out);
        }
        if let Some(child) = self.star.as_deref() {
            child.collect(rest, out);
        }
    }
}

#[derive(Debug, Default)]
pub struct TopicRouter {
    root: Node,
    patterns: HashMap<SubscriptionId, Pattern>,
    next_id: SubscriptionId,
}

impl TopicRouter {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    pub fn subscribe(&mut self, raw: &str) -> Result<SubscriptionId, RouterError> {
        let pattern = Pattern::parse(raw)?;
        if self.patterns.len() >= MAX_SUBSCRIPTIONS {
            return Err(RouterError::CapacityExhausted);
        }
        let id = self.next_id;
        self.next_id = id.checked_add(1).ok_or(RouterError::CapacityExhausted)?;
        self.root.insert(pattern.segments(), pattern.tail(), id);
        self.patterns.insert(id, pattern);
        Ok(id)
    }

    pub fn unsubscribe(&mut self, id: SubscriptionId) -> bool {
        self.patterns
            .remove(&id)
            .is_some_and(|pattern| self.root.remove(pattern.segments(), pattern.tail(), id))
    }

    pub fn route(&self, raw: &str) -> Result<Vec<SubscriptionId>, RouterError> {
        let topic = Topic::parse(raw)?;
        Ok(self.route_topic(&topic))
    }

    #[must_use]
    pub fn route_topic(&self, topic: &Topic) -> Vec<SubscriptionId> {
        let mut out = BTreeSet::new();
        self.root.collect(topic.segments(), &mut out);
        out.into_iter().collect()
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.patterns.len()
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.patterns.is_empty()
    }

    #[must_use]
    pub fn pattern(&self, id: SubscriptionId) -> Option<&Pattern> {
        self.patterns.get(&id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::topic::matches;

    fn router(patterns: &[&str]) -> (TopicRouter, Vec<SubscriptionId>) {
        let mut router = TopicRouter::new();
        let ids = patterns
            .iter()
            .map(|p| router.subscribe(p))
            .collect::<Result<Vec<_>, _>>();
        (router, ids.unwrap_or_default())
    }

    #[test]
    fn routes_in_subscription_order() {
        let (router, ids) = router(&[
            "nvr.event.*",
            ">",
            "nvr.>",
            "nvr.event.garden",
            "printers.status",
        ]);
        assert_eq!(ids.len(), 5);
        let routed = router.route("nvr.event.garden");
        let expected: Vec<SubscriptionId> = ids.iter().copied().take(4).collect();
        assert_eq!(routed, Ok(expected));
    }

    #[test]
    fn tail_requires_one_more_segment() {
        let (router, _) = router(&["nvr.>"]);
        assert_eq!(router.route("nvr"), Ok(vec![]));
        assert_eq!(router.route("nvr.a.b.c").map(|v| v.len()), Ok(1));
    }

    #[test]
    fn unsubscribe_prunes_the_trie() {
        let (mut router, ids) = router(&["a.*.c", "a.b.>"]);
        for id in &ids {
            assert!(router.unsubscribe(*id));
            assert!(!router.unsubscribe(*id));
        }
        assert!(router.is_empty());
        assert!(router.root.is_empty());
    }

    #[test]
    fn rejects_invalid_input() {
        let mut router = TopicRouter::new();
        assert_eq!(
            router.subscribe("a..b"),
            Err(RouterError::Topic(TopicError::InvalidPattern))
        );
        assert_eq!(
            router.route("a.*"),
            Err(RouterError::Topic(TopicError::InvalidTopic))
        );
    }

    #[test]
    fn enforces_capacity() {
        let mut router = TopicRouter::new();
        for _ in 0..MAX_SUBSCRIPTIONS {
            assert!(router.subscribe("a.b").is_ok());
        }
        assert_eq!(router.subscribe("a.b"), Err(RouterError::CapacityExhausted));
    }

    #[test]
    fn agrees_with_linear_matching() {
        let patterns = [
            "a", "a.b", "a.*", "*.b", "a.>", "*.>", ">", "a.*.c", "*.*.*", "b.>", "a.b.c",
        ];
        let topics = [
            "a", "b", "a.b", "a.c", "b.b", "a.b.c", "a.x.c", "b.c.d", "a.b.c.d",
        ];
        let (router, ids) = router(&patterns);
        for topic in topics {
            let expected: Vec<SubscriptionId> = patterns
                .iter()
                .zip(&ids)
                .filter(|(p, _)| matches(p, topic))
                .map(|(_, id)| *id)
                .collect();
            assert_eq!(router.route(topic), Ok(expected), "{topic}");
        }
    }
}
