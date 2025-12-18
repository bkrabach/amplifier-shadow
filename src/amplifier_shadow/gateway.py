"""Shadow Environment Gateway.

Provides programmatic interface for interacting with shadow environments.
Designed for use by recipes and automation tools.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ExecResult:
    """Result of executing a command in shadow environment."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0

    def raise_on_error(self) -> None:
        """Raise exception if command failed."""
        if not self.success:
            raise RuntimeError(f"Command failed (exit {self.returncode}): {self.stderr}")


def _get_shadow_config_dir() -> Path:
    """Get the directory for shadow configuration files."""
    base_dir = Path.home() / ".amplifier" / "shadow" / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


class ShadowGateway:
    """Bridge between host and shadow environment.

    Provides methods for:
    - Executing commands inside the shadow workspace
    - Reading/writing files via volume mount
    - Managing the shadow lifecycle

    Example:
        >>> gateway = ShadowGateway("my-experiment")
        >>> result = await gateway.exec("amplifier run 'hello world'")
        >>> print(result.stdout)
    """

    def __init__(
        self,
        shadow_name: str = "default",
        workspace_path: Path | None = None,
        gitea_port: int = 3000,
    ):
        """Initialize gateway to shadow environment.

        Args:
            shadow_name: Unique identifier for this shadow environment
            workspace_path: Host path mounted as /workspace in container
            gitea_port: Port for Gitea server (default 3000)
        """
        self.shadow_name = shadow_name
        self.workspace_path = workspace_path or Path.cwd()
        self.gitea_port = gitea_port
        self._templates_dir = Path(__file__).parent.parent.parent / "templates"

    @property
    def _config_file(self) -> Path:
        """Path to this shadow's config file."""
        return _get_shadow_config_dir() / f"{self.shadow_name}.json"

    def _save_config(self) -> None:
        """Save shadow configuration for later use by diff/promote commands."""
        config = {
            "workspace_path": str(self.workspace_path.absolute()),
            "gitea_port": self.gitea_port,
        }
        self._config_file.write_text(json.dumps(config, indent=2))

    def _load_config(self) -> bool:
        """Load saved shadow configuration.

        Returns:
            True if config was loaded and applied, False if no config exists.
        """
        if not self._config_file.exists():
            return False
        try:
            config = json.loads(self._config_file.read_text())
            self.workspace_path = Path(config["workspace_path"])
            self.gitea_port = config.get("gitea_port", 3000)
            return True
        except (json.JSONDecodeError, KeyError):
            return False

    @classmethod
    def from_saved_config(cls, shadow_name: str = "default") -> "ShadowGateway":
        """Create a gateway using saved configuration.

        This is useful for commands like diff/promote that need to know
        the original workspace path used when the shadow was started.

        Args:
            shadow_name: Name of the shadow environment

        Returns:
            ShadowGateway with workspace_path from saved config, or defaults
        """
        gateway = cls(shadow_name=shadow_name)
        gateway._load_config()
        return gateway

    @property
    def compose_file(self) -> Path:
        """Path to docker-compose.yaml."""
        return self._templates_dir / "docker-compose.yaml"

    @property
    def gitea_url(self) -> str:
        """URL to Gitea server from host."""
        return f"http://localhost:{self.gitea_port}"

    @property
    def gitea_internal_url(self) -> str:
        """URL to Gitea server from inside shadow network."""
        return "http://gitea:3000"

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for docker-compose commands."""
        return {
            "SHADOW_NAME": self.shadow_name,
            "WORKSPACE_DIR": str(self.workspace_path.absolute()),
            "GITEA_PORT": str(self.gitea_port),
        }

    def exec(self, command: str, timeout: int = 300) -> ExecResult:
        """Execute shell command inside shadow workspace container.

        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds

        Returns:
            ExecResult with returncode, stdout, stderr
        """
        docker_cmd = [
            "docker",
            "compose",
            "-f",
            str(self.compose_file),
            "exec",
            "-T",  # No TTY for automation
            "workspace",
            "bash",
            "-c",
            command,
        ]

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, **self._get_env()},
            )
            return ExecResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired as e:
            return ExecResult(
                returncode=-1,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Command timed out after {timeout}s",
            )

    def read_file(self, path: str) -> str:
        """Read file from shadow workspace via volume mount.

        Args:
            path: Path relative to /workspace in container

        Returns:
            File contents as string
        """
        file_path = self.workspace_path / path
        return file_path.read_text()

    def write_file(self, path: str, content: str) -> None:
        """Write file to shadow workspace via volume mount.

        Args:
            path: Path relative to /workspace in container
            content: Content to write
        """
        file_path = self.workspace_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    def read_json(self, path: str) -> Any:
        """Read JSON file from shadow workspace."""
        return json.loads(self.read_file(path))

    def write_json(self, path: str, data: Any) -> None:
        """Write JSON file to shadow workspace."""
        self.write_file(path, json.dumps(data, indent=2))

    def is_running(self) -> bool:
        """Check if shadow environment is running."""
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "ps",
                "--status",
                "running",
                "-q",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, **self._get_env()},
        )
        return bool(result.stdout.strip())

    def start(self, copy_workspace: bool = True) -> ExecResult:
        """Start the shadow environment.

        Args:
            copy_workspace: If True (default), copy workspace into container after start

        Returns:
            ExecResult with success/failure info
        """
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "up",
                "-d",
                "--build",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, **self._get_env()},
        )

        if result.returncode != 0:
            return ExecResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        # Copy workspace into container if requested
        if copy_workspace:
            copy_result = self.copy_workspace_in()
            if not copy_result.success:
                return copy_result

            # Save config so diff/promote can find the original workspace path
            self._save_config()

            return ExecResult(
                returncode=0,
                stdout=f"{result.stdout}\n{copy_result.stdout}",
                stderr=result.stderr,
            )

        # Save config even if not copying (still useful for other commands)
        self._save_config()

        return ExecResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    @property
    def token_file(self) -> Path:
        """Path to API token file for this shadow.

        Stored in ~/.amplifier/shadow/tokens/ to avoid being inside any workspace.
        """
        base_dir = Path.home() / ".amplifier" / "shadow" / "tokens"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / f"{self.shadow_name}"

    def stop(self, remove_volumes: bool = False) -> ExecResult:
        """Stop the shadow environment.

        Args:
            remove_volumes: If True, also remove data volumes, token file, and snapshot
        """
        import shutil

        cmd = [
            "docker",
            "compose",
            "-f",
            str(self.compose_file),
            "down",
        ]
        if remove_volumes:
            cmd.append("-v")
            # Also remove the token file since Gitea DB is being deleted
            if self.token_file.exists():
                self.token_file.unlink()
            # Also remove the snapshot directory
            if self.snapshot_dir.exists():
                shutil.rmtree(self.snapshot_dir)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={**os.environ, **self._get_env()},
        )
        return ExecResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def get_logs(self, service: str = "workspace", tail: int = 100) -> str:
        """Get logs from a shadow service.

        Args:
            service: Service name (workspace or gitea)
            tail: Number of lines to return
        """
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "logs",
                "--tail",
                str(tail),
                service,
            ],
            capture_output=True,
            text=True,
            env={**os.environ, **self._get_env()},
        )
        return result.stdout

    # =========================================================================
    # Gitea Management
    # =========================================================================

    def _gitea_exec(self, command: str) -> ExecResult:
        """Execute command in Gitea container."""
        docker_cmd = [
            "docker",
            "compose",
            "-f",
            str(self.compose_file),
            "exec",
            "-T",
            "gitea",
            "bash",
            "-c",
            command,
        ]
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            env={**os.environ, **self._get_env()},
        )
        return ExecResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _gitea_api(self, method: str, endpoint: str, data: dict | None = None) -> tuple[int, str]:
        """Make authenticated API request to Gitea.

        Returns:
            Tuple of (http_status_code, response_body)
        """
        import urllib.error
        import urllib.request

        url = f"{self.gitea_url}/api/v1{endpoint}"
        token = self._load_token()

        headers = {"Authorization": f"token {token}"} if token else {}
        if data is not None:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode() if data else None,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
        except urllib.error.URLError as e:
            return 0, str(e.reason)

    def _load_token(self) -> str | None:
        """Load API token from file."""
        if self.token_file.exists():
            return self.token_file.read_text().strip()
        return None

    def _save_token(self, token: str) -> None:
        """Save API token to file."""
        self.token_file.write_text(token + "\n")
        self.token_file.chmod(0o600)

    def wait_for_gitea(self, timeout: int = 120) -> bool:
        """Wait for Gitea to be ready.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if Gitea is ready, False if timeout
        """
        import time
        import urllib.error
        import urllib.request

        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(f"{self.gitea_url}/api/healthz", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(2)
        return False

    def init_gitea(
        self,
        admin_user: str = "shadow-admin",
        admin_password: str = "shadow-admin",
        admin_email: str = "shadow@amplifier.local",
        org_name: str = "amplifier",
    ) -> ExecResult:
        """Initialize Gitea with admin user, API token, and organization.

        This replaces the init-shadow.sh script functionality.

        Args:
            admin_user: Admin username
            admin_password: Admin password
            admin_email: Admin email
            org_name: Organization name to create

        Returns:
            ExecResult with success/failure info
        """
        errors = []

        # 1. Create admin user
        result = self._gitea_exec(
            f"gitea admin user create --admin --username {admin_user} "
            f"--password {admin_password} --email {admin_email} --must-change-password=false"
        )
        if result.returncode != 0 and "already exists" not in result.stderr.lower():
            errors.append(f"Failed to create admin user: {result.stderr}")

        # 2. Generate API token
        result = self._gitea_exec(
            f"gitea admin user generate-access-token --username {admin_user} --token-name shadow-token --scopes all"
        )
        if result.returncode == 0:
            # Parse token from output: "Access token was successfully created: <token>"
            for line in result.stdout.strip().split("\n"):
                if ":" in line:
                    token = line.split(":")[-1].strip()
                    if token and len(token) > 20:
                        self._save_token(token)
                        break
        elif "already exists" not in result.stderr.lower():
            errors.append(f"Failed to generate token: {result.stderr}")

        # 3. Create organization via API
        status, body = self._gitea_api(
            "POST",
            "/orgs",
            {"username": org_name, "visibility": "public", "full_name": org_name},
        )
        if status not in (201, 409, 422):  # 409/422 = already exists
            errors.append(f"Failed to create organization: HTTP {status} - {body}")

        if errors:
            return ExecResult(returncode=1, stdout="", stderr="\n".join(errors))

        return ExecResult(
            returncode=0,
            stdout=f"Gitea initialized: admin={admin_user}, org={org_name}",
            stderr="",
        )

    def publish_module(self, module_path: Path) -> ExecResult:
        """Publish a module to shadow's Gitea.

        This replaces the publish-module.sh script functionality.

        Args:
            module_path: Path to module directory (must be a git repo)

        Returns:
            ExecResult with success/failure info
        """
        module_path = module_path.absolute()
        module_name = module_path.name

        # Verify it's a git repo
        if not (module_path / ".git").exists():
            return ExecResult(
                returncode=1,
                stdout="",
                stderr=f"Error: {module_path} is not a git repository",
            )

        # Check/create repo in Gitea
        status, body = self._gitea_api("GET", f"/repos/amplifier/{module_name}")
        if status != 200:
            # Create repo
            status, body = self._gitea_api(
                "POST",
                "/orgs/amplifier/repos",
                {
                    "name": module_name,
                    "description": f"Shadow copy of {module_name}",
                    "private": False,
                    "auto_init": False,
                },
            )
            if status not in (201, 409):  # 409 = already exists
                # Parse error message for helpful guidance
                error_msg = f"Failed to create repository (HTTP {status})\n\nAPI Response: {body}\n"
                if "invalid" in body.lower() and "token" in body.lower():
                    error_msg += (
                        "\nLikely cause: API token is invalid or expired.\n"
                        f"Fix: Delete token and reinitialize:\n"
                        f"  rm {self.token_file}\n"
                        f"  shadow init {self.shadow_name}"
                    )
                elif "not found" in body.lower() or "does not exist" in body.lower():
                    error_msg += (
                        "\nLikely cause: 'amplifier' organization does not exist.\n"
                        f"Fix: Initialize Gitea first:\n"
                        f"  shadow init {self.shadow_name}"
                    )
                return ExecResult(returncode=1, stdout="", stderr=error_msg)

        # Configure git and add shadow remote
        admin_user = os.environ.get("GITEA_ADMIN_USER", "shadow-admin")
        admin_pass = os.environ.get("GITEA_ADMIN_PASS", "shadow-admin")
        remote_url = f"http://{admin_user}:{admin_pass}@localhost:{self.gitea_port}/amplifier/{module_name}.git"

        # Run git commands in module directory
        def git_cmd(args: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git"] + args,
                cwd=module_path,
                capture_output=True,
                text=True,
            )

        # Disable SSL verify for local HTTP
        git_cmd(["config", "--local", "http.sslVerify", "false"])

        # Add or update shadow remote
        result = git_cmd(["remote", "get-url", "shadow"])
        if result.returncode == 0:
            git_cmd(["remote", "set-url", "shadow", remote_url])
        else:
            git_cmd(["remote", "add", "shadow", remote_url])

        # Get current branch
        result = git_cmd(["branch", "--show-current"])
        current_branch = result.stdout.strip() or "main"

        # Push to shadow
        result = git_cmd(["push", "-f", "shadow", f"{current_branch}:main"])
        if result.returncode != 0:
            return ExecResult(
                returncode=1,
                stdout="",
                stderr=f"Git push failed:\n{result.stderr}",
            )

        return ExecResult(
            returncode=0,
            stdout=(
                f"Published {module_name} to shadow\n"
                f"  Host URL: {self.gitea_url}/amplifier/{module_name}\n"
                f"  Shadow URL: {self.gitea_internal_url}/amplifier/{module_name}\n"
                f"  Install: uv pip install 'git+{self.gitea_internal_url}/amplifier/{module_name}.git@main'"
            ),
            stderr="",
        )

    # =========================================================================
    # Isolated Workspace Operations
    # =========================================================================

    @property
    def snapshot_dir(self) -> Path:
        """Directory for storing original workspace snapshot.

        Stored in ~/.amplifier/shadow/snapshots/ to avoid being inside any workspace.
        This prevents recursive copying when the workspace contains the snapshot.
        """
        base_dir = Path.home() / ".amplifier" / "shadow" / "snapshots"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / f"{self.shadow_name}"

    def copy_workspace_in(self) -> ExecResult:
        """Copy workspace directory into the isolated container.

        This copies the host workspace into /workspace inside the container.
        Also saves a snapshot of the original state for later diff/promote.

        Returns:
            ExecResult with success/failure info
        """
        import shutil

        container_name = f"{self.shadow_name}-workspace"

        # Verify container is running
        if not self.is_running():
            return ExecResult(
                returncode=1,
                stdout="",
                stderr="Shadow environment is not running. Start it first.",
            )

        # Save snapshot of original workspace for diff
        if self.snapshot_dir.exists():
            shutil.rmtree(self.snapshot_dir)
        shutil.copytree(
            self.workspace_path,
            self.snapshot_dir,
            ignore=shutil.ignore_patterns(
                ".git",
                "__pycache__",
                "*.pyc",
                ".venv",
                "node_modules",
                ".shadow-snapshot-*",
                ".shadow-token-*",  # Exclude shadow artifacts
            ),
        )

        # Clear existing /workspace content in container
        clear_result = self.exec("rm -rf /workspace/* /workspace/.[!.]* 2>/dev/null || true")
        if clear_result.returncode not in (0, 1):  # 1 is ok if no hidden files
            return ExecResult(
                returncode=1,
                stdout="",
                stderr=f"Failed to clear workspace: {clear_result.stderr}",
            )

        # Copy workspace into container
        result = subprocess.run(
            ["docker", "cp", f"{self.workspace_path}/.", f"{container_name}:/workspace/"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ExecResult(
                returncode=1,
                stdout="",
                stderr=f"Failed to copy workspace into container: {result.stderr}",
            )

        return ExecResult(
            returncode=0,
            stdout=f"Copied {self.workspace_path} into shadow workspace",
            stderr="",
        )

    def diff(self) -> ExecResult:
        """Show changes made in shadow workspace vs original.

        Compares current container state against the snapshot taken when
        copy_workspace_in() was called.

        Returns:
            ExecResult with diff output in stdout
        """
        import tempfile

        container_name = f"{self.shadow_name}-workspace"

        # Verify snapshot exists
        if not self.snapshot_dir.exists():
            return ExecResult(
                returncode=1,
                stdout="",
                stderr="No snapshot found. Did you run copy_workspace_in()?",
            )

        # Copy current workspace from container to temp dir
        with tempfile.TemporaryDirectory() as tmpdir:
            current_dir = Path(tmpdir) / "current"
            current_dir.mkdir()

            # Copy from container
            result = subprocess.run(
                ["docker", "cp", f"{container_name}:/workspace/.", str(current_dir)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return ExecResult(
                    returncode=1,
                    stdout="",
                    stderr=f"Failed to copy workspace from container: {result.stderr}",
                )

            # Run diff between snapshot and current
            result = subprocess.run(
                [
                    "diff",
                    "-rq",
                    "--exclude=.git",
                    "--exclude=__pycache__",
                    "--exclude=*.pyc",
                    "--exclude=.venv",
                    "--exclude=node_modules",
                    str(self.snapshot_dir),
                    str(current_dir),
                ],
                capture_output=True,
                text=True,
            )

            # diff returns 1 if differences found (not an error)
            if result.returncode == 0:
                return ExecResult(
                    returncode=0,
                    stdout="No changes detected.",
                    stderr="",
                )
            elif result.returncode == 1:
                return ExecResult(
                    returncode=0,
                    stdout=result.stdout,
                    stderr="",
                )
            else:
                return ExecResult(
                    returncode=result.returncode,
                    stdout="",
                    stderr=f"Diff failed: {result.stderr}",
                )

    def promote(self, force: bool = False) -> ExecResult:
        """Copy changes from shadow workspace back to host.

        This is a one-way operation that overwrites the host workspace
        with the contents of the shadow workspace.

        Args:
            force: If True, skip confirmation prompt

        Returns:
            ExecResult with success/failure info
        """
        container_name = f"{self.shadow_name}-workspace"

        # Verify container is running
        if not self.is_running():
            return ExecResult(
                returncode=1,
                stdout="",
                stderr="Shadow environment is not running.",
            )

        # Copy from container to host workspace
        # First, clear the destination (except .git)
        for item in self.workspace_path.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                import shutil

                shutil.rmtree(item)
            else:
                item.unlink()

        # Copy from container
        result = subprocess.run(
            ["docker", "cp", f"{container_name}:/workspace/.", str(self.workspace_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ExecResult(
                returncode=1,
                stdout="",
                stderr=f"Failed to copy workspace from container: {result.stderr}",
            )

        # Clean up snapshot
        if self.snapshot_dir.exists():
            import shutil

            shutil.rmtree(self.snapshot_dir)

        return ExecResult(
            returncode=0,
            stdout=f"Promoted shadow changes to {self.workspace_path}",
            stderr="",
        )
