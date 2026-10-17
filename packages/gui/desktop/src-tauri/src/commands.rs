// The six commands of the webview adapter. None takes a URL, host, scheme or header; none returns a header or the
// session secret. Validation is `skm_gui_core::adapter::validate`; `Authorization`, `Origin` and `Content-Type` are set here.
use crate::sidecar::{Shared, StatusView, LOG_REPLY_MAX};
use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use serde_json::{json, Value};
use skm_gui_core::adapter;
use skm_gui_core::batch::Batcher;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::ipc::Channel;
use tauri::State;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::Message;

const MAX_RESPONSE: usize = 16 * 1024 * 1024;

#[derive(Debug, Serialize)]
pub struct CommandError {
    pub code: String,
    pub message: String,
}

fn fail(code: &str, message: &str) -> CommandError {
    CommandError { code: code.to_owned(), message: message.to_owned() }
}

impl From<adapter::AdapterError> for CommandError {
    fn from(e: adapter::AdapterError) -> Self {
        fail(e.code(), "request refused by the adapter")
    }
}

#[derive(Debug, Serialize)]
pub struct ApiResponse {
    pub status: u16,
    pub body: Value,
}

#[derive(Default)]
pub struct Subscriptions {
    next: AtomicU64,
    tasks: Mutex<HashMap<u64, tauri::async_runtime::JoinHandle<()>>>,
}

impl Subscriptions {
    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<u64, tauri::async_runtime::JoinHandle<()>>> {
        self.tasks.lock().unwrap_or_else(|e| e.into_inner())
    }

    pub fn abort(&self, id: u64) {
        if let Some(handle) = self.lock().remove(&id) {
            handle.abort();
        }
    }

    pub fn abort_all(&self) {
        for (_, handle) in self.lock().drain() {
            handle.abort();
        }
    }
}

#[tauri::command]
pub async fn api_request(
    shared: State<'_, Arc<Shared>>,
    method: String,
    path: String,
    body: Option<Value>,
) -> Result<ApiResponse, CommandError> {
    let payload = match &body {
        Some(value) => Some(serde_json::to_vec(value).map_err(|_| fail("ADAPTER_BODY", "body is not JSON"))?),
        None => None,
    };
    adapter::validate(&method, &path, payload.as_ref().map_or(0, Vec::len))?;
    let port = shared.ready_port().ok_or_else(|| fail("SIDECAR_UNAVAILABLE", "the backend is not ready"))?;
    let url = format!("http://127.0.0.1:{}{}", port, path);
    let verb = match method.as_str() {
        "GET" => reqwest::Method::GET,
        "POST" => reqwest::Method::POST,
        _ => reqwest::Method::PATCH,
    };
    let mut request = shared
        .client
        .request(verb, url)
        .bearer_auth(shared.secret())
        .header("Origin", format!("http://127.0.0.1:{}", port));
    if let Some(bytes) = payload {
        request = request.header("Content-Type", "application/json").body(bytes);
    }
    let response = request.send().await.map_err(|_| fail("SIDECAR_REQUEST_FAILED", "the backend did not answer"))?;
    let status = response.status().as_u16();
    let bytes = response.bytes().await.map_err(|_| fail("SIDECAR_REQUEST_FAILED", "the backend answer was cut"))?;
    if bytes.len() > MAX_RESPONSE {
        return Err(fail("SIDECAR_RESPONSE_TOO_LARGE", "the backend answer is too large"));
    }
    let body = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or_else(|_| Value::String(String::from_utf8_lossy(&bytes).into_owned()))
    };
    Ok(ApiResponse { status, body })
}

fn frame_value(text: &str) -> Value {
    serde_json::from_str(text).unwrap_or_else(|_| Value::String(text.to_owned()))
}

/// One WebSocket to `/v1/events`; frames go to the Channel in batches (an array; a first element `{"dropped": N}`
/// reports frames lost to overflow; a last array `[{"closed": true}]` says the stream ended). The task ends when
/// `Channel.send` fails, when the socket closes, on `api_unsubscribe` and when the window is destroyed.
async fn pump(shared: Arc<Shared>, subs: Arc<Subscriptions>, id: u64, filter: Value, channel: Channel<Value>) {
    let _ = run_pump(&shared, id, filter, &channel).await;
    let _ = channel.send(json!([{ "closed": true }]));
    subs.lock().remove(&id);
}

async fn run_pump(shared: &Shared, id: u64, filter: Value, channel: &Channel<Value>) -> Option<()> {
    let port = shared.ready_port()?;
    let mut request = format!("ws://127.0.0.1:{}/v1/events", port).into_client_request().ok()?;
    let headers = request.headers_mut();
    headers.insert("Authorization", format!("Bearer {}", shared.secret()).parse().ok()?);
    headers.insert("Origin", format!("http://127.0.0.1:{}", port).parse().ok()?);
    let (socket, _) = tokio_tungstenite::connect_async(request).await.ok()?;
    let (mut sink, mut stream) = socket.split();
    let subscribe = json!({
        "$schema": "urn:swissknifeman:gui:stream:v1",
        "kind": "subscribe",
        "id": format!("s{}", id),
        "filter": filter,
        "cursor": null,
        "epoch": null,
    });
    sink.send(Message::Text(subscribe.to_string().into())).await.ok()?;
    let base = Instant::now();
    let now = || base.elapsed().as_millis() as u64;
    let mut batcher = Batcher::default();
    let mut tick = tokio::time::interval(Duration::from_millis(10));
    let mut open = true;
    while open {
        tokio::select! {
            message = stream.next() => match message {
                Some(Ok(Message::Text(text))) => batcher.push(text.to_string(), now()),
                Some(Ok(Message::Close(_))) | None | Some(Err(_)) => open = false,
                Some(Ok(_)) => {}
            },
            _ = tick.tick() => {},
        }
        while let Some(batch) = batcher.poll(if open { now() } else { u64::MAX }) {
            let mut frames: Vec<Value> = Vec::with_capacity(batch.frames.len() + 1);
            if batch.dropped > 0 {
                frames.push(json!({ "dropped": batch.dropped }));
            }
            frames.extend(batch.frames.iter().map(|f| frame_value(f)));
            channel.send(Value::Array(frames)).ok()?;
        }
    }
    Some(())
}

#[tauri::command]
pub async fn api_subscribe(
    shared: State<'_, Arc<Shared>>,
    subs: State<'_, Arc<Subscriptions>>,
    filter: Value,
    channel: Channel<Value>,
) -> Result<u64, CommandError> {
    if !filter.is_object() {
        return Err(fail("ADAPTER_FILTER", "the filter must be an object"));
    }
    if shared.ready_port().is_none() {
        return Err(fail("SIDECAR_UNAVAILABLE", "the backend is not ready"));
    }
    let id = subs.next.fetch_add(1, Ordering::Relaxed) + 1;
    let handle = tauri::async_runtime::spawn(pump(shared.inner().clone(), subs.inner().clone(), id, filter, channel));
    subs.lock().insert(id, handle);
    Ok(id)
}

#[tauri::command]
pub fn api_unsubscribe(subs: State<'_, Arc<Subscriptions>>, id: u64) {
    subs.abort(id);
}

#[tauri::command]
pub fn sidecar_status(shared: State<'_, Arc<Shared>>) -> StatusView {
    shared.status()
}

#[tauri::command]
pub fn sidecar_restart(shared: State<'_, Arc<Shared>>) {
    shared.request_restart();
}

#[tauri::command]
pub fn sidecar_log(shared: State<'_, Arc<Shared>>, lines: Option<usize>) -> Vec<String> {
    shared.log_tail(lines.unwrap_or(LOG_REPLY_MAX))
}
