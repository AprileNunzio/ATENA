#[cfg(target_os = "linux")]
mod capture;
mod config;
mod sink;

use std::fs::File;
use std::io::BufReader;
use std::path::PathBuf;
use std::process::ExitCode;

use atena_netguard::engine::{Engine, Event};
use atena_netguard::pcap::Reader;

use crate::config::Config;
use crate::sink::Sink;

#[derive(Debug, Default)]
struct Args {
    command: String,
    file: Option<PathBuf>,
    config: Option<PathBuf>,
    socket: Option<PathBuf>,
    interfaces: Vec<String>,
}

fn parse_args() -> Result<Args, String> {
    let mut raw = std::env::args().skip(1);
    let mut args = Args {
        command: raw.next().unwrap_or_default(),
        ..Args::default()
    };
    while let Some(flag) = raw.next() {
        let value = raw
            .next()
            .ok_or_else(|| format!("manca il valore di {flag}"))?;
        match flag.as_str() {
            "--file" => args.file = Some(PathBuf::from(value)),
            "--config" => args.config = Some(PathBuf::from(value)),
            "--socket" => args.socket = Some(PathBuf::from(value)),
            "--interface" => args.interfaces.push(value),
            _ => return Err(format!("opzione sconosciuta: {flag}")),
        }
    }
    Ok(args)
}

fn engine(config: &Config) -> Result<Engine, String> {
    let mut engine = Engine::new(
        config.thresholds.clone(),
        config.max_flows,
        config.idle_seconds.saturating_mul(1_000),
    );
    for mac in config.macs()? {
        engine.detector().trust_mac(mac);
    }
    Ok(engine)
}

fn replay(args: &Args, config: &Config) -> Result<(), String> {
    let path = args.file.as_ref().ok_or("serve --file <cattura.pcap>")?;
    let file = File::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut reader = Reader::open(BufReader::new(file)).map_err(|e| e.to_string())?;
    let mut engine = engine(config)?;
    let mut sink = Sink::stdout();
    let mut last = 0;
    while let Some(record) = reader.next_record().map_err(|e| e.to_string())? {
        last = record.at_ms;
        for alert in engine.feed(&record.data, record.at_ms) {
            sink.emit(&Event::Alert(alert));
        }
    }
    sink.emit(&Event::Summary(engine.summary(last, config.top)));
    Ok(())
}

#[cfg(target_os = "linux")]
fn live(args: &Args, config: &Config) -> Result<(), String> {
    if args.interfaces.is_empty() {
        return Err("serve almeno un --interface (es. eth0, wlan0)".into());
    }
    let sink = match &args.socket {
        Some(path) => Sink::socket(path)?,
        None => Sink::stdout(),
    };
    capture::run(&args.interfaces, engine(config)?, sink, config)
}

#[cfg(not(target_os = "linux"))]
fn live(_: &Args, _: &Config) -> Result<(), String> {
    Err("la cattura dal vivo è disponibile solo su Linux".into())
}

fn main() -> ExitCode {
    let outcome = parse_args().and_then(|args| {
        let config = Config::load(args.config.as_deref())?;
        match args.command.as_str() {
            "replay" => replay(&args, &config),
            "capture" => live(&args, &config),
            _ => Err("uso: atena-netguard replay --file F | capture --interface I [--socket S] [--config C]".into()),
        }
    });
    match outcome {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("atena-netguard: {message}");
            ExitCode::FAILURE
        }
    }
}
