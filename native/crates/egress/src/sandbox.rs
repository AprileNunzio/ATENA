use std::path::Path;

use landlock::{
    ABI, Access, AccessFs, AccessNet, CompatLevel, Compatible, NetPort, Ruleset, RulesetAttr,
    RulesetCreatedAttr, RulesetError, RulesetStatus, Scope, path_beneath_rules,
};

const ABI_TARGET: ABI = ABI::V6;
const READ_ONLY: [&str; 6] = [
    "/etc",
    "/usr",
    "/lib",
    "/lib64",
    "/run/systemd/resolve",
    "/run/nscd",
];
const DNS_PORT: u16 = 53;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Enforcement {
    Full,
    Partial,
    None,
}

impl Enforcement {
    #[must_use]
    pub fn label(self) -> &'static str {
        match self {
            Self::Full => "full",
            Self::Partial => "partial",
            Self::None => "none",
        }
    }
}

pub fn restrict(connect_ports: &[u16]) -> Result<Enforcement, RulesetError> {
    let readable: Vec<&str> = READ_ONLY
        .into_iter()
        .filter(|p| Path::new(p).exists())
        .collect();
    let mut ruleset = Ruleset::default()
        .set_compatibility(CompatLevel::BestEffort)
        .handle_access(AccessFs::from_all(ABI_TARGET))?
        .handle_access(AccessNet::BindTcp | AccessNet::ConnectTcp)?
        .scope(Scope::AbstractUnixSocket | Scope::Signal)?
        .create()?
        .add_rules(path_beneath_rules(
            readable,
            AccessFs::from_read(ABI_TARGET),
        ))?;
    for port in connect_ports.iter().copied().chain([DNS_PORT]) {
        ruleset = ruleset.add_rule(NetPort::new(port, AccessNet::ConnectTcp))?;
    }
    let status = ruleset.restrict_self()?;
    Ok(match status.ruleset {
        RulesetStatus::FullyEnforced => Enforcement::Full,
        RulesetStatus::PartiallyEnforced => Enforcement::Partial,
        RulesetStatus::NotEnforced => Enforcement::None,
    })
}
