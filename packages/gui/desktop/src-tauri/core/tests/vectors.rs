//! Runs `desktop/tests/vectors/*.json` against the core. The Python oracle (`packages/gui/tests/desktop_oracle.py`)
//! reads the same files; neither side holds expected values of its own.

use serde_json::Value;
use skm_gui_core::adapter::{self, AdapterError};
use skm_gui_core::backoff::{self, Decision, Policy};
use skm_gui_core::batch::Batcher;
use skm_gui_core::ready;
use std::path::PathBuf;

fn load(name: &str) -> Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/vectors").join(name);
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {}", path.display(), e));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("{}: {}", path.display(), e))
}

fn arr<'a>(v: &'a Value, key: &str) -> &'a Vec<Value> {
    v[key].as_array().unwrap_or_else(|| panic!("{} is not an array", key))
}

#[test]
fn adapter_vectors() {
    let doc = load("adapter.json");
    let cases = arr(&doc, "cases");
    assert!(cases.len() >= 20);
    for case in cases {
        let name = case["name"].as_str().unwrap();
        let got = adapter::validate(
            case["method"].as_str().unwrap(),
            case["path"].as_str().unwrap(),
            case["body_len"].as_u64().unwrap() as usize,
        );
        let expect = &case["expect"];
        match got {
            Ok(()) => assert_eq!(expect["ok"], Value::Bool(true), "{}", name),
            Err(e) => {
                let _: AdapterError = e;
                assert_eq!(expect["error"].as_str(), Some(e.code()), "{}", name)
            }
        }
    }
}

#[test]
fn ready_vectors() {
    let doc = load("ready.json");
    let cases = arr(&doc, "cases");
    assert!(cases.len() >= 8);
    for case in cases {
        let name = case["name"].as_str().unwrap();
        let expect = &case["expect"];
        match ready::parse(case["line"].as_str().unwrap()) {
            Ok(r) => {
                let ok = &expect["ok"];
                assert!(ok.is_object(), "{}", name);
                assert_eq!(ok["port"].as_u64(), Some(r.port as u64), "{}", name);
                assert_eq!(ok["epoch"].as_str(), Some(r.epoch.as_str()), "{}", name);
                assert_eq!(ok["pid"].as_u64(), Some(r.pid), "{}", name);
                assert_eq!(ok["backend"].as_str(), Some(r.backend.as_str()), "{}", name);
                assert_eq!(ok["gui_protocol"]["min"].as_str(), Some(r.protocol_min.as_str()), "{}", name);
                assert_eq!(ok["gui_protocol"]["max"].as_str(), Some(r.protocol_max.as_str()), "{}", name);
            }
            Err(e) => assert_eq!(expect["error"].as_str(), Some(e.code()), "{}", name),
        }
    }
}

#[test]
fn backoff_delay_table() {
    let doc = load("backoff.json");
    let rows = arr(&doc, "delays");
    assert_eq!(rows.len(), 11);
    for row in rows {
        let attempt = row["attempt"].as_u64().unwrap() as u32;
        assert_eq!(backoff::delay_ms(attempt), row["ms"].as_u64().unwrap(), "attempt {}", attempt);
    }
}

#[test]
fn policy_vectors() {
    let doc = load("backoff.json");
    for case in arr(&doc, "policy") {
        let name = case["name"].as_str().unwrap();
        let expect = arr(case, "expect");
        let events = arr(case, "events");
        assert_eq!(events.len(), expect.len(), "{}", name);
        let mut policy = Policy::new();
        for (i, event) in events.iter().enumerate() {
            if event.as_str() == Some("reset") {
                policy.reset();
                assert!(expect[i].is_null(), "{} #{}", name, i);
                continue;
            }
            let got = policy.on_exit(event["started_ms"].as_u64().unwrap(), event["exited_ms"].as_u64().unwrap());
            match got {
                Decision::Restart { delay_ms } => assert_eq!(expect[i].as_u64(), Some(delay_ms), "{} #{}", name, i),
                Decision::Failed => assert_eq!(expect[i].as_str(), Some("failed"), "{} #{}", name, i),
            }
        }
    }
}

#[test]
fn batch_vectors() {
    let doc = load("batch.json");
    let limits = &doc["limits"];
    let cases = arr(&doc, "cases");
    assert!(cases.len() >= 6);
    for case in cases {
        let name = case["name"].as_str().unwrap();
        let mut batcher = Batcher::new(
            limits["max_frames"].as_u64().unwrap() as usize,
            limits["max_age_ms"].as_u64().unwrap(),
            limits["queue_limit"].as_u64().unwrap() as usize,
        );
        for op in arr(case, "ops") {
            let t = op["t"].as_u64().unwrap();
            match op["op"].as_str().unwrap() {
                "push" => batcher.push(op["frame"].as_str().unwrap().to_owned(), t),
                "push_n" => {
                    let start = op["start"].as_u64().unwrap_or(0);
                    let prefix = op["prefix"].as_str().unwrap();
                    for i in start..start + op["count"].as_u64().unwrap() {
                        batcher.push(format!("{}{}", prefix, i), t);
                    }
                }
                "poll" => match batcher.poll(t) {
                    None => assert!(op["expect"].is_null(), "{}", name),
                    Some(batch) => {
                        let expect = &op["expect"];
                        assert_eq!(expect["count"].as_u64(), Some(batch.frames.len() as u64), "{}", name);
                        assert_eq!(expect["first"].as_str(), batch.frames.first().map(String::as_str), "{}", name);
                        assert_eq!(expect["last"].as_str(), batch.frames.last().map(String::as_str), "{}", name);
                        assert_eq!(expect["dropped"].as_u64(), Some(batch.dropped), "{}", name);
                    }
                },
                other => panic!("unknown op {}", other),
            }
        }
    }
}
