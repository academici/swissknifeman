fn main() {
    // The six commands of the adapter get the permissions `allow-<command>`; capabilities/default.json lists them.
    // The config and the capabilities sit one level above this crate (workspace layout of desktop/src-tauri).
    // tauri-build looks for tauri.conf.json in the current directory, so move there first; paths below are relative to it.
    std::env::set_current_dir("..").expect("desktop/src-tauri directory");
    println!("cargo:rerun-if-changed=tauri.conf.json");
    println!("cargo:rerun-if-changed=capabilities");
    let attributes = tauri_build::Attributes::new()
        .capabilities_path_pattern("capabilities/**/*")
        .app_manifest(tauri_build::AppManifest::new().commands(&[
            "api_request",
            "api_subscribe",
            "api_unsubscribe",
            "sidecar_status",
            "sidecar_restart",
            "sidecar_log",
        ]));
    tauri_build::try_build(attributes).expect("tauri build configuration");
}
