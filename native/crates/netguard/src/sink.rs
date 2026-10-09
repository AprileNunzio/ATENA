use std::io::{self, Write};
#[cfg(unix)]
use std::os::unix::net::{UnixListener, UnixStream};
#[cfg(unix)]
use std::path::Path;

use atena_netguard::engine::Event;

#[derive(Debug)]
pub struct Sink {
    #[cfg(unix)]
    listener: Option<UnixListener>,
    #[cfg(unix)]
    clients: Vec<UnixStream>,
    to_stdout: bool,
}

impl Sink {
    pub fn stdout() -> Self {
        Self {
            #[cfg(unix)]
            listener: None,
            #[cfg(unix)]
            clients: Vec::new(),
            to_stdout: true,
        }
    }

    #[cfg(unix)]
    pub fn socket(path: &Path) -> Result<Self, String> {
        use std::fs;
        use std::os::unix::fs::PermissionsExt;
        if path.exists() {
            fs::remove_file(path).map_err(|e| format!("{}: {e}", path.display()))?;
        }
        let listener = UnixListener::bind(path).map_err(|e| format!("{}: {e}", path.display()))?;
        listener.set_nonblocking(true).map_err(|e| e.to_string())?;
        fs::set_permissions(path, fs::Permissions::from_mode(0o660)).map_err(|e| e.to_string())?;
        Ok(Self {
            listener: Some(listener),
            clients: Vec::new(),
            to_stdout: false,
        })
    }

    #[cfg(unix)]
    fn accept(&mut self) {
        let Some(listener) = &self.listener else {
            return;
        };
        while let Ok((stream, _)) = listener.accept() {
            if stream.set_nonblocking(false).is_ok()
                && stream
                    .set_write_timeout(Some(std::time::Duration::from_millis(200)))
                    .is_ok()
            {
                self.clients.push(stream);
            }
        }
    }

    pub fn emit(&mut self, event: &Event) {
        let Ok(mut line) = serde_json::to_string(event) else {
            return;
        };
        line.push('\n');
        if self.to_stdout {
            let stdout = io::stdout();
            let mut lock = stdout.lock();
            if lock
                .write_all(line.as_bytes())
                .and_then(|()| lock.flush())
                .is_err()
            {
                self.to_stdout = false;
            }
        }
        #[cfg(unix)]
        {
            self.accept();
            self.clients
                .retain_mut(|client| client.write_all(line.as_bytes()).is_ok());
        }
    }
}
