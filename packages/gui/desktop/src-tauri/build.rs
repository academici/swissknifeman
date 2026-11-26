fn main() {
    // The six commands of the adapter get the permissions `allow-<command>`; capabilities/default.json lists them.
    // The crate sits in desktop/src-tauri with tauri.conf.json and capabilities/ (the layout the Tauri CLI expects).
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
