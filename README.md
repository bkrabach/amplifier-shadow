# amplifier-shadow

Shadow environment management for Amplifier development.

Shadow environments are **isolated, ephemeral development environments** that enable:
- **Safe experimentation**: Changes inside the shadow do NOT affect your host filesystem
- **Autonomous AI operation**: AI tools can run fully autonomously without risk
- **Remote-install testing**: Validate git URL installation paths before pushing to GitHub

## Quick Start

```bash
# Install the CLI
cd amplifier-shadow
uv pip install -e .

# Start a shadow environment (copies workspace IN)
amplifier-shadow start --workspace /path/to/your/workspace

# Initialize Gitea (creates admin user and 'amplifier' org)
amplifier-shadow init

# Enter the workspace (isolated from host)
amplifier-shadow shell

# See what changed inside the shadow
amplifier-shadow diff

# Copy changes back to host (when ready)
amplifier-shadow promote

# Stop when done
amplifier-shadow stop
```

## What is a Shadow Environment?

A shadow environment is an **isolated** Docker Compose stack containing:

1. **Workspace Container**: Full development environment with Python, uv, and Docker CLI
2. **Gitea Sidecar**: Local git server simulating GitHub for testing remote installs

**Key Feature: Isolation**

Your workspace is **copied INTO** the container, not mounted. Changes inside the shadow do NOT affect your host filesystem. This enables:
- Safe experimentation without risk
- AI tools running fully autonomously
- "What if" scenarios without consequences

```
┌────────────────────────────────────────────────────────────────┐
│  HOST FILESYSTEM                                               │
│  /path/to/workspace  ─────────┐                                │
│                               │ docker cp (on start)           │
│                               ▼                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Shadow Environment (ISOLATED)                           │  │
│  │  ┌─────────────────┐  ┌────────────────────────────────┐ │  │
│  │  │  gitea:latest   │  │  amplifier-workspace           │ │  │
│  │  │  Port 3000      │  │  - Python 3.11+                │ │  │
│  │  │  Local git host │  │  - uv, Docker CLI              │ │  │
│  │  │                 │  │  - Isolated workspace volume   │ │  │
│  │  │  Repos:         │  │  - Changes stay HERE           │ │  │
│  │  │  - amplifier-*  │  │                                │ │  │
│  │  └─────────────────┘  └────────────────────────────────┘ │  │
│  │         ▲                        │                       │  │
│  │         └────── git clone ───────┘                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                               │                                │
│                               │ amplifier-shadow promote       │
│                               ▼ (when ready)                   │
│  /path/to/workspace  ◄────────┘                                │
└────────────────────────────────────────────────────────────────┘
```

## Why Shadow Environments?

### Use Case 1: Safe Autonomous AI Operation

**The Problem**: AI tools (like Amplifier with recipes) need to run autonomously, but you don't want them modifying your actual filesystem.

**The Solution**: Shadow environments provide true isolation. AI tools can:
- Write files, modify code, run experiments
- Make mistakes without consequences
- Run "until done or stuck" without supervision

When the AI is done, you review the changes with `amplifier-shadow diff` and selectively promote good changes with `amplifier-shadow promote`.

### Use Case 2: Test Remote Install Paths

**The Problem**: Things regularly break when installing from GitHub that work locally:

```
Local dev today:     filesystem path → works
Production:          git+https://github.com/... → breaks
Shadow env:          git+http://gitea:3000/... → tests real path
```

**The Solution**: Shadow environments test the *exact* loading mechanism used in production by providing a local git server that simulates GitHub.

## Installation

```bash
cd amplifier-shadow
uv pip install -e .
```

## CLI Commands

### Environment Lifecycle

```bash
# Start shadow environment (copies workspace IN)
amplifier-shadow start [name] [--workspace PATH] [--port PORT]

# Initialize Gitea with admin user and organization
amplifier-shadow init [name] [--admin-user USER] [--admin-password PASS] [--org ORG]

# Stop shadow environment
amplifier-shadow stop [name] [--volumes]

# Check status
amplifier-shadow status [name]

# List all shadow environments
amplifier-shadow list

# Show platform information
amplifier-shadow platform

# List shadow volumes (including orphaned)
amplifier-shadow volumes

# Remove orphaned volumes and snapshots
amplifier-shadow cleanup [--all] [--force]
```

### Workspace Interaction

```bash
# Open interactive shell in workspace
amplifier-shadow shell [name]

# Execute command in workspace
amplifier-shadow exec [name] <command>

# View logs
amplifier-shadow logs [name] [--service workspace|gitea] [--tail N]
```

### Change Management

```bash
# See what changed inside the shadow
amplifier-shadow diff [name]

# Copy changes back to host (with confirmation)
amplifier-shadow promote [name]

# Copy changes back without confirmation
amplifier-shadow promote [name] --force
```

### Module Publishing

```bash
# Publish a single module to shadow's Gitea
amplifier-shadow publish <module-path> [--shadow NAME]

# Sync all amplifier-* modules in a directory
amplifier-shadow sync [--shadow NAME] [--workspace PATH]
```

## Python API (ShadowGateway)

```python
from amplifier_shadow import ShadowGateway
from pathlib import Path

# Create gateway
gateway = ShadowGateway(
    shadow_name="my-experiment",
    workspace_path=Path("/path/to/workspace"),
    gitea_port=3000,
)

# Start environment (automatically copies workspace in)
gateway.start()

# Wait for Gitea and initialize
gateway.wait_for_gitea()
gateway.init_gitea()

# Execute commands (in isolated container)
result = gateway.exec("amplifier run 'hello world'")
print(result.stdout)

# Publish modules
gateway.publish_module(Path("./amplifier-module-foo"))

# See what changed
diff_result = gateway.diff()
print(diff_result.stdout)

# Promote changes back to host (when ready)
gateway.promote()

# Stop when done
gateway.stop()
```

## Publishing Modules to Shadow

After initializing Gitea:

```bash
# Publish a module
amplifier-shadow publish ./amplifier-module-foo

# Or sync all amplifier-* modules
amplifier-shadow sync --workspace /path/to/your-workspace
```

Then install from shadow inside the workspace:

```bash
# Enter workspace
amplifier-shadow shell

# Install from shadow's Gitea
uv pip install "git+http://gitea:3000/amplifier/amplifier-module-foo.git@main"
```

## Parallel Development (Multiple Shadows)

You can run multiple shadow environments simultaneously for parallel development work. Each shadow is completely isolated with its own:

- Docker containers (`{name}-workspace`, `{name}-gitea`)
- Docker network (`{name}-net`)
- Gitea data volume (`{name}-gitea-data`)
- API token file (`.shadow-token-{name}`)
- Gitea port (configurable)

### Example: Two Parallel Feature Branches

```bash
# Feature A: Testing new provider on port 3001
amplifier-shadow start feature-a --port 3001
amplifier-shadow init feature-a

# Feature B: Testing new tool on port 3002
amplifier-shadow start feature-b --port 3002
amplifier-shadow init feature-b

# Publish different modules to each
amplifier-shadow publish ./amplifier-module-provider-new --shadow feature-a
amplifier-shadow publish ./amplifier-module-tool-new --shadow feature-b

# Work in feature-a shadow
amplifier-shadow shell feature-a
# ... test provider changes ...

# Work in feature-b shadow (different terminal)
amplifier-shadow shell feature-b
# ... test tool changes ...

# Stop each when done (--volumes to clean up completely)
amplifier-shadow stop feature-a --volumes
amplifier-shadow stop feature-b --volumes
```

### Key Points for Parallel Development

1. **Use unique names**: Each shadow needs a unique name
2. **Use unique ports**: Each Gitea needs its own port
3. **Token files are per-shadow**: `.shadow-token-{name}` keeps credentials separate
4. **Clean up with `--volumes`**: Removes data volumes AND token files

## Environment Variables

Inside the shadow workspace:

| Variable | Value | Purpose |
|----------|-------|---------|
| `AMPLIFIER_GIT_HOST` | `http://gitea:3000` | Override git URLs to use local Gitea |
| `AMPLIFIER_SHADOW_MODE` | `true` | Indicates running in shadow environment |
| `SHADOW_NAME` | Environment name | Identifies which shadow this is |

## Platform Support

| Platform | Support | Notes |
|----------|---------|-------|
| **WSL2/Linux** | Primary | Native Docker, best performance |
| **macOS** | Strong | Docker Desktop / OrbStack |
| **Windows** | Functional | Docker Desktop (recommend WSL2) |
| **GitHub Codespaces** | Strong | Requires Docker-in-Docker feature |

## File Structure

```
amplifier-shadow/
├── pyproject.toml              # Package metadata
├── src/
│   └── amplifier_shadow/
│       ├── __init__.py
│       ├── cli.py              # Click CLI
│       ├── gateway.py          # ShadowGateway class
│       └── platform.py         # Platform detection
├── templates/
│   ├── docker-compose.yaml     # Shadow stack definition
│   └── Dockerfile.workspace    # Workspace container
└── README.md
```

## Integration with Recipes

Shadow environments are designed to be driven by Amplifier recipes for safe autonomous AI operation:

```python
from amplifier_shadow import ShadowGateway
from pathlib import Path

async def autonomous_code_improvement():
    """Recipe that lets AI improve code in complete isolation."""
    gateway = ShadowGateway(
        shadow_name="code-improvement",
        workspace_path=Path("./my-project"),
    )

    try:
        # Start isolated environment (workspace copied IN)
        gateway.start()
        gateway.wait_for_gitea()
        gateway.init_gitea()

        # Sync modules to shadow's Gitea
        gateway.publish_module(Path("./amplifier-core"))

        # Let AI run autonomously in isolation
        # It can modify files, run experiments, make mistakes
        # WITHOUT affecting your actual project
        result = gateway.exec(
            "amplifier run 'Refactor the authentication module for better testability'"
        )

        # Check what the AI changed
        diff_result = gateway.diff()
        print("AI made these changes:")
        print(diff_result.stdout)

        # Human reviews and decides to promote (or not)
        if approve_changes(diff_result):
            gateway.promote()
            print("Changes promoted to host workspace!")
        else:
            print("Changes discarded.")

    finally:
        gateway.stop()
```

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) in the parent repository.

This project uses CLA-based contribution. See Microsoft's [Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).

## Trademarks

This project may contain trademarks or logos for projects, products, or services. See Microsoft's [Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
