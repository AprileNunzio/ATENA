use std::fs;
use std::path::Path;

use serde::Deserialize;

use atena_netguard::detect::Thresholds;
use atena_netguard::net::parse_mac;

#[derive(Debug, Deserialize)]
#[serde(default)]
pub struct Config {
    pub thresholds: Thresholds,
    pub trusted_macs: Vec<String>,
    pub max_flows: usize,
    pub idle_seconds: u64,
    pub summary_seconds: u64,
    pub top: usize,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            thresholds: Thresholds::default(),
            trusted_macs: Vec::new(),
            max_flows: 200_000,
            idle_seconds: 120,
            summary_seconds: 10,
            top: 25,
        }
    }
}

impl Config {
    pub fn load(path: Option<&Path>) -> Result<Self, String> {
        let Some(path) = path else {
            return Ok(Self::default());
        };
        let text = fs::read_to_string(path)
            .map_err(|e| format!("configurazione {}: {e}", path.display()))?;
        serde_json::from_str(&text).map_err(|e| format!("configurazione {}: {e}", path.display()))
    }

    pub fn macs(&self) -> Result<Vec<[u8; 6]>, String> {
        self.trusted_macs
            .iter()
            .map(|m| parse_mac(m).ok_or_else(|| format!("MAC non valido: {m}")))
            .collect()
    }
}
