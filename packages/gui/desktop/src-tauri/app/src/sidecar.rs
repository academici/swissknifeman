// Supervisor of the Python sidecar: spawn, stdin handshake, READY, health check, restart by the core policy.
// The session secret lives only here: it is written to the sidecar stdin and used for the Bearer header of the adapter.
use base64::Engine;
use serde::Serialize;
use serde_json::json;
use skm_gui_core::backoff::{Decision, Policy};
use skm_gui_core::ready;
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::AppHandle;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;
use tokio::sync::mpsc::{unbounded_channel, UnboundedReceiver, UnboundedSender};

const READY_TIMEOUT: Duration = Duration::from_secs(20);
const HEALTH_EVERY_TICKS: u32 = 10; // one tick per second
const HEALTH_FAILS: u32 = 3;
const TERM_WAIT: Duration = Duration::from_secs(15);
const LOG_LINES: usize = 1000;
const LOG_LINE_CHARS: usize = 2000;
pub const LOG_REPLY_MAX: usize = 200;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum State {
    Starting,
    Ready,
    Restarting,
    Failed,
}

/// What `sidecar_status` returns. It never holds the secret.
#[derive(Debug, Clone, Serialize)]
pub struct StatusView {
    pub state: State,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub port: Option<u16>,
    pub restarts: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_error: Option<String>,
}

enum Control {
    Restart,
    Stop,
}

enum End {
    Exited(String),
    Restart,
    Stop,
}

struct Inner {
    state: State,
    port: Option<u16>,
    restarts: u32,
    last_error: Option<String>,
    log: VecDeque<String>,
    alive: bool,
}

pub struct Shared {
    inner: Mutex<Inner>,
    secret: String,
    ctrl: UnboundedSender<Control>,
    pub client: reqwest::Client,
}

fn new_secret() -> String {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).expect("operating system random generator");
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(bytes)
}

impl Shared {
    fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// Only the adapter reads it, to set `Authorization`; no command returns it.
    pub(crate) fn secret(&self) -> &str {
        &self.secret
    }

    pub fn status(&self) -> StatusView {
        let inner = self.lock();
        StatusView {
            state: inner.state,
            port: if inner.state == State::Ready { inner.port } else { None },
            restarts: inner.restarts,
            last_error: inner.last_error.clone(),
        }
    }

    pub fn ready_port(&self) -> Option<u16> {
        let inner = self.lock();
        if inner.state == State::Ready {
            inner.port
        } else {
            None
        }
    }

    pub fn log_tail(&self, lines: usize) -> Vec<String> {
        let inner = self.lock();
        let n = lines.min(LOG_REPLY_MAX).min(inner.log.len());
        inner.log.iter().skip(inner.log.len() - n).cloned().collect()
    }

    pub fn request_restart(&self) {
        let _ = self.ctrl.send(Control::Restart);
    }

    /// Appends a line to the ring buffer after removing the secret value and cutting the length.
    fn log_line(&self, line: &str) {
        let mut clean = line.replace(self.secret.as_str(), "[redacted]");
        if clean.chars().count() > LOG_LINE_CHARS {
            clean = clean.chars().take(LOG_LINE_CHARS).collect();
        }
        let mut inner = self.lock();
        if inner.log.len() >= LOG_LINES {
            inner.log.pop_front();
        }
        inner.log.push_back(clean);
    }

    fn set_state(&self, state: State) {
        let mut inner = self.lock();
        inner.state = state;
        if state != State::Ready {
            inner.port = None;
        }
    }

    fn set_error(&self, error: &str) {
        let clean = error.replace(self.secret.as_str(), "[redacted]");
        self.lock().last_error = Some(clean.clone());
        self.log_line(&format!("sidecar: {}", clean));
    }

    /// Stops the supervisor and waits (at most 16 s) until the sidecar is gone.
    pub async fn shutdown(&self) {
        let _ = self.ctrl.send(Control::Stop);
        let deadline = Instant::now() + TERM_WAIT + Duration::from_secs(1);
        while self.lock().alive && Instant::now() < deadline {
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    }
}

pub fn start(app: AppHandle) -> Arc<Shared> {
    let (tx, rx) = unbounded_channel();
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(30))
        .build()
        .expect("http client");
    let shared = Arc::new(Shared {
        inner: Mutex::new(Inner {
            state: State::Starting,
            port: None,
            restarts: 0,
            last_error: None,
            log: VecDeque::new(),
            alive: false,
        }),
        secret: new_secret(),
        ctrl: tx,
        client,
    });
    tauri::async_runtime::spawn(supervise(app, shared.clone(), rx));
    shared
}

fn ms(base: Instant) -> u64 {
    base.elapsed().as_millis() as u64
}

async fn supervise(app: AppHandle, shared: Arc<Shared>, mut rx: UnboundedReceiver<Control>) {
    let base = Instant::now();
    let mut policy = Policy::new();
    loop {
        let started = ms(base);
        let end = run_once(&app, &shared, &mut rx).await;
        shared.lock().alive = false;
        let exited = ms(base);
        match end {
            End::Stop => return,
            End::Restart => {
                policy.reset();
                shared.set_state(State::Restarting);
                shared.lock().restarts += 1;
            }
            End::Exited(error) => {
                shared.set_error(&error);
                match policy.on_exit(started, exited) {
                    Decision::Failed => {
                        shared.set_state(State::Failed);
                        loop {
                            match rx.recv().await {
                                Some(Control::Restart) => {
                                    policy.reset();
                                    break;
                                }
                                Some(Control::Stop) | None => return,
                            }
                        }
                    }
                    Decision::Restart { delay_ms } => {
                        shared.set_state(State::Restarting);
                        shared.lock().restarts += 1;
                        tokio::select! {
                            _ = tokio::time::sleep(Duration::from_millis(delay_ms)) => {}
                            ctrl = rx.recv() => match ctrl {
                                Some(Control::Restart) => policy.reset(),
                                Some(Control::Stop) | None => return,
                            },
                        }
                    }
                }
            }
        }
    }
}

#[cfg(unix)]
fn send_term(pid: u32) {
    let _ = std::process::Command::new("kill").arg("-TERM").arg(pid.to_string()).status();
}

#[cfg(not(unix))]
fn send_term(_pid: u32) {}

/// SIGTERM, wait for the exit (the sidecar stops gracefully), then kill.
async fn terminate(
    child: tauri_plugin_shell::process::CommandChild,
    events: &mut tauri::async_runtime::Receiver<CommandEvent>,
) {
    send_term(child.pid());
    let wait = async {
        while let Some(event) = events.recv().await {
            if let CommandEvent::Terminated(_) = event {
                return true;
            }
        }
        true
    };
    if tokio::time::timeout(TERM_WAIT, wait).await.is_err() {
        let _ = child.kill();
    }
}

async fn health_ok(shared: &Shared, port: u16) -> bool {
    let url = format!("http://127.0.0.1:{}/v1/bootstrap", port);
    match shared.client.get(url).bearer_auth(shared.secret()).send().await {
        Ok(response) => response.status().is_success(),
        Err(_) => false,
    }
}

async fn run_once(app: &AppHandle, shared: &Arc<Shared>, rx: &mut UnboundedReceiver<Control>) -> End {
    if shared.lock().state != State::Restarting {
        shared.set_state(State::Starting);
    }
    let spawned = app.shell().sidecar("gui-backend").and_then(|command| command.spawn());
    let (mut events, mut child) = match spawned {
        Ok(pair) => pair,
        Err(e) => return End::Exited(format!("spawn failed: {}", e)),
    };
    shared.lock().alive = true;
    let handshake = json!({
        "v": 1,
        "secret": shared.secret(),
        "port": 0,
        "shell_version": env!("CARGO_PKG_VERSION"),
    });
    if let Err(e) = child.write(format!("{}\n", handshake).as_bytes()) {
        let _ = child.kill();
        return End::Exited(format!("handshake write failed: {}", e));
    }
    let deadline = Instant::now() + READY_TIMEOUT;
    let mut ready_seen = false;
    let mut ticker = tokio::time::interval(Duration::from_secs(1));
    let mut ticks = 0u32;
    let mut fails = 0u32;
    loop {
        tokio::select! {
            event = events.recv() => match event {
                None => return End::Exited("sidecar event channel closed".into()),
                Some(CommandEvent::Stdout(bytes)) => {
                    let line = String::from_utf8_lossy(&bytes).trim_end().to_owned();
                    if !ready_seen {
                        match ready::parse(&line) {
                            Ok(r) => {
                                ready_seen = true;
                                let mut inner = shared.lock();
                                inner.port = Some(r.port);
                                inner.state = State::Ready;
                                inner.last_error = None;
                                drop(inner);
                                shared.log_line(&format!("ready: port {} backend {}", r.port, r.backend));
                            }
                            Err(e) => {
                                shared.log_line(&line);
                                let _ = child.kill();
                                return End::Exited(e.code().into());
                            }
                        }
                    } else {
                        shared.log_line(&line);
                    }
                }
                Some(CommandEvent::Stderr(bytes)) => {
                    shared.log_line(String::from_utf8_lossy(&bytes).trim_end());
                }
                Some(CommandEvent::Error(e)) => shared.log_line(&format!("shell error: {}", e)),
                Some(CommandEvent::Terminated(payload)) => {
                    return End::Exited(format!("sidecar exited (code {:?}, signal {:?})", payload.code, payload.signal));
                }
                Some(_) => {}
            },
            ctrl = rx.recv() => {
                terminate(child, &mut events).await;
                return match ctrl {
                    Some(Control::Restart) => End::Restart,
                    Some(Control::Stop) | None => End::Stop,
                };
            },
            _ = ticker.tick() => {
                ticks += 1;
                if !ready_seen {
                    if Instant::now() > deadline {
                        let _ = child.kill();
                        return End::Exited("READY timeout".into());
                    }
                } else if ticks % HEALTH_EVERY_TICKS == 0 {
                    let port = shared.lock().port;
                    if let Some(port) = port {
                        if health_ok(shared, port).await {
                            fails = 0;
                        } else {
                            fails += 1;
                            if fails >= HEALTH_FAILS {
                                let _ = child.kill();
                                return End::Exited("health check failed".into());
                            }
                        }
                    }
                }
            },
        }
    }
}
