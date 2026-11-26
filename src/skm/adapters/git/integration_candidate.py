"""Owned scratch projection and independent validation of the accepted task delta."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from skm.adapters.git.commit import author_env
from skm.adapters.git.host_inputs import capture_checkout
from skm.adapters.git.output_writer import verify_sealed_output
from skm.adapters.git.runner import GitRunner
from skm.adapters.git.status import tree_entries
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.ids import ExternalEffectId
from skm.modules.execution.domain.integration import TRAILER_NAMES, CommitMode, commit_trailers
from skm.modules.execution.domain.output import matches_path

__all__: list[str] = []


class IntegrationCandidate:
    git: GitRunner
    root: Path

    def _text(self, repo: Path, args: list[str]) -> str:
        return self.git.run(repo, args).stdout.strip()

    def _verify_outputs(self, repo: Path, inputs: Mapping[str, Any]) -> None:
        source = capture_checkout(Path(inputs.get("source_repo", repo)))
        for output in inputs["outputs"]:
            verify_sealed_output(
                self.git,
                source,
                attempt_id=UUID(inputs["attempt_id"]),
                mount=inputs["mount"],
                output_no=output["output_no"],
                output_id=UUID(output["output_id"]),
                head=output["head_sha"],
                manifest_digest=output["output_digest"],
            )

    def _patch(self, repo: Path, base: str, head: str, excludes: list[str]) -> bytes:
        return self.git.run_bytes(
            repo,
            [
                "diff",
                "--binary",
                "--full-index",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                base,
                head,
                "--",
                ".",
                *(":(exclude,glob)" + p for p in excludes),
            ],
        ).stdout

    def _apply(self, scratch: Path, patch: bytes) -> None:
        if (
            patch
            and self.git.run_bytes(
                scratch, ["apply", "--3way", "--index", "--binary", "-"], stdin=patch, check=False
            ).exit_code
        ):
            raise error_for(ErrorCode.INTEGRATION_CONFLICT, "task delta conflicts with target")

    def _verify_delta(self, repo: Path, before: str, patch: bytes, tree: str) -> None:
        # A separate index verifies the complete result, including modes, binary hunks and deletions.
        with tempfile.TemporaryDirectory(dir=self.root, prefix="verify-") as directory:
            env = {"GIT_INDEX_FILE": str(Path(directory) / "index")}
            self.git.run_bytes(repo, ["read-tree", before], env=env)
            if patch:
                self.git.run_bytes(
                    repo, ["apply", "--cached", "--3way", "--binary", "-"], stdin=patch, env=env
                )
            expected = self.git.run_bytes(repo, ["write-tree"], env=env).stdout.decode().strip()
            if expected != tree:
                raise error_for(ErrorCode.INTEGRATION_CONFLICT, "candidate differs from exact task delta")

    def _guard_artifacts(self, repo: Path, tree: str, inputs: Mapping[str, Any]) -> None:
        forbidden = set(inputs.get("artifact_digests", []))
        excludes = inputs.get("exclude_paths", [".skm/**"])
        for path, fingerprint in tree_entries(self.git, repo, tree).items():
            digest = (
                "sha256:"
                + hashlib.sha256(
                    self.git.run_bytes(repo, ["cat-file", "blob", fingerprint.split(" ")[1]]).stdout
                ).hexdigest()
            )
            if digest in forbidden or any(
                matches_path(path.decode("utf-8", "surrogateescape"), p) for p in excludes
            ):
                raise error_for(ErrorCode.RUNTIME_ARTIFACT_IN_COMMIT, "runtime artifact in candidate tree")

    def _candidate(
        self,
        repo: Path,
        scratch: Path,
        before: str,
        effect_id: ExternalEffectId,
        inputs: Mapping[str, Any],
        mode: CommitMode,
    ) -> tuple[list[str], str]:
        outputs = inputs["outputs"]
        squash = inputs.get("strategy", "squash") == "squash"
        selected = outputs[-1:] if mode is CommitMode.FINAL_ONLY and squash else outputs
        if not selected:
            raise ValueError("accepted output required")
        commits: list[str] = []
        tree, text = "", ""
        base, parent = str(inputs["baseline_sha"]), before
        for output in selected:
            head = str(output["head_sha"])
            patch = self._patch(repo, base, head, inputs.get("exclude_paths", [".skm/**"]))
            self._apply(scratch, patch)
            tree = self._text(scratch, ["write-tree"])
            self._guard_artifacts(scratch, tree, inputs)
            self._verify_delta(repo, parent, patch, tree)
            if mode in {CommitMode.FINAL_ONLY, CommitMode.PER_STAGE_ATTRIBUTED} and tree == self._text(
                repo, ["rev-parse", parent + "^{tree}"]
            ):
                base = head
                continue
            # The published final-only identity belongs to the accepted output, including when
            # its tree is unchanged and its projection is skipped after an earlier changed output.
            identity_output = outputs[-1] if mode is CommitMode.FINAL_ONLY else output
            identity = {**inputs, **identity_output, "effect_id": str(effect_id)}
            trailers = commit_trailers(identity)
            message = str(inputs.get("message", "chore: integrate accepted output"))
            if "\0" in message or any(
                line.lstrip().lower().startswith("skm-")
                or line.partition(":")[0].strip().lower() in TRAILER_NAMES
                for line in message.splitlines()
            ):
                raise ValueError("registrar message contains identity trailers")
            text = message.rstrip() + "\n\n" + "\n".join(f"{k}: {v}" for k, v in trailers) + "\n"
            parent = (
                self.git.run_bytes(
                    scratch, ["commit-tree", tree, "-p", parent], env=author_env(None), stdin=text.encode()
                )
                .stdout.decode()
                .strip()
            )
            commits.append(parent)
            self.git.run(scratch, ["reset", "--hard", parent])
            base = head
        # Also validate the final combined tree against B -> accepted output, independently of projection.
        final_patch = self._patch(
            repo,
            str(inputs["baseline_sha"]),
            str(outputs[-1]["head_sha"]),
            inputs.get("exclude_paths", [".skm/**"]),
        )
        self._verify_delta(repo, before, final_patch, tree)
        if mode is CommitMode.FINAL_ONLY and tree == self._text(repo, ["rev-parse", before + "^{tree}"]):
            self.git.run(scratch, ["reset", "--hard", before])
            return [], tree
        if mode is CommitMode.FINAL_ONLY and len(commits) > 1:
            final = (
                self.git.run_bytes(
                    scratch, ["commit-tree", tree, "-p", before], env=author_env(None), stdin=text.encode()
                )
                .stdout.decode()
                .strip()
            )
            commits = [final]
            self.git.run(scratch, ["reset", "--hard", final])
        return commits, tree
