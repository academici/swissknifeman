//! Validation of an `api_request` before it reaches the sidecar. The webview supplies only method, path and body size;
//! host, scheme and headers are never taken from it.

pub const MAX_PATH: usize = 2048;
pub const MAX_BODY: usize = 1_048_576;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdapterError {
    Method,
    Path,
    BodyTooLarge,
}

impl AdapterError {
    pub fn code(&self) -> &'static str {
        match self {
            AdapterError::Method => "ADAPTER_METHOD",
            AdapterError::Path => "ADAPTER_PATH",
            AdapterError::BodyTooLarge => "ADAPTER_BODY_TOO_LARGE",
        }
    }
}

fn hex(c: u8) -> Option<u8> {
    match c {
        b'0'..=b'9' => Some(c - b'0'),
        b'a'..=b'f' => Some(c - b'a' + 10),
        b'A'..=b'F' => Some(c - b'A' + 10),
        _ => None,
    }
}

/// Checks in order: method (GET|POST|PATCH), path, body size.
/// The path must start with `/v1/`, be at most 2048 bytes, hold printable ASCII only (no space, control, `\`, `#`) and
/// no `..` also after percent-decoding; a decoded NUL, control character or `\` is refused too.
pub fn validate(method: &str, path: &str, body_len: usize) -> Result<(), AdapterError> {
    if !matches!(method, "GET" | "POST" | "PATCH") {
        return Err(AdapterError::Method);
    }
    if !path.starts_with("/v1/") || path.len() > MAX_PATH {
        return Err(AdapterError::Path);
    }
    let raw = path.as_bytes();
    if raw.iter().any(|&c| c <= 0x20 || c == 0x7f || c >= 0x80 || c == b'\\' || c == b'#') {
        return Err(AdapterError::Path);
    }
    let mut decoded: Vec<u8> = Vec::with_capacity(raw.len());
    let mut i = 0;
    while i < raw.len() {
        if raw[i] == b'%' {
            let (hi, lo) = match (raw.get(i + 1).and_then(|&c| hex(c)), raw.get(i + 2).and_then(|&c| hex(c))) {
                (Some(hi), Some(lo)) => (hi, lo),
                _ => return Err(AdapterError::Path),
            };
            let d = hi * 16 + lo;
            if d < 0x20 || d == 0x7f || d == b'\\' {
                return Err(AdapterError::Path);
            }
            decoded.push(d);
            i += 3;
        } else {
            decoded.push(raw[i]);
            i += 1;
        }
    }
    if decoded.windows(2).any(|w| w == b"..") {
        return Err(AdapterError::Path);
    }
    if body_len > MAX_BODY {
        return Err(AdapterError::BodyTooLarge);
    }
    Ok(())
}
