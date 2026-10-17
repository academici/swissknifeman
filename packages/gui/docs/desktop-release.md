# Desktop release (owner steps)

Everything below runs on the owner's machine (gate `GUI_TOOLCHAIN`, decisions D9 and D26). The repository holds sources,
configuration and scripts; nothing here was compiled, built, signed or installed by the development environment.
The signing key never enters the repository, CI or a script: scripts read nothing of it, and `tauri signer sign` reads
it only from the owner's environment (`TAURI_SIGNING_PRIVATE_KEY` holds the key content, or
`TAURI_SIGNING_PRIVATE_KEY_PATH` its path, with `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`).

## Steps, in order

1. **Toolchain.** Install `rustup` (stable) and the Tauri Linux packages: `build-essential`, `libssl-dev`,
   `libwebkit2gtk-4.1-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev`, `patchelf`; install the Tauri CLI
   (`cargo install tauri-cli --version "^2" --locked`) and PyInstaller in a virtual environment (`python3 -m venv ~/.venvs/skm-build && ~/.venvs/skm-build/bin/pip install pyinstaller`; run step 3 with `source ~/.venvs/skm-build/bin/activate`, because `build.sh` calls `python3 -m PyInstaller`). Check the versions against the
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
   capabilities (both sit in `src-tauri`), see "Not checked".
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

## Status of the first build (2026-10-17)

Steps 1 to 8 ran on the owner's machine: the Rust core tests pass, the sidecar builds and reaches `GUI_READY` in about 1 s,
`cargo tauri build` writes `SKM GUI_0.1.0_amd64.AppImage` and `.deb` with `.sig` files, and the AppImage starts the
application with the sidecar. Details and the findings of that build: `docs/desktop.md`, "Checked and not checked".
Left for the owner: the real https endpoint in `plugins.updater.endpoints` (then `check-release-config.py --release` passes),
a product icon (`cargo tauri icon <png>`), the key policy (the key of this build was created without a password in
`~/.keys/skm-gui-updater.key`; generate a new one with a password for releases and replace `plugins.updater.pubkey`), the
install and update checks (steps 11 and 12), macOS signing and notarization.

## Not checked

- Installing the `.deb`, the update flow against a real updater endpoint and the refusal of a wrong signature.
- The restart of the sidecar after a crash and the diagnostics screen in the real web view.
- macOS and other distributions; the behaviour of `Cargo.lock` against newer crate versions.

`smoke.sh` and `sidecar/build.sh` with `--allow-missing` only report `SKIPPED: GUI_TOOLCHAIN` when the tools are missing; such a line is not a verified build.
