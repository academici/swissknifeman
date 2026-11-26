//! Parsing of the sidecar READY line: `GUI_READY {"v":1,"port":N,"epoch":"...","pid":P,"backend":"...",
//! "gui_protocol":{"min":"1","max":"1"}}`. Unknown fields are ignored.

use serde_json::Value;

const PREFIX: &str = "GUI_READY ";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ready {
    pub port: u16,
    pub epoch: String,
    pub pid: u64,
    pub backend: String,
    pub protocol_min: String,
    pub protocol_max: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ReadyError;

impl ReadyError {
    pub fn code(&self) -> &'static str {
        "READY_INVALID"
    }
}

fn text(v: Option<&Value>) -> Option<String> {
    v.and_then(Value::as_str).map(str::to_owned)
}

pub fn parse(line: &str) -> Result<Ready, ReadyError> {
    let line = line.trim_end_matches(|c| c == '\n' || c == '\r');
    let rest = line.strip_prefix(PREFIX).ok_or(ReadyError)?;
    let value: Value = serde_json::from_str(rest).map_err(|_| ReadyError)?;
    let obj = value.as_object().ok_or(ReadyError)?;
    if obj.get("v").and_then(Value::as_u64) != Some(1) {
        return Err(ReadyError);
    }
    let port = obj.get("port").and_then(Value::as_u64).ok_or(ReadyError)?;
    if !(1..=65535).contains(&port) {
        return Err(ReadyError);
    }
    let pid = obj.get("pid").and_then(Value::as_u64).filter(|&p| p > 0).ok_or(ReadyError)?;
    let epoch = text(obj.get("epoch")).filter(|s| !s.is_empty()).ok_or(ReadyError)?;
    let backend = text(obj.get("backend")).filter(|s| !s.is_empty()).ok_or(ReadyError)?;
    let proto = obj.get("gui_protocol").and_then(Value::as_object).ok_or(ReadyError)?;
    let protocol_min = text(proto.get("min")).ok_or(ReadyError)?;
    let protocol_max = text(proto.get("max")).ok_or(ReadyError)?;
    Ok(Ready { port: port as u16, epoch, pid, backend, protocol_min, protocol_max })
}
