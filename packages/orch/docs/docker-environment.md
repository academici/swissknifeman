# Docker environment (optional)

orch does not need Docker. When it is installed, the acceptance checks of a piece of work usually run in containers, and
the conductor starts them as the user that runs it. This page says how to check that setup, why it is safer rootless, and
how to build the whole thing from a clean Ubuntu machine, so that it can be restored on another computer.

## Why rootless

A rootful Docker daemon is root on the host for everyone who can reach its socket: a member of the `docker` group can
start a container that mounts `/`. Everything the conductor runs in containers (checks, tests, compose files written by the
work) then has that authority. A rootless daemon runs as an ordinary user: root inside a container is only that user outside,
so a container cannot touch the system. The executor of a piece of work (the Codex sandbox) cannot reach any Docker socket,
by design; the conductor runs the container checks after the executor's report, outside its sandbox (the
`done_pending_checks` status).

## Check it

This is a branch apart from orchestration: no run, claim or conductor step calls it, and `orch doctor` does not run it. It is
a probe of the environment doctor, to be run **once** when Docker is in use; a `warn` row points to this page, and once the
machine is set up as below nothing needs to be revisited.

```bash
swissknifeman doctor --unit orch --category environment   # the environment doctor (rows orch.docker*)
python3 packages/orch/scripts/docker-env-check.py          # the same probe on its own, text
python3 packages/orch/scripts/docker-env-check.py --json   # check-result/v1 rows
```

Every command it runs (`docker info`, `docker context inspect`, `docker compose version`) is limited to 5 seconds.

| Row | Says |
|---|---|
| `orch.docker` | whether the daemon can be used, whether it is rootless, and who owns the socket. A **rootful** daemon reached through the `docker` group is a `warn` (root-equivalent, see above); a rootless one is `ok` |
| `orch.docker-credentials` | `fail` when `~/.docker/config.json` names a credential helper (`credsStore`, `credHelpers`) whose `docker-credential-<name>` is not installed: every pull and build then fails |
| `orch.docker-compose` | the compose plugin answers |

Without the `docker` CLI every row is `skip`. A `warn` is advice, not an error. Exit code 1 only for a `fail` row.

## Build it from a clean Ubuntu 24.04 machine

Run as your normal user in a real login session (SSH or the desktop), never inside `sudo -i` or `sudo su`: the user
systemd/D-Bus session must be yours. Every step is safe to repeat.

**1. Docker Engine from the Docker apt repository** (skip when `docker-ce` and `docker-ce-rootless-extras` are installed):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras
```

**2. Prerequisites of the rootless mode**

```bash
sudo apt-get install -y uidmap slirp4netns dbus-user-session
grep "^$USER:" /etc/subuid /etc/subgid     # each file needs a line with 65536 ids, e.g. youruser:100000:65536
ls /etc/apparmor.d/rootlesskit             # Ubuntu's AppArmor profile for /usr/bin/rootlesskit
```

If the `subuid`/`subgid` lines are missing: `sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$USER"`
(pick ranges no other account uses). Ubuntu 24.04 restricts unprivileged user namespaces
(`kernel.apparmor_restrict_unprivileged_userns=1`); leave that on, the packaged profile above allows RootlessKit. If the
profile file is missing, `sudo apt-get install --reinstall apparmor` restores it.

**3. A fresh machine: stop the rootful daemon** (the package starts it); skip this on a machine whose rootful containers you
still need, and use `--force` in step 4 instead (see "Side by side"):

```bash
sudo systemctl disable --now docker.service docker.socket
```

**4. Create and start the rootless daemon**

```bash
unset DOCKER_HOST DOCKER_CONTEXT
dockerd-rootless-setuptool.sh install            # on a machine that keeps the rootful daemon: install --force
systemctl --user enable --now docker             # the daemon is a service of your user, not of root
sudo loginctl enable-linger "$USER"              # start it at boot, without a login
docker context use rootless                      # the CLI now talks to /run/user/<uid>/docker.sock (saved in ~/.docker/config.json)
```

The installer prints `export PATH=/usr/bin:$PATH` and `export DOCKER_HOST=unix:///run/user/<uid>/docker.sock`; neither is
needed here (`/usr/bin` is on the PATH, and the context carries the socket). Set `DOCKER_HOST` only for a tool that ignores
Docker contexts.

**5. Verify**

```bash
docker context show                                # rootless
docker info --format '{{json .SecurityOptions}}'   # a list with "name=rootless"
docker run --rm hello-world
loginctl show-user "$USER" -p Linger               # Linger=yes
python3 packages/orch/scripts/docker-env-check.py  # OK orch.docker, "the daemon is rootless"
```

**6. Take the root-equivalent access away** (after your project works on the rootless daemon; a re-login makes it effective):

```bash
sudo gpasswd -d "$USER" docker
```

On a fresh machine you were never in the group: do not add yourself (`sudo usermod -aG docker "$USER"` is the thing to avoid).

## Optional settings

- **Resource limits** (`docker run --cpus/--memory/--pids-limit`): the warnings "No io.max (rbps) support" in the daemon log
  mean the user session does not own those cgroup controllers. Delegate them, then log in again:

  ```bash
  printf '[Service]\nDelegate=cpu cpuset io memory pids\n' | sudo systemctl edit --stdin user@.service
  ```

- **Ports below 1024** (a compose file that publishes `80`): rootless cannot bind them unless allowed. Either publish a high
  port, or: `printf 'net.ipv4.ip_unprivileged_port_start=80\n' | sudo tee /etc/sysctl.d/99-rootless-ports.conf && sudo sysctl --system`.
- **Do not publish the same host port from both daemons** when they run side by side.
- **Faster networking** than slirp4netns (`passt`/`pasta`): see the Docker rootless documentation; it is experimental.

## Differences you will meet

- Root inside a container is **your user** outside: files a container writes into a bind mount belong to you, not to root.
  A user other than root inside the container appears as a sub-uid (`100000+`) on the host.
- A compose file or a tool that mounts `/var/run/docker.sock` into a container must mount `/run/user/<uid>/docker.sock` instead
  (`$XDG_RUNTIME_DIR/docker.sock`).
- The rootless daemon has its **own images, volumes and containers** (`~/.local/share/docker`), apart from the rootful ones
  (`/var/lib/docker`). The first build or pull of every image happens again.
- Storage is yours: `docker system df`, `docker system prune -a --volumes` clean the rootless daemon only.

## Side by side with an existing rootful daemon, and clearing it

To try rootless without stopping anything, use `dockerd-rootless-setuptool.sh install --force` in step 4 and skip step 3. The
two daemons have separate sockets and storage. Switch with `docker context use rootless` / `docker context use default`, or
address one for a single command: `docker --context default ps`.

When the rootful data is no longer needed, clear it and stop the daemon:

```bash
docker --context default ps -aq | xargs -r docker --context default rm -f        # containers
docker --context default system prune -a --volumes -f                            # images, networks, volumes, build cache
sudo systemctl disable --now docker.service docker.socket
```

## Roll back

```bash
docker context use default                       # back to the rootful daemon (if it still runs)
dockerd-rootless-setuptool.sh uninstall          # removes the user service, keeps the data
docker context rm rootless
sudo loginctl disable-linger "$USER"             # only if nothing else of yours needs lingering
rootlesskit rm -rf "$HOME/.local/share/docker"   # optional: delete the rootless images, containers and volumes
sudo systemctl enable --now docker.service docker.socket   # only if you disabled the rootful daemon
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `context "rootless": context not found` | the context is created by `dockerd-rootless-setuptool.sh install`; run step 4 first |
| `newuidmap: not found` / the installer asks for `uidmap` | `sudo apt-get install -y uidmap` |
| the installer says the systemd user session is not available, `Failed to connect to bus` | log in again as the user (not through `sudo -i`), install `dbus-user-session`, check `systemctl --user is-system-running` (`degraded` is fine, it only means an unrelated unit failed) |
| the daemon does not start | `journalctl --user -u docker.service -b --no-pager -n 100`; on Ubuntu 24.04 check the AppArmor profile of step 2 |
| the daemon is gone after logout | `sudo loginctl enable-linger "$USER"` |
| `permission denied` on `/var/run/docker.sock` | you are on the rootful context without the `docker` group; use `docker context use rootless` |
| every pull fails with `error getting credentials - exec: "docker-credential-…": executable file not found` | `~/.docker/config.json` names a helper that is not installed: install it, or remove the `credsStore`/`credHelpers` entry (a file of yours) |
| a port below 1024 is refused | see "Optional settings" |

## A dedicated account (stronger)

A rootless daemon has the authority of its user. If that user is you, a container can still read your files. For an autonomous
agent that is to run containers itself, the stronger setup is a **dedicated account** that owns the rootless daemon and a
checkout of its own, with no access to your home. orch does not need this today (the conductor, not the executor, runs the
container checks), and it does not set it up.
