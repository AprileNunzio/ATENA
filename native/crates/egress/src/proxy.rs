use std::net::{IpAddr, SocketAddr};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use serde::Serialize;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::Semaphore;
use tokio::time::{Instant, timeout, timeout_at};

use crate::config::{Config, Resolution, Upstream};
use crate::policy::{host_matches, is_public};
use crate::request::{self, HEAD_LIMIT, Target};

pub const ALLOWED_PORTS: [u16; 2] = [80, 443];
pub const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
pub const IDLE_TIMEOUT: Duration = Duration::from_secs(30);
pub const MAX_CONNECTIONS: usize = 64;
pub const MAX_DENIED: usize = 256;
const CHUNK: usize = 64 * 1024;
const ACCEPT_BACKOFF: Duration = Duration::from_millis(50);

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct Stats {
    pub carried: u64,
    pub denied: Vec<String>,
}

#[derive(Debug)]
pub struct Proxy {
    allowed: Vec<String>,
    deadline: Instant,
    max_bytes: u64,
    carried: AtomicU64,
    denied: Mutex<Vec<String>>,
    resolution: Resolution,
    upstream: Upstream,
    slots: Arc<Semaphore>,
}

enum Refusal {
    BadRequest,
    Forbidden,
    BadGateway,
}

impl Refusal {
    fn reply(&self) -> &'static [u8] {
        match self {
            Self::BadRequest => {
                b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            }
            Self::Forbidden => {
                b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            }
            Self::BadGateway => {
                b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            }
        }
    }
}

impl Proxy {
    #[must_use]
    pub fn new(config: &Config) -> Arc<Self> {
        Arc::new(Self {
            allowed: config.allowed.clone(),
            deadline: Instant::now()
                .checked_add(config.lifetime())
                .unwrap_or_else(Instant::now),
            max_bytes: config.max_bytes,
            carried: AtomicU64::new(0),
            denied: Mutex::new(Vec::new()),
            resolution: config.resolution(),
            upstream: config.upstream(),
            slots: Arc::new(Semaphore::new(MAX_CONNECTIONS)),
        })
    }

    #[must_use]
    pub fn deadline(&self) -> Instant {
        self.deadline
    }

    #[must_use]
    pub fn stats(&self) -> Stats {
        let denied = self
            .denied
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone();
        Stats {
            carried: self.carried.load(Ordering::Acquire),
            denied,
        }
    }

    pub async fn serve(self: Arc<Self>, listener: TcpListener) {
        loop {
            let Ok((client, _)) = listener.accept().await else {
                tokio::time::sleep(ACCEPT_BACKOFF).await;
                continue;
            };
            let Ok(permit) = Arc::clone(&self.slots).try_acquire_owned() else {
                drop(client);
                continue;
            };
            let proxy = Arc::clone(&self);
            tokio::spawn(async move {
                proxy.handle(client).await;
                drop(permit);
            });
        }
    }

    async fn handle(&self, mut client: TcpStream) {
        let _ = client.set_nodelay(true);
        let opened = match self.open(&mut client).await {
            Ok(opened) => opened,
            Err(refusal) => {
                let _ = timeout(CONNECT_TIMEOUT, client.write_all(refusal.reply())).await;
                return;
            }
        };
        let (upstream, target, leftover) = opened;
        self.relay(client, upstream, &target, &leftover).await;
    }

    async fn open(&self, client: &mut TcpStream) -> Result<(TcpStream, Target, Vec<u8>), Refusal> {
        let (head, leftover) = timeout(CONNECT_TIMEOUT, read_head(client))
            .await
            .map_err(|_| Refusal::BadRequest)??;
        let target = request::parse(&head).map_err(|_| Refusal::BadRequest)?;
        if !ALLOWED_PORTS.contains(&target.port) || !host_matches(&target.host, &self.allowed) {
            self.deny(&target.host);
            return Err(Refusal::Forbidden);
        }
        let Some(address) = self.resolve(&target.host).await else {
            self.deny(&target.host);
            return Err(Refusal::Forbidden);
        };
        let destination = match self.upstream {
            Upstream::Direct => SocketAddr::new(address, target.port),
            Upstream::Fixed(fixed) => fixed,
        };
        let upstream = timeout(CONNECT_TIMEOUT, TcpStream::connect(destination))
            .await
            .map_err(|_| Refusal::BadGateway)?
            .map_err(|_| Refusal::BadGateway)?;
        let _ = upstream.set_nodelay(true);
        Ok((upstream, target, leftover))
    }

    async fn resolve(&self, host: &str) -> Option<IpAddr> {
        let addresses: Vec<IpAddr> = match &self.resolution {
            Resolution::Static(table) => table.get(host).cloned().unwrap_or_default(),
            Resolution::System => timeout(CONNECT_TIMEOUT, tokio::net::lookup_host((host, 0)))
                .await
                .ok()?
                .ok()?
                .map(|a| a.ip())
                .collect(),
        };
        let first = addresses.first().copied()?;
        addresses.iter().all(|a| is_public(*a)).then_some(first)
    }

    fn deny(&self, host: &str) {
        let mut denied = self.denied.lock().unwrap_or_else(PoisonError::into_inner);
        if denied.len() < MAX_DENIED {
            denied.push(host.chars().take(253).collect());
        }
    }

    fn charge(&self, bytes: usize) -> bool {
        let bytes = u64::try_from(bytes).unwrap_or(u64::MAX);
        self.carried
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |carried| {
                carried
                    .checked_add(bytes)
                    .filter(|total| *total <= self.max_bytes)
            })
            .is_ok()
    }

    async fn relay(
        &self,
        mut client: TcpStream,
        mut upstream: TcpStream,
        target: &Target,
        leftover: &[u8],
    ) {
        let greeting = if target.tunnel {
            client
                .write_all(b"HTTP/1.1 200 Connection established\r\n\r\n")
                .await
        } else if self.charge(leftover.len()) {
            let mut first = target.forwarded.clone();
            first.extend_from_slice(leftover);
            upstream.write_all(&first).await
        } else {
            return;
        };
        if greeting.is_ok() {
            self.pipe(client, upstream).await;
        }
    }

    async fn pipe(&self, client: TcpStream, upstream: TcpStream) {
        let (mut client_read, mut client_write) = client.into_split();
        let (mut upstream_read, mut upstream_write) = upstream.into_split();
        let mut outbound = vec![0_u8; CHUNK];
        let mut inbound = vec![0_u8; CHUNK];
        loop {
            let idle = Instant::now()
                .checked_add(IDLE_TIMEOUT)
                .unwrap_or(self.deadline)
                .min(self.deadline);
            let step = timeout_at(idle, async {
                tokio::select! {
                    read = client_read.read(&mut outbound) => (true, read),
                    read = upstream_read.read(&mut inbound) => (false, read),
                }
            })
            .await;
            let (to_upstream, size) = match step {
                Ok((direction, Ok(size))) if size > 0 => (direction, size),
                _ => return,
            };
            if !self.charge(size) {
                return;
            }
            let written = if to_upstream {
                timeout(
                    IDLE_TIMEOUT,
                    upstream_write.write_all(outbound.get(..size).unwrap_or_default()),
                )
                .await
            } else {
                timeout(
                    IDLE_TIMEOUT,
                    client_write.write_all(inbound.get(..size).unwrap_or_default()),
                )
                .await
            };
            if !matches!(written, Ok(Ok(()))) {
                return;
            }
        }
    }
}

async fn read_head(client: &mut TcpStream) -> Result<(Vec<u8>, Vec<u8>), Refusal> {
    let mut buffer = Vec::with_capacity(4096);
    let mut chunk = [0_u8; 4096];
    loop {
        if let Some(end) = request::head_end(&buffer) {
            let leftover = buffer.split_off(end);
            return Ok((buffer, leftover));
        }
        if buffer.len() > HEAD_LIMIT {
            return Err(Refusal::BadRequest);
        }
        let size = client
            .read(&mut chunk)
            .await
            .map_err(|_| Refusal::BadRequest)?;
        if size == 0 {
            return Err(Refusal::BadRequest);
        }
        buffer.extend_from_slice(chunk.get(..size).unwrap_or_default());
    }
}
