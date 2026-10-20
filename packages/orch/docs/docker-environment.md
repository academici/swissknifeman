# Docker environment (optional)

orch does not need Docker. When it is installed, the acceptance checks of a piece of work usually run in containers, and
the conductor starts them as the user that runs it. This page says how to check that setup and how to make it safer.

## Check it

```bash
python3 packages/orch/scripts/docker-env-check.py          # text
python3 packages/orch/scripts/docker-env-check.py --json   # check-result/v1 rows
swissknifeman orch doctor                                  # the same rows among the others
```

| Row | Says |
|---|---|
| `orch.docker` | whether the daemon can be used, whether it is rootless, and who owns the socket. A **rootful** daemon reached through the `docker` group is a `warn`: whoever controls it controls the host as root (a container can mount `/`), and the checks, tests and compose files of the work run with that authority |
| `orch.docker-credentials` | `fail` when `~/.docker/config.json` names a credential helper (`credsStore`, `credHelpers`) whose `docker-credential-<name>` is not installed: every pull and build then fails |
| `orch.docker-compose` | the compose plugin answers |

Without the `docker` CLI every row is `skip`. A `warn` is advice, not an error.

The executor of a piece of work (the Codex sandbox) cannot reach the Docker socket, by design: the conductor runs the
container checks after the executor's report, outside its sandbox (`done_pending_checks`).

## Make it safer: rootless Docker

Rootless Docker runs the daemon and the containers as an ordinary user, so a container does not give root on the host.
The steps below are for Ubuntu 24.04 with `docker-ce` and `docker-ce-rootless-extras` from the Docker apt repository (other
systems: <https://docs.docker.com/engine/security/rootless/>). Run them as your normal user, in a real login session, never
as `sudo -i` / `sudo su`. They install the rootless daemon **next to** the rootful one, so nothing is lost and nothing
stops while you try it. The two daemons have separate sockets and storage: the images, volumes and containers of the
rootful daemon are not visible to the rootless one, and images are pulled or built again.

**1. Install (one time)**

```bash
sudo apt-get install -y uidmap slirp4netns dbus-user-session   # newuidmap/newgidmap, rootless networking, user D-Bus
grep "^$USER:" /etc/subuid /etc/subgid                          # expect a line with 65536 ids in both files
ls /etc/apparmor.d/rootlesskit                                  # Ubuntu ships the AppArmor profile for /usr/bin/rootlesskit
```

Ubuntu 24.04 restricts unprivileged user namespaces (`kernel.apparmor_restrict_unprivileged_userns=1`); leave that on. The
packaged profile above allows RootlessKit; if the file is missing, `sudo apt-get install --reinstall apparmor` restores it.

**2. Create and start the rootless daemon**

```bash
unset DOCKER_HOST DOCKER_CONTEXT
dockerd-rootless-setuptool.sh install --force    # --force: the rootful daemon keeps running
systemctl --user enable --now docker             # the daemon is a service of your user, not of root
sudo loginctl enable-linger "$USER"              # start it at boot, without a login
docker context use rootless                      # the docker CLI now talks to /run/user/<uid>/docker.sock
```

**3. Verify**

```bash
docker info --format '{{json .SecurityOptions}}'   # expect "name=rootless" in the list
docker run --rm hello-world
python3 packages/orch/scripts/docker-env-check.py  # expect OK orch.docker, "the daemon is rootless"
```

If the daemon does not start: `journalctl --user -u docker.service -b --no-pager -n 100`. Published ports below 1024 need
an extra setting in rootless mode; test with a port such as 8080 first. Do not publish the same host port from both
daemons.

**4. Drop the root-equivalent access (only after your project works on the rootless daemon)**

```bash
sudo gpasswd -d "$USER" docker                   # takes effect at the next login
sudo systemctl disable --now docker.service docker.socket   # optional: stop the rootful daemon altogether
```

Its images, volumes and containers stay on disk (`/var/lib/docker`) and come back with `sudo systemctl enable --now
docker.service docker.socket` and `sudo usermod -aG docker "$USER"`.

**Roll back the rootless daemon**

```bash
docker context use default
dockerd-rootless-setuptool.sh uninstall          # removes the user service, keeps the data
docker context rm rootless
sudo loginctl disable-linger "$USER"             # only if nothing else of yours needs lingering
```

A rootless daemon has the authority of its user. If that user is you, a container can still read your files; for an
autonomous agent the stronger setup is a **dedicated account** that owns the rootless daemon and a checkout of its own.
