#![forbid(unsafe_code)]

use std::io::{BufRead, Write};
use std::net::{SocketAddr, TcpListener as StdListener};
use std::process::ExitCode;

use atena_egress::config::{Config, MAX_CONFIG_BYTES, Upstream};
use atena_egress::proxy::{ALLOWED_PORTS, Proxy};
use atena_egress::sandbox;
use serde_json::json;
use tokio::io::AsyncReadExt;
use tokio::net::TcpListener;

const WORKERS: usize = 2;

fn emit(value: &serde_json::Value) -> bool {
    let mut out = std::io::stdout().lock();
    writeln!(out, "{value}").and_then(|()| out.flush()).is_ok()
}

fn fail(message: &str) -> ExitCode {
    emit(&json!({ "error": message }));
    ExitCode::FAILURE
}

fn read_config() -> Result<Config, String> {
    let mut line = Vec::new();
    let limit = u64::try_from(MAX_CONFIG_BYTES)
        .unwrap_or(u64::MAX)
        .saturating_add(1);
    std::io::Read::take(std::io::stdin().lock(), limit)
        .read_until(b'\n', &mut line)
        .map_err(|e| format!("cannot read configuration: {e}"))?;
    Config::parse(line.trim_ascii()).map_err(|e| e.to_string())
}

fn bind(config: &Config) -> Result<StdListener, String> {
    let (low, high) = config.ports;
    (low..=high)
        .find_map(|port| StdListener::bind(SocketAddr::new(config.bind, port)).ok())
        .ok_or_else(|| format!("no free proxy port in {low}-{high}"))
}

fn connect_ports(config: &Config) -> Vec<u16> {
    match config.upstream() {
        Upstream::Direct => ALLOWED_PORTS.to_vec(),
        Upstream::Fixed(address) => vec![address.port()],
    }
}

async fn stdin_closed() {
    let mut stdin = tokio::io::stdin();
    let mut sink = [0_u8; 256];
    while matches!(stdin.read(&mut sink).await, Ok(n) if n > 0) {}
}

fn main() -> ExitCode {
    let config = match read_config() {
        Ok(config) => config,
        Err(message) => return fail(&message),
    };
    let listener = match bind(&config).and_then(|l| {
        l.set_nonblocking(true)
            .map(|()| l)
            .map_err(|e| e.to_string())
    }) {
        Ok(listener) => listener,
        Err(message) => return fail(&message),
    };
    let enforcement = match sandbox::restrict(&connect_ports(&config)) {
        Ok(enforcement) => enforcement,
        Err(error) => return fail(&format!("sandbox setup failed: {error}")),
    };
    let Ok(port) = listener.local_addr().map(|a| a.port()) else {
        return fail("cannot read the bound port");
    };
    let runtime = match tokio::runtime::Builder::new_multi_thread()
        .worker_threads(WORKERS)
        .enable_all()
        .build()
    {
        Ok(runtime) => runtime,
        Err(error) => return fail(&format!("runtime setup failed: {error}")),
    };
    let proxy = Proxy::new(&config);
    let stats = runtime.block_on(async {
        let listener = TcpListener::from_std(listener).map_err(|e| e.to_string())?;
        if !emit(&json!({ "port": port, "sandbox": enforcement.label() })) {
            return Err("cannot report the bound port".to_owned());
        }
        tokio::select! {
            () = std::sync::Arc::clone(&proxy).serve(listener) => {}
            () = stdin_closed() => {}
            () = tokio::time::sleep_until(proxy.deadline()) => {}
        }
        Ok(proxy.stats())
    });
    runtime.shutdown_background();
    match stats {
        Ok(stats) if emit(&json!(stats)) => ExitCode::SUCCESS,
        Ok(_) => ExitCode::FAILURE,
        Err(message) => fail(&message),
    }
}
