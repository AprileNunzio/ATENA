use std::collections::HashMap;
use std::fmt;
use std::net::{IpAddr, SocketAddr};
use std::time::Duration;

use serde::Deserialize;

use crate::policy::valid_host_pattern;

pub const MAX_CONFIG_BYTES: usize = 64 * 1024;
pub const MAX_ALLOWED_HOSTS: usize = 8;
pub const MAX_LIFETIME: Duration = Duration::from_secs(3600);
pub const MAX_TRANSFER_BYTES: u64 = 1 << 30;

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub bind: IpAddr,
    pub ports: (u16, u16),
    pub allowed: Vec<String>,
    pub lifetime_ms: u64,
    pub max_bytes: u64,
    #[cfg(feature = "test-hooks")]
    #[serde(default)]
    pub hooks: Option<Hooks>,
}

#[cfg(feature = "test-hooks")]
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Hooks {
    pub resolve: HashMap<String, Vec<IpAddr>>,
    pub upstream: SocketAddr,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConfigError(String);

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for ConfigError {}

fn invalid(message: &str) -> ConfigError {
    ConfigError(message.to_owned())
}

#[derive(Debug, Clone)]
pub enum Resolution {
    System,
    Static(HashMap<String, Vec<IpAddr>>),
}

#[derive(Debug, Clone, Copy)]
pub enum Upstream {
    Direct,
    Fixed(SocketAddr),
}

impl Config {
    pub fn parse(raw: &[u8]) -> Result<Self, ConfigError> {
        if raw.len() > MAX_CONFIG_BYTES {
            return Err(invalid("configuration too large"));
        }
        let config: Self = serde_json::from_slice(raw)
            .map_err(|e| ConfigError(format!("invalid configuration: {e}")))?;
        config.validate()?;
        Ok(config)
    }

    fn validate(&self) -> Result<(), ConfigError> {
        if self.allowed.is_empty() || self.allowed.len() > MAX_ALLOWED_HOSTS {
            return Err(invalid("allowed hosts must be between 1 and 8"));
        }
        if !self.allowed.iter().all(|h| valid_host_pattern(h)) {
            return Err(invalid("invalid allowed host"));
        }
        if self.ports.0 > self.ports.1 {
            return Err(invalid("invalid port range"));
        }
        if self.lifetime_ms == 0 || self.lifetime() > MAX_LIFETIME {
            return Err(invalid("invalid lifetime"));
        }
        if self.max_bytes == 0 || self.max_bytes > MAX_TRANSFER_BYTES {
            return Err(invalid("invalid transfer budget"));
        }
        Ok(())
    }

    #[must_use]
    pub fn lifetime(&self) -> Duration {
        Duration::from_millis(self.lifetime_ms)
    }

    #[must_use]
    pub fn resolution(&self) -> Resolution {
        #[cfg(feature = "test-hooks")]
        if let Some(hooks) = &self.hooks {
            return Resolution::Static(hooks.resolve.clone());
        }
        Resolution::System
    }

    #[must_use]
    pub fn upstream(&self) -> Upstream {
        #[cfg(feature = "test-hooks")]
        if let Some(hooks) = &self.hooks {
            return Upstream::Fixed(hooks.upstream);
        }
        Upstream::Direct
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const GOOD: &str = r#"{"bind":"127.0.0.1","ports":[0,0],"allowed":["api.example.com"],"lifetime_ms":1000,"max_bytes":1024}"#;

    #[test]
    fn accepts_a_valid_configuration() {
        assert!(Config::parse(GOOD.as_bytes()).is_ok());
    }

    #[test]
    fn rejects_invalid_configurations() {
        for bad in [
            GOOD.replace("api.example.com", "localhost"),
            GOOD.replace(r#"["api.example.com"]"#, "[]"),
            GOOD.replace("[0,0]", "[10,5]"),
            GOOD.replace("\"lifetime_ms\":1000", "\"lifetime_ms\":0"),
            GOOD.replace("\"lifetime_ms\":1000", "\"lifetime_ms\":3600001"),
            GOOD.replace("\"max_bytes\":1024", "\"max_bytes\":0"),
            GOOD.replace('}', r#","extra":1}"#),
            "not json".to_owned(),
        ] {
            assert!(Config::parse(bad.as_bytes()).is_err(), "{bad}");
        }
    }

    #[cfg(not(feature = "test-hooks"))]
    #[test]
    fn hooks_do_not_exist_in_production_builds() {
        let hooked = GOOD.replace('}', r#","hooks":{"resolve":{},"upstream":"127.0.0.1:1"}}"#);
        assert!(Config::parse(hooked.as_bytes()).is_err());
    }
}
