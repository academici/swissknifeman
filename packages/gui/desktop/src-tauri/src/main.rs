// Thin shell: wires plugins, the sidecar supervisor and the six adapter commands. Logic lives in `skm-gui-core`.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod sidecar;

use std::sync::Arc;
use tauri::{Manager, RunEvent, WindowEvent};
use tauri_plugin_deep_link::DeepLinkExt;

fn show_main(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let shared = sidecar::start(app.handle().clone());
            app.manage(shared);
            app.manage(Arc::new(commands::Subscriptions::default()));
            // A skm-gui:// link only brings the window forward; its content is never interpreted.
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |_event| show_main(&handle));
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::Destroyed = event {
                if let Some(subs) = window.app_handle().try_state::<Arc<commands::Subscriptions>>() {
                    subs.abort_all();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::api_request,
            commands::api_subscribe,
            commands::api_unsubscribe,
            commands::sidecar_status,
            commands::sidecar_restart,
            commands::sidecar_log,
        ])
        .build(tauri::generate_context!())
        .expect("tauri application");

    app.run(|handle, event| {
        // The last window is closed: the sidecar goes down with the shell.
        if let RunEvent::Exit = event {
            if let Some(shared) = handle.try_state::<Arc<sidecar::Shared>>() {
                if let Some(subs) = handle.try_state::<Arc<commands::Subscriptions>>() {
                    subs.abort_all();
                }
                tauri::async_runtime::block_on(shared.shutdown());
            }
        }
    });
}
