//! Pure logic of the desktop shell. No Tauri, no I/O: everything here is checked by `cargo test` against the vectors
//! in `desktop/tests/vectors/*.json`, which are the single source of expected values (the Python oracle reads the same).

pub mod adapter;
pub mod backoff;
pub mod batch;
pub mod ready;
