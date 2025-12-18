"""Amplifier Shadow CLI.

Simple command-line interface for managing shadow environments.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from amplifier_shadow.gateway import ShadowGateway
from amplifier_shadow.platform import print_platform_status


@click.group()
@click.version_option()
def main() -> None:
    """Amplifier Shadow Environment Manager.

    Create and manage isolated development environments for testing
    Amplifier's remote-install experience.
    """


@main.command()
@click.argument("name", default="default")
@click.option(
    "--workspace",
    "-w",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    help="Directory to mount as /workspace",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=3000,
    help="Port for Gitea web UI",
)
def start(name: str, workspace: Path, port: int) -> None:
    """Start a shadow environment.

    NAME is the unique identifier for this shadow (default: default)
    """
    gateway = ShadowGateway(
        shadow_name=name,
        workspace_path=workspace.absolute(),
        gitea_port=port,
    )

    click.echo(f"Starting shadow environment: {name}")
    click.echo(f"  Workspace: {workspace.absolute()}")
    click.echo(f"  Gitea port: {port}")
    click.echo()

    result = gateway.start()
    if result.success:
        click.echo("Shadow environment started!")
        click.echo()
        click.echo(f"  Gitea UI: {gateway.gitea_url}")
        click.echo(f"  Enter workspace: amplifier-shadow exec {name} bash")
    else:
        click.echo(f"Failed to start: {result.stderr}", err=True)
        sys.exit(1)


@main.command()
@click.argument("name", default="default")
@click.option(
    "--volumes",
    "-v",
    is_flag=True,
    help="Also remove data volumes",
)
def stop(name: str, volumes: bool) -> None:
    """Stop a shadow environment."""
    gateway = ShadowGateway(shadow_name=name)

    click.echo(f"Stopping shadow environment: {name}")
    result = gateway.stop(remove_volumes=volumes)

    if result.success:
        click.echo("Shadow environment stopped.")
        if not volumes:
            click.echo("Data preserved. Use --volumes to remove all data.")
    else:
        click.echo(f"Failed to stop: {result.stderr}", err=True)
        sys.exit(1)


@main.command()
@click.argument("name", default="default")
def status(name: str) -> None:
    """Check if shadow environment is running."""
    gateway = ShadowGateway(shadow_name=name)

    if gateway.is_running():
        click.echo(f"Shadow '{name}' is running")
        click.echo(f"  Gitea: {gateway.gitea_url}")
    else:
        click.echo(f"Shadow '{name}' is not running")


@main.command("exec")
@click.argument("name", default="default")
@click.argument("command", nargs=-1, required=True)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=300,
    help="Command timeout in seconds",
)
def exec_cmd(name: str, command: tuple[str, ...], timeout: int) -> None:
    """Execute command in shadow workspace.

    NAME is the shadow environment name.
    COMMAND is the command to execute (quote if contains spaces).
    """
    gateway = ShadowGateway(shadow_name=name)

    if not gateway.is_running():
        click.echo(f"Shadow '{name}' is not running. Start it first.", err=True)
        sys.exit(1)

    cmd_str = " ".join(command)
    result = gateway.exec(cmd_str, timeout=timeout)

    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)

    sys.exit(result.returncode)


@main.command()
@click.argument("name", default="default")
@click.option(
    "--tail",
    "-n",
    type=int,
    default=100,
    help="Number of log lines",
)
@click.option(
    "--service",
    "-s",
    type=click.Choice(["workspace", "gitea"]),
    default="workspace",
    help="Service to get logs from",
)
def logs(name: str, tail: int, service: str) -> None:
    """View logs from shadow environment."""
    gateway = ShadowGateway(shadow_name=name)
    output = gateway.get_logs(service=service, tail=tail)
    click.echo(output)


@main.command("list")
def list_shadows() -> None:
    """List all shadow environments."""
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=-workspace", "--format", "{{.Names}}\t{{.Status}}"],
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        click.echo("No shadow environments found.")
        return

    click.echo("Shadow Environments:")
    click.echo("-" * 50)
    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 2:
            name = parts[0].replace("-workspace", "")
            status = parts[1]
            running = "running" in status.lower()
            icon = "●" if running else "○"
            click.echo(f"  {icon} {name}: {status}")


def _get_shadow_volumes() -> list[dict]:
    """Get all Docker volumes associated with shadow environments.

    Returns list of dicts with keys: name, shadow_name, size, orphaned
    """
    # Get all volumes with amplifier-shadow prefix
    result = subprocess.run(
        ["docker", "volume", "ls", "--format", "{{.Name}}"],
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        return []

    volumes = []
    known_shadows = _get_known_shadows()

    for vol_name in result.stdout.strip().split("\n"):
        if not vol_name.startswith("amplifier-shadow-"):
            continue

        # Extract shadow name from volume name
        # Format: amplifier-shadow-{name}_{type} (e.g., amplifier-shadow-default_workspace)
        parts = vol_name.replace("amplifier-shadow-", "").rsplit("_", 1)
        shadow_name = parts[0] if parts else "unknown"

        # Get volume size
        inspect_result = subprocess.run(
            ["docker", "system", "df", "-v", "--format", "{{.Name}}\t{{.Size}}"],
            capture_output=True,
            text=True,
        )

        size = "unknown"
        for line in inspect_result.stdout.strip().split("\n"):
            if vol_name in line:
                size_parts = line.split("\t")
                if len(size_parts) >= 2:
                    size = size_parts[1]
                break

        volumes.append(
            {
                "name": vol_name,
                "shadow_name": shadow_name,
                "size": size,
                "orphaned": shadow_name not in known_shadows,
            }
        )

    return volumes


def _get_known_shadows() -> set[str]:
    """Get set of shadow names that have saved configs."""
    config_dir = Path.home() / ".amplifier" / "shadow" / "config"
    if not config_dir.exists():
        return set()

    shadows = set()
    for config_file in config_dir.glob("*.json"):
        shadows.add(config_file.stem)
    return shadows


def _get_orphaned_snapshots() -> list[Path]:
    """Get snapshot directories that don't have corresponding configs."""
    snapshot_dir = Path.home() / ".amplifier" / "shadow" / "snapshots"
    if not snapshot_dir.exists():
        return []

    known_shadows = _get_known_shadows()
    orphaned = []

    for snapshot in snapshot_dir.iterdir():
        if snapshot.is_dir() and snapshot.name not in known_shadows:
            orphaned.append(snapshot)

    return orphaned


@main.command()
def volumes() -> None:
    """List Docker volumes associated with shadow environments.

    Shows all volumes, their associated shadow environment, size,
    and whether they are orphaned (no corresponding shadow config).
    """
    vols = _get_shadow_volumes()

    if not vols:
        click.echo("No shadow volumes found.")
        return

    click.echo("Shadow Volumes:")
    click.echo("-" * 60)

    orphaned_count = 0
    for vol in vols:
        status = "orphaned" if vol["orphaned"] else "active"
        if vol["orphaned"]:
            orphaned_count += 1
        icon = "⚠" if vol["orphaned"] else "●"
        click.echo(f"  {icon} {vol['name']}")
        click.echo(f"      Shadow: {vol['shadow_name']} ({status})")
        click.echo(f"      Size: {vol['size']}")

    # Also show orphaned snapshots
    orphaned_snapshots = _get_orphaned_snapshots()

    click.echo()
    click.echo("Summary:")
    click.echo(f"  Total volumes: {len(vols)}")
    click.echo(f"  Orphaned volumes: {orphaned_count}")
    click.echo(f"  Orphaned snapshots: {len(orphaned_snapshots)}")

    if orphaned_count > 0 or orphaned_snapshots:
        click.echo()
        click.echo("Run 'amplifier-shadow cleanup' to remove orphaned data.")


@main.command()
@click.option(
    "--all",
    "remove_all",
    is_flag=True,
    help="Remove ALL shadow volumes (not just orphaned)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt",
)
def cleanup(remove_all: bool, force: bool) -> None:
    """Remove orphaned shadow volumes and snapshots.

    By default, only removes volumes/snapshots that don't have a
    corresponding shadow configuration. Use --all to remove everything.
    """
    import shutil

    vols = _get_shadow_volumes()
    orphaned_snapshots = _get_orphaned_snapshots()

    # Filter volumes based on --all flag
    if remove_all:
        volumes_to_remove = [v["name"] for v in vols]
    else:
        volumes_to_remove = [v["name"] for v in vols if v["orphaned"]]

    snapshots_to_remove = orphaned_snapshots if not remove_all else []
    if remove_all:
        snapshot_dir = Path.home() / ".amplifier" / "shadow" / "snapshots"
        if snapshot_dir.exists():
            snapshots_to_remove = list(snapshot_dir.iterdir())

    if not volumes_to_remove and not snapshots_to_remove:
        click.echo("Nothing to clean up.")
        return

    # Show what will be removed
    click.echo("The following will be removed:")
    if volumes_to_remove:
        click.echo(f"\n  Volumes ({len(volumes_to_remove)}):")
        for vol in volumes_to_remove:
            click.echo(f"    - {vol}")

    if snapshots_to_remove:
        click.echo(f"\n  Snapshots ({len(snapshots_to_remove)}):")
        for snap in snapshots_to_remove:
            click.echo(f"    - {snap.name}")

    click.echo()

    if not force:
        if not click.confirm("Proceed with cleanup?"):
            click.echo("Aborted.")
            return

    # Remove volumes
    removed_volumes = 0
    for vol in volumes_to_remove:
        result = subprocess.run(
            ["docker", "volume", "rm", vol],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            removed_volumes += 1
            click.echo(f"  Removed volume: {vol}")
        else:
            click.echo(f"  Failed to remove {vol}: {result.stderr.strip()}", err=True)

    # Remove snapshots
    removed_snapshots = 0
    for snap in snapshots_to_remove:
        try:
            shutil.rmtree(snap)
            removed_snapshots += 1
            click.echo(f"  Removed snapshot: {snap.name}")
        except Exception as e:
            click.echo(f"  Failed to remove {snap.name}: {e}", err=True)

    click.echo()
    click.echo(f"Cleanup complete: {removed_volumes} volumes, {removed_snapshots} snapshots removed.")


@main.command()
@click.argument("name", default="default")
def shell(name: str) -> None:
    """Open interactive shell in shadow workspace.

    NAME is the shadow environment name.
    """
    gateway = ShadowGateway(shadow_name=name)

    if not gateway.is_running():
        click.echo(f"Shadow '{name}' is not running. Start it first.", err=True)
        sys.exit(1)

    click.echo(f"Opening shell in shadow '{name}'...")
    click.echo("Type 'exit' to return.\n")

    # Use os.execvp to replace current process with interactive shell
    env = {**os.environ, **gateway._get_env()}
    os.execvpe(
        "docker",
        [
            "docker",
            "compose",
            "-f",
            str(gateway.compose_file),
            "exec",
            "workspace",
            "bash",
        ],
        env,
    )


@main.command()
@click.argument("module_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--shadow", "-s", default="default", help="Shadow environment name")
def publish(module_path: Path, shadow: str) -> None:
    """Publish a module to shadow's Gitea.

    MODULE_PATH is the path to the module directory (must be a git repo).
    """
    gateway = ShadowGateway(shadow_name=shadow)

    if not gateway.is_running():
        click.echo(f"Shadow '{shadow}' is not running. Start it first.", err=True)
        sys.exit(1)

    click.echo(f"Publishing {module_path.name} to shadow '{shadow}'...")

    result = gateway.publish_module(module_path)
    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)

    sys.exit(result.returncode)


@main.command()
@click.option("--shadow", "-s", default="default", help="Shadow environment name")
@click.option(
    "--workspace",
    "-w",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    help="Workspace directory containing modules",
)
def sync(shadow: str, workspace: Path) -> None:
    """Sync all amplifier-* modules to shadow's Gitea.

    Finds all amplifier-* directories in the workspace and publishes them.
    """
    gateway = ShadowGateway(shadow_name=shadow)

    if not gateway.is_running():
        click.echo(f"Shadow '{shadow}' is not running. Start it first.", err=True)
        sys.exit(1)

    # Find all amplifier-* directories that are git repos
    workspace = workspace.absolute()
    modules = []
    for item in workspace.iterdir():
        if item.is_dir() and item.name.startswith("amplifier"):
            # Check if it's a git repo (handles both regular repos and submodules)
            if (item / ".git").exists():
                modules.append(item)

    if not modules:
        click.echo(f"No amplifier-* modules found in {workspace}")
        sys.exit(1)

    click.echo(f"Found {len(modules)} modules to sync:")
    for mod in modules:
        click.echo(f"  - {mod.name}")
    click.echo()

    failed = []
    for mod in modules:
        click.echo(f"Syncing {mod.name}...")
        result = gateway.publish_module(mod)
        if result.returncode != 0:
            click.echo(f"  Failed: {result.stderr}", err=True)
            failed.append(mod.name)
        else:
            click.echo("  Done!")

    click.echo()
    if failed:
        click.echo(f"Failed to sync: {', '.join(failed)}", err=True)
        sys.exit(1)
    else:
        click.echo(f"Successfully synced {len(modules)} modules.")


@main.command()
def platform() -> None:
    """Show platform information and readiness."""
    info = print_platform_status()
    sys.exit(0 if info.ready else 1)


@main.command()
@click.argument("name", default="default")
def diff(name: str) -> None:
    """Show changes made in shadow workspace vs original.

    NAME is the shadow environment name.

    Compares the current state of the shadow workspace against the
    snapshot taken when the shadow was started.
    """
    gateway = ShadowGateway.from_saved_config(shadow_name=name)

    if not gateway.is_running():
        click.echo(f"Shadow '{name}' is not running.", err=True)
        sys.exit(1)

    result = gateway.diff()
    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)
        sys.exit(1)


@main.command()
@click.argument("name", default="default")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt",
)
def promote(name: str, force: bool) -> None:
    """Copy changes from shadow workspace back to host.

    NAME is the shadow environment name.

    This overwrites your host workspace with the contents of the
    shadow workspace. Use 'amplifier-shadow diff' first to see what changed.
    """
    gateway = ShadowGateway.from_saved_config(shadow_name=name)

    if not gateway.is_running():
        click.echo(f"Shadow '{name}' is not running.", err=True)
        sys.exit(1)

    # Show diff first
    diff_result = gateway.diff()
    if diff_result.stdout and diff_result.stdout != "No changes detected.":
        click.echo("Changes to promote:")
        click.echo(diff_result.stdout)
        click.echo()

        if not force:
            if not click.confirm("Promote these changes to host workspace?"):
                click.echo("Aborted.")
                sys.exit(0)
    else:
        click.echo("No changes detected.")
        sys.exit(0)

    result = gateway.promote()
    if result.success:
        click.echo(result.stdout)
    else:
        click.echo(f"Promote failed: {result.stderr}", err=True)
        sys.exit(1)


@main.command("init")
@click.argument("name", default="default")
@click.option(
    "--admin-user",
    default="shadow-admin",
    help="Gitea admin username",
)
@click.option(
    "--admin-password",
    default="shadow-admin",
    help="Gitea admin password",
)
@click.option(
    "--org",
    default="amplifier",
    help="Organization name to create",
)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=120,
    help="Timeout waiting for Gitea to be ready",
)
def init_shadow(name: str, admin_user: str, admin_password: str, org: str, timeout: int) -> None:
    """Initialize shadow environment with Gitea admin user and organization.

    NAME is the shadow environment name.

    This command waits for Gitea to be ready, creates an admin user,
    generates an API token, and creates the specified organization.
    """
    gateway = ShadowGateway(shadow_name=name)

    if not gateway.is_running():
        click.echo(f"Shadow '{name}' is not running. Start it first.", err=True)
        sys.exit(1)

    click.echo(f"Initializing shadow '{name}'...")
    click.echo("Waiting for Gitea to be ready...")

    if not gateway.wait_for_gitea(timeout=timeout):
        click.echo(f"Gitea did not become ready within {timeout}s", err=True)
        sys.exit(1)

    click.echo("Gitea is ready. Creating admin user and organization...")

    result = gateway.init_gitea(
        admin_user=admin_user,
        admin_password=admin_password,
        org_name=org,
    )

    if result.success:
        click.echo(result.stdout)
        click.echo()
        click.echo(f"Shadow '{name}' initialized successfully!")
        click.echo(f"  Gitea UI: {gateway.gitea_url}")
        click.echo(f"  Organization: {gateway.gitea_url}/{org}")
    else:
        click.echo(f"Initialization failed: {result.stderr}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
