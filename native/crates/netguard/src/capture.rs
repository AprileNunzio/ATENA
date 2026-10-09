use std::io::Read;
use std::sync::mpsc::{self, RecvTimeoutError, SyncSender, TrySendError};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use socket2::{Domain, Protocol, Socket, Type};

use atena_netguard::engine::{Engine, Event};
use atena_netguard::net::parse_mac;

use crate::config::Config;
use crate::sink::Sink;

const ETH_P_ALL: u16 = 0x0003;
const FRAME: usize = 65_536;
const QUEUE: usize = 16_384;

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| u64::try_from(d.as_millis()).unwrap_or(u64::MAX))
}

fn mac_of(interface: &str) -> Option<[u8; 6]> {
    let safe = !interface.is_empty()
        && interface.len() <= 15
        && !interface.contains("..")
        && interface
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "_.:-".contains(c));
    if !safe {
        return None;
    }
    let text = std::fs::read_to_string(format!("/sys/class/net/{interface}/address")).ok()?;
    parse_mac(text.trim()).filter(|mac| *mac != [0; 6])
}

fn open(interface: &str) -> Result<Socket, String> {
    let protocol = Protocol::from(i32::from(ETH_P_ALL.to_be()));
    let socket = Socket::new(Domain::PACKET, Type::RAW, Some(protocol))
        .map_err(|e| format!("socket di cattura su {interface}: {e} (serve CAP_NET_RAW)"))?;
    socket
        .bind_device(Some(interface.as_bytes()))
        .map_err(|e| format!("interfaccia {interface}: {e}"))?;
    Ok(socket)
}

fn listen(interface: &str, socket: &Socket, frames: &SyncSender<(u64, Vec<u8>)>) {
    let mut buffer = vec![0_u8; FRAME];
    let mut reader = socket;
    loop {
        match reader.read(&mut buffer) {
            Ok(0) => {}
            Ok(n) => {
                let frame = buffer.get(..n).map(<[u8]>::to_vec).unwrap_or_default();
                if let Err(TrySendError::Disconnected(_)) = frames.try_send((now_ms(), frame)) {
                    return;
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => {}
            Err(e) => {
                eprintln!("atena-netguard: cattura su {interface} interrotta: {e}");
                return;
            }
        }
    }
}

pub fn run(
    interfaces: &[String],
    mut engine: Engine,
    mut sink: Sink,
    config: &Config,
) -> Result<(), String> {
    let own: Vec<[u8; 6]> = interfaces.iter().filter_map(|i| mac_of(i)).collect();
    if own.len() != interfaces.len() {
        return Err("impossibile leggere il MAC di tutte le interfacce scelte".into());
    }
    engine.own_macs(&own);
    let (tx, rx) = mpsc::sync_channel::<(u64, Vec<u8>)>(QUEUE);
    for interface in interfaces {
        let socket = open(interface)?;
        let name = interface.clone();
        let frames = tx.clone();
        thread::Builder::new()
            .name(format!("netguard-{interface}"))
            .spawn(move || listen(&name, &socket, &frames))
            .map_err(|e| e.to_string())?;
    }
    drop(tx);
    let every = Duration::from_secs(config.summary_seconds.max(1));
    let mut next_summary = Instant::now()
        .checked_add(every)
        .unwrap_or_else(Instant::now);
    loop {
        let wait = next_summary.saturating_duration_since(Instant::now());
        match rx.recv_timeout(wait) {
            Ok((at, frame)) if !frame.is_empty() => {
                for alert in engine.feed(&frame, at) {
                    sink.emit(&Event::Alert(alert));
                }
            }
            Ok(_) | Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => {
                return Err("tutte le interfacce di cattura si sono fermate".into());
            }
        }
        if Instant::now() >= next_summary {
            sink.emit(&Event::Summary(engine.summary(now_ms(), config.top)));
            next_summary = Instant::now()
                .checked_add(every)
                .unwrap_or_else(Instant::now);
        }
    }
}
