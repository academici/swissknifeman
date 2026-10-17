# Desktop release (owner steps)

Everything below runs on the owner's machine (gate `GUI_TOOLCHAIN`, decisions D9 and D26). The repository holds sources,
configuration and scripts; nothing here was compiled, built, signed or installed by the development environment.
The signing key never enters the repository, CI or a script: scripts read nothing of it, and `tauri signer sign` reads
it only from the owner's environment (`TAURI_SIGNING_PRIVATE_KEY` holds the key content, or
`TAURI_SIGNING_PRIVATE_KEY_PATH` its path, with `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`).

## Steps, in order

1. **Toolchain.** Install `rustup` (stable) and the Tauri Linux packages: `build-essential`, `libssl-dev`,
   `libwebkit2gtk-4.1-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev`, `patchelf`; install the Tauri CLI
   (`cargo install tauri-cli --version "^2" --locked`) and `pip install pyinstaller`. Check the versions against the
   registries; `Cargo.lock` is not committed, commit it after the first build.
2. **Rust core tests.** `cd packages/gui/desktop/src-tauri && cargo test -p skm-gui-core` (reads `desktop/tests/vectors/*.json`).
3. **Sidecar.** `bash packages/gui/sidecar/build.sh` builds `sidecar/dist/gui-backend-<target-triple>/`. Copy the tree to
   `packages/gui/desktop/src-tauri/binaries/gui-backend-onedir/` (it goes to `resources`; the shell starts
   `gui-backend/gui-backend` from the resource directory, so the executable stays next to its runtime directory; there is no `externalBin`).
4. **Sidecar check.** `bash packages/gui/desktop/scripts/smoke.sh` starts the built `gui-backend`, sends the handshake and waits
   for `GUI_READY` (limit 20 s). Also request `GET /v1/bootstrap` with the Bearer secret against the printed port.
5. **Frontend.** `npm --prefix packages/gui/frontend ci && npm --prefix packages/gui/frontend run build`.
6. **Updater key.** `cargo tauri signer generate -w <path outside the repository>`; keep the private key and its password
   outside the repository and CI. Put the **public** key content in `plugins.updater.pubkey` and the real https URL in
   `plugins.updater.endpoints` of `tauri.conf.json`.
7. **Release config.** `python3 packages/gui/desktop/scripts/check-release-config.py --release` must exit 0.
8. **Bundle.** `cd packages/gui/desktop/src-tauri && cargo tauri build` (AppImage, deb, `.app` on macOS; with
   `createUpdaterArtifacts` it also writes the update archives). If the build cannot find `tauri.conf.json` or the
   capabilities (the crate lives in `src-tauri/app`), see "Not checked".
9. **Sign.** On the trusted machine, with the key in the environment: `cargo tauri signer sign` for each updater artifact,
   passing the app version (`--app-version`), so a signed version cannot be swapped in an unsigned update JSON; use
   `requireSignedVersion` of the CLI (2.12.0 or newer, check the registry).
10. **Update JSON.** `python3 packages/gui/desktop/scripts/make-update-json.py --version V --platform linux-x86_64
    --artifact <archive> --sig <archive>.sig --url https://... --out latest.json`; publish it with the artifacts over https.
    The script refuses an empty signature, a non-semver version, a non-https url and missing files; it does not verify the
    signature (the updater does, with the public key).
11. **Install check.** Install the `.deb` and run the AppImage on a clean machine; start, see the diagnostics screen turn into
    the application, restart the sidecar from the diagnostics screen, close the window and check that no `gui-backend`
    process stays.
12. **Update check.** Install the previous build, publish the new update JSON, and check that the application updates and
    refuses an artifact with a wrong signature.

Updater signing (minisign) is not platform signing: on macOS the owner also signs and notarizes the `.app` (Apple
Developer ID, `notarytool`); on Linux there is no notarization. Updating a `.deb` may need `sudo`/`dpkg`; check this flow on
each supported distribution.

## Not checked in the repository

- Compilation of any Rust file (`core`, `app`) and the `cargo test` of the vectors.
- The PyInstaller build of the sidecar: the `gui-backend.spec` data layout (`src/gui/lib`, `src/aicore/lib` with schemas and
  `unit.json`) and the in-place filter of `a.pure` are confirmed only by the first build; run the built `gui-backend`, give
  the handshake, get `GUI_READY` and `GET /v1/bootstrap`.
- The `tauri build` bundle, the use of `generate_context!("../tauri.conf.json")` and `set_current_dir("..")` in `build.rs` with the config
  outside the crate directory, and the shell plugin starting a sidecar from the onedir resource tree.
- Signing, the update JSON against a real updater, the update flow of deb and AppImage.
- Installation of deb and AppImage and the behaviour of the web view (WebKitGTK) with the CSP and the global `__TAURI__`.
- The supervisor (restart policy, SIGTERM instead of closing stdin) and the adapter at run time.

`smoke.sh`, `sidecar/build.sh` with `--allow-missing` only report `SKIPPED: GUI_TOOLCHAIN`; such a line is not a verified build.
