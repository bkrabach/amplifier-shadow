# Shadow Environment Architecture for Amplifier Development

**Status**: Phase 0 Complete
**Created**: 2024-12-01
**Updated**: 2024-12-02
**Author**: Amplifier (with Brian Krabach)

---

## Executive Summary

This document outlines the architecture for **Shadow Environments** - isolated, ephemeral development environments that enable safe experimentation, automated testing, and validation of the full Amplifier "remote install" experience without pushing to GitHub.

Shadow environments are the foundational unlock for:

- **Safe autonomous AI operation**: AI tools run in complete isolation without affecting the host filesystem
- Recipe-driven automated development workflows
- Parallel experimentation with easy discard/promote
- End-user scenario simulation within safe sandboxes
- Model-agnostic development (testing with gpt-oss-20b, etc.)
- Working at higher abstraction levels ("delegate to Amplifier")

---

## Vision & Goals

### The Dream State

> "Personally no longer using Amplifier v1, instead doing all Amplifier 'next' dev through a system that works at the task-level - directing requests/feedback at the chat level, not lower."

### Core Requirements

1. **Isolation**: True sandbox - changes inside do NOT affect host filesystem
2. **Fidelity**: Tests the _actual_ remote-install path (not just local filesystem)
3. **Ephemerality**: Easy to create, discard, run many in parallel
4. **Reviewability**: See what changed (`diff`), selectively promote good changes
5. **Automation Surface**: Recipes/tools can drive scenarios within
6. **Cross-Platform**: Works on WSL2/Linux (primary), macOS (strong), Windows/Codespaces (functional)

### What "Fidelity" Means

The key insight: things regularly break when installing from GitHub that work locally. Shadow environments must test the _exact_ loading mechanism used in production:

```
Local dev today:     filesystem path → works
Production:          git+https://github.com/... → breaks
Shadow env:          git+http://local-gitea/... → tests real path
```

---

## High-Level Roadmap (Light)

```
Phase 0: Foundation
├── Shadow environment infrastructure
├── Local git server integration (Gitea sidecar)
├── URL rewriting (AMPLIFIER_GIT_HOST)
├── Profile/Collection testing from shadow
└── CI Integration (GitHub Actions)

Phase 1: Automation Integration
├── CLI wrapper (amplifier-shadow)
├── Recipes can target shadow environments
├── User scenario simulation framework
└── Evaluation/metrics collection

Phase 2: Parallel Experimentation
├── Multi-shadow orchestration
├── A/B testing approaches
└── Automated comparison decisions

Phase 3: Higher-Level Abstraction
├── Task-level interface (chat only at high level)
├── Self-improving development loops
└── Model flexibility (gpt-oss-20b forcing function)

Phase 4: Promotion & Distribution (AFTER approach proven)
├── New repository setup
├── Promotion workflow (shadow → GitHub/PRs)
├── Automated promote/discard decisions
└── Production deployment patterns
```

**Current focus**: Phase 0 - foundational infrastructure.

**Key decision**: Promotion workflow deferred to Phase 4 (after Phase 3 validates the approach). We don't set up distribution infrastructure until we know the shadow environment pattern is a "winner."

---

## Technical Architecture

### Approach: Devcontainer + Compose + Gitea

**Core Pattern**: Each shadow environment is a Docker Compose stack containing:

1. **Workspace container**: Full Amplifier development environment with isolated volume
2. **Gitea sidecar**: Local git server simulating GitHub
3. **Shared network**: Containers can communicate

**Key Design: Isolation via Copy-In/Copy-Out**

The workspace is **copied INTO** the container (not mounted). Changes inside the shadow do NOT affect the host filesystem. This enables safe autonomous AI operation.

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

### Why This Approach

| Criterion               | Score | Rationale                                 |
| ----------------------- | ----- | ----------------------------------------- |
| Remote Install Fidelity | 4/5   | Real git server, tests actual clone/fetch |
| Isolation               | 5/5   | Full container isolation                  |
| Speed                   | 3/5   | Container startup + git push (~30s)       |
| Parallelism             | 4/5   | Compose scaling, different ports          |
| Simplicity              | 4/5   | Well-documented patterns                  |
| Ecosystem Fit           | 5/5   | Matches Codespaces mental model           |
| Cross-Platform          | 4/5   | Docker works everywhere                   |
| Promotability           | 4/5   | Standard git workflow                     |

**Total: 33/40** - Best balance of fidelity, simplicity, and cross-platform support.

### Directory Structure

```
amplifier-dev/
├── amplifier-shadow/                 # CLI tool (Phase 0.7 Complete)
│   ├── pyproject.toml
│   ├── README.md
│   ├── src/
│   │   └── amplifier_shadow/
│   │       ├── __init__.py
│   │       ├── cli.py                # Click-based CLI (canonical interface)
│   │       ├── gateway.py            # ShadowGateway class (Python API)
│   │       └── platform.py           # Platform detection
│   └── templates/
│       ├── docker-compose.yaml       # Compose stack definition
│       └── Dockerfile.workspace      # Workspace image
```

### Key Configuration Files

#### `templates/docker-compose.yaml`

```yaml
# Shadow Environment Docker Compose Stack
# Creates ISOLATED development environment with local git server (Gitea)
#
# ISOLATION: The workspace is copied INTO the container, not mounted.
# Changes inside the shadow do NOT affect the host filesystem.
# Use `amplifier-shadow promote` to copy changes back when ready.

services:
  gitea:
    image: gitea/gitea:latest
    container_name: ${SHADOW_NAME:-shadow}-gitea
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - GITEA__server__ROOT_URL=http://gitea:3000/
      - GITEA__server__HTTP_PORT=3000
      - GITEA__security__INSTALL_LOCK=true
    volumes:
      - gitea-data:/data
    ports:
      - "${GITEA_PORT:-3000}:3000"
    networks:
      - shadow-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5

  workspace:
    build:
      context: .
      dockerfile: Dockerfile.workspace
    container_name: ${SHADOW_NAME:-shadow}-workspace
    volumes:
      # Isolated workspace volume (NOT mounted to host)
      # Files are copied in via `docker cp` after container starts
      - workspace-data:/workspace
      # Docker socket for nested operations (build/push within shadow)
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - AMPLIFIER_GIT_HOST=http://gitea:3000
      - AMPLIFIER_SHADOW_MODE=true
      - SHADOW_NAME=${SHADOW_NAME:-default}
    depends_on:
      gitea:
        condition: service_healthy
    networks:
      - shadow-net
    working_dir: /workspace
    command: sleep infinity

networks:
  shadow-net:
    driver: bridge
    name: ${SHADOW_NAME:-shadow}-net

volumes:
  gitea-data:
    name: ${SHADOW_NAME:-shadow}-gitea-data
  workspace-data:
    name: ${SHADOW_NAME:-shadow}-workspace-data
```

#### `.shadow-env/Dockerfile.workspace`

```dockerfile
FROM mcr.microsoft.com/devcontainers/python:3.11

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Install Docker CLI (for nested operations)
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

# Set up workspace
WORKDIR /workspace

# Install Amplifier in editable mode (will happen at runtime via mount)
```

---

## Workflow: Using Shadow Environments

### Creating a Shadow Environment

```bash
# Start shadow environment (copies workspace IN - isolated from host)
amplifier-shadow start --workspace /path/to/amplifier-dev

# Initialize Gitea (creates admin user and 'amplifier' org)
amplifier-shadow init
```

**Key behavior**: The workspace is **copied INTO** the container, not mounted. Changes inside the shadow do NOT affect your host filesystem.

### Publishing Modules to Shadow's Gitea

```bash
# Publish a single module
amplifier-shadow publish ./amplifier-module-foo

# Or sync all amplifier-* modules
amplifier-shadow sync --workspace /path/to/amplifier-dev
```

**What publish does:**

1. Creates repo in Gitea if needed (via API)
2. Adds Gitea as remote
3. Pushes current branch to Gitea

### Testing Remote Install in Shadow

```bash
# Enter the isolated workspace
amplifier-shadow shell

# Inside the shadow, install from Gitea (tests real remote path!)
uv tool install "git+http://gitea:3000/amplifier/amplifier.git@main"

# Or install a module
uv pip install "git+http://gitea:3000/amplifier/amplifier-module-provider-anthropic.git@main"
```

### Running Tests/Recipes in Shadow

```bash
# Execute commands in shadow
amplifier-shadow exec default "cd /workspace && make test"

# Or run a recipe
amplifier-shadow exec default "amplifier recipe run user-onboarding-scenario"
```

### Reviewing and Promoting Changes

```bash
# See what changed inside the shadow vs original
amplifier-shadow diff

# Copy changes back to host (when ready)
amplifier-shadow promote

# Or without confirmation prompt
amplifier-shadow promote --force
```

**Change review workflow:**

1. Run experiments in isolated shadow
2. Use `diff` to see what the AI/tools modified
3. Review the diff to validate changes
4. Use `promote` to apply good changes to host
5. Or just `stop` to discard changes completely

---

## Recipe Integration Architecture

The real power of shadow environments comes from **recipe-driven automation**. This section details how recipes interact with shadow environments to enable automated testing, user simulation, and self-improving development loops.

### Two-Layer Recipe Pattern

Shadow environments use a **two-layer recipe architecture**:

1. **Outer Layer (Shadow Management Recipes)**: Run on the host, manage shadow lifecycle, delegate work inward
2. **Inner Layer (Scenario Recipes)**: Run inside the shadow, executed by the inner Amplifier, simulate user workflows

```
┌─────────────────────────────────────────────────────────────────────┐
│  HOST / ORCHESTRATION LAYER                                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Shadow Management Recipe                                      │  │
│  │  - Creates/destroys shadow envs                                │  │
│  │  - Syncs code to Gitea                                         │  │
│  │  - Installs Amplifier from "remote"                            │  │
│  │  - Delegates scenarios to inner Amplifier                      │  │
│  │  - Collects results, decides promote/discard                   │  │
│  └──────────────────────────┬────────────────────────────────────┘  │
│                             │                                        │
│                             │  ShadowGateway                         │
│                             │  (docker exec / volume mount)          │
│                             ▼                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  SHADOW ENVIRONMENT                                            │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  Inner Amplifier CLI (installed from Gitea)             │  │  │
│  │  │  - Full tool access (file, bash, web, search, task)     │  │  │
│  │  │  - Can run scenario recipes                             │  │  │
│  │  │  - IS the system under test                             │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  ┌─────────────┐  ┌─────────────────────────────────────────┐ │  │
│  │  │   Gitea     │  │  /workspace (ISOLATED volume)           │ │  │
│  │  │   (repos)   │  │  - amplifier-dev source (copied in)     │ │  │
│  │  │             │  │  - changes stay in shadow until promote │ │  │
│  │  └─────────────┘  └─────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### The ShadowGateway Interface

A thin abstraction that bridges recipe operations to shadow commands:

```python
class ShadowGateway:
    """Bridge between recipe executor and shadow environment."""

    def __init__(self, shadow_name: str, workspace_path: Path = None):
        self.shadow_name = shadow_name
        self.workspace_path = workspace_path  # Original host workspace
        self.compose_project = f"shadow-{shadow_name}"

    # === Command Execution ===

    def exec(self, command: str, timeout: int = 300) -> ExecResult:
        """Execute shell command inside shadow workspace."""
        return docker_exec(
            project=self.compose_project,
            service="workspace",
            command=command,
            timeout=timeout
        )

    def amplifier(self, prompt: str, profile: str = "dev") -> AmplifierResult:
        """Run Amplifier inside shadow with given prompt."""
        result = self.exec(
            f'amplifier run --profile {profile} --output-format json "{prompt}"'
        )
        return AmplifierResult.from_json(result.stdout)

    def run_recipe(self, recipe_path: str, context: dict = None) -> RecipeResult:
        """Run a recipe inside the shadow's Amplifier."""
        ctx_arg = f"--context '{json.dumps(context)}'" if context else ""
        result = self.exec(f"amplifier recipe run {recipe_path} {ctx_arg}")
        return RecipeResult.from_output(result)

    # === Isolation Operations ===

    def copy_workspace_in(self) -> ExecResult:
        """Copy host workspace into the isolated container.

        Called automatically by start(). Creates a snapshot for later diff.
        """
        # Save snapshot for diff/promote
        shutil.copytree(self.workspace_path, self.snapshot_dir)

        # Clear container /workspace and copy in
        self.exec("rm -rf /workspace/*")
        subprocess.run(["docker", "cp", f"{self.workspace_path}/.", f"{self.container_name}:/workspace/"])

    def diff(self) -> ExecResult:
        """Show changes made in shadow workspace vs original.

        Compares current container state against snapshot taken at start.
        """
        # Copy from container to temp, diff against snapshot
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["docker", "cp", f"{self.container_name}:/workspace/.", tmpdir])
            result = subprocess.run(
                ["diff", "-rq", str(self.snapshot_dir), tmpdir],
                capture_output=True, text=True
            )
            return ExecResult(stdout=result.stdout, returncode=result.returncode)

    def promote(self) -> ExecResult:
        """Copy changes from shadow workspace back to host.

        Overwrites host workspace with current shadow state.
        """
        # Clear host (except .git), copy from container
        for item in self.workspace_path.iterdir():
            if item.name != ".git":
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        subprocess.run(["docker", "cp", f"{self.container_name}:/workspace/.", str(self.workspace_path)])
        return ExecResult(success=True, stdout="Changes promoted to host workspace.")

    # === Git Operations ===

    def git(self, command: str, cwd: str = ".") -> ExecResult:
        """Run git command inside shadow."""
        return self.exec(f"cd {cwd} && git {command}")

    def publish_module(self, module_path: Path) -> ExecResult:
        """Push local module to shadow's Gitea."""
        # Creates repo via API, pushes via git
        ...

    # === Lifecycle ===

    def start(self) -> ExecResult:
        """Start the shadow environment.

        Automatically copies workspace into the isolated container.
        """
        result = subprocess.run(["docker", "compose", "up", "-d", ...])
        if result.returncode == 0:
            self.copy_workspace_in()  # Isolation: copy in, not mount
        return ExecResult(success=result.returncode == 0)

    def stop(self, remove_volumes: bool = False) -> ExecResult:
        """Stop the shadow environment."""
        ...

    def reinstall_amplifier(self):
        """Reinstall Amplifier from shadow's Gitea (test remote install)."""
        self.exec("uv tool uninstall amplifier || true")
        self.exec(
            'uv tool install "git+http://gitea:3000/amplifier/amplifier.git@main"'
        )
```

### File Operations Strategy

The **isolated volume** with copy-in/copy-out is the key enabler for safe autonomous operation:

```yaml
# In docker-compose.yaml
workspace:
  volumes:
    # Isolated workspace volume (NOT mounted to host)
    # Files are copied in via `docker cp` after container starts
    - workspace-data:/workspace
```

**This means:**

| Operation | Outer Recipe (Host) | Inner Amplifier (Shadow) |
|-----------|---------------------|--------------------------|
| Read file | `gateway.exec("cat ...")` | Normal file tool |
| Write file | `gateway.exec("echo ...")` | Normal file tool |
| Run command | `gateway.exec()` (docker exec) | Normal bash tool |
| See changes | `gateway.diff()` | N/A (works inside) |
| Apply changes | `gateway.promote()` | N/A (host operation) |

**Key insight**: Changes are **isolated until explicitly promoted**:
- Inner Amplifier can modify, delete, experiment freely
- Host workspace remains unchanged until `promote()`
- Use `diff()` to see what changed before promoting
- Safe to discard changes by just stopping the shadow

### Shadow Management Recipes (Outer Layer)

These recipes run on the host and orchestrate the full workflow:

```yaml
name: test-feature-branch
description: Test a feature branch in isolated shadow environment

context:
  branch_name: "feature/new-provider-api"

steps:
  - id: create-shadow
    action: shadow.create
    config:
      name: "test-{{branch_name}}-{{timestamp}}"
      from_branch: "{{branch_name}}"

  - id: sync-all-modules
    action: shadow.sync
    config:
      modules: all # Syncs all amplifier-* repos to Gitea

  - id: install-from-remote
    action: shadow.exec
    command: |
      uv tool install "git+http://gitea:3000/amplifier/amplifier.git@main"

  - id: verify-install
    action: shadow.exec
    command: amplifier --version

  - id: run-user-scenario
    action: shadow.run_recipe
    recipe: scenarios/new-user-onboarding.yaml
    # This runs INSIDE the shadow, driven by inner Amplifier

  - id: run-dev-scenario
    action: shadow.run_recipe
    recipe: scenarios/developer-workflow.yaml

  - id: run-error-scenarios
    action: shadow.run_recipe
    recipe: scenarios/error-handling.yaml

  - id: collect-results
    action: shadow.read_file
    path: /workspace/test-results/summary.json

  - id: evaluate
    prompt: |
      Evaluate these test results and determine if the feature is ready:
      {{collect-results.output}}

      Consider: functionality, user experience, error handling, performance.
    outputs:
      - verdict: pass | fail | needs-work
      - issues: list of problems found
      - recommendations: next steps

  - id: decide-promote
    condition: "{{evaluate.verdict}} == 'pass'"
    action: shadow.promote
    config:
      to_branch: "pr/{{branch_name}}"
      create_pr: true

  - id: decide-report-issues
    condition: "{{evaluate.verdict}} == 'needs-work'"
    action: report
    config:
      issues: "{{evaluate.issues}}"
      recommendations: "{{evaluate.recommendations}}"

  - id: cleanup
    action: shadow.destroy
    when: always # Run even if earlier steps fail
```

### Scenario Recipes (Inner Layer)

These recipes run **inside** the shadow, executed by the inner Amplifier. They simulate real user workflows:

```yaml
name: new-user-onboarding
description: Simulate a new user setting up Amplifier for the first time
persona: "Developer new to Amplifier, familiar with Python/CLI tools"

context:
  working_dir: /tmp/test-project

steps:
  - id: setup-project
    prompt: |
      Create a new project directory and initialize it:
      - mkdir -p {{working_dir}}
      - cd {{working_dir}}
      - Create a simple Python project structure with a few files
    tools: [bash, filesystem]

  - id: discover-amplifier
    prompt: |
      As a new user, explore what Amplifier can do:
      - Run amplifier --help
      - List available profiles with amplifier profile list
      - List available commands
      Document what you learn about the system.
    tools: [bash]
    outputs:
      - discovered_commands: list
      - discovered_profiles: list
      - clarity_score: 1-10 # How clear was the help?

  - id: first-interaction
    prompt: |
      Try your first Amplifier interaction:
      - Choose an appropriate profile for development
      - Run a simple prompt like "What can you help me with?"
      - Evaluate the response quality and timing
    tools: [bash]
    outputs:
      - response_quality: 1-10
      - response_time_acceptable: boolean
      - any_errors: list

  - id: attempt-real-task
    prompt: |
      Try to use Amplifier for a real development task:
      - Ask it to create a simple Python function in your project
      - Ask it to explain some existing code
      - Ask it to help write a test
      Evaluate how well it helps with each task.
    tools: [bash, filesystem]
    outputs:
      - task_completion: success | partial | failed
      - friction_points: list
      - helpful_features: list

  - id: test-error-recovery
    prompt: |
      Intentionally trigger some errors and see how Amplifier handles them:
      - Try an invalid command
      - Try to access a file that doesn't exist
      - Give an ambiguous instruction
      Evaluate error messages and recovery guidance.
    tools: [bash, filesystem]
    outputs:
      - error_clarity: 1-10
      - recovery_guidance: 1-10
      - frustration_level: 1-10

  - id: synthesize-experience
    prompt: |
      Based on this complete onboarding experience, provide a structured evaluation:

      1. Overall experience rating (1-10)
      2. Time to first value (how long until genuinely useful?)
      3. Confusion points (what was unclear or surprising?)
      4. Delight points (what exceeded expectations?)
      5. Critical issues (blockers or serious problems)
      6. Suggestions for improvement
      7. Would you recommend to a colleague? Why or why not?

      Write results to /workspace/test-results/onboarding-results.json
    tools: [filesystem]
    outputs:
      - overall_rating: number
      - time_to_value: string
      - confusion_points: list
      - delight_points: list
      - critical_issues: list
      - improvements: list
      - would_recommend: boolean
      - recommendation_reason: string
```

### Full Workflow Example

Here's how the complete flow works end-to-end:

```
1. TRIGGER: Developer pushes feature branch (or manual trigger)
   │
   ▼
2. OUTER RECIPE: Shadow management recipe starts on host
   │
   ├── Creates shadow environment (docker-compose up)
   ├── Syncs all modules to shadow's Gitea
   ├── Installs Amplifier from Gitea URLs (tests remote install!)
   │
   ▼
3. INNER RECIPES: Scenario recipes run inside shadow
   │
   │  ┌─────────────────────────────────────────────┐
   │  │ new-user-onboarding.yaml                    │
   │  │ ├── Inner Amplifier executes steps          │
   │  │ ├── Uses bash, file, web tools as needed    │
   │  │ ├── Simulates real user behavior            │
   │  │ └── Writes results to /workspace/results/   │
   │  └─────────────────────────────────────────────┘
   │
   │  ┌─────────────────────────────────────────────┐
   │  │ developer-workflow.yaml                     │
   │  │ ├── Tests code editing scenarios            │
   │  │ ├── Tests git operations                    │
   │  │ ├── Tests multi-file changes                │
   │  │ └── Writes results to /workspace/results/   │
   │  └─────────────────────────────────────────────┘
   │
   │  ┌─────────────────────────────────────────────┐
   │  │ error-handling.yaml                         │
   │  │ ├── Tests edge cases                        │
   │  │ ├── Tests error recovery                    │
   │  │ ├── Tests graceful degradation              │
   │  │ └── Writes results to /workspace/results/   │
   │  └─────────────────────────────────────────────┘
   │
   ▼
4. COLLECTION: Outer recipe reads result files (via volume mount)
   │
   ├── Reads /workspace/test-results/*.json
   ├── Aggregates across all scenarios
   │
   ▼
5. EVALUATION: LLM evaluates aggregated results
   │
   ├── Analyzes pass/fail across scenarios
   ├── Identifies patterns in issues
   ├── Determines overall verdict
   │
   ▼
6. DECISION: Based on verdict
   │
   ├── PASS → Promote changes to real GitHub, create PR
   ├── NEEDS-WORK → Report issues, optionally keep shadow for debugging
   └── FAIL → Report critical issues, destroy shadow
   │
   ▼
7. CLEANUP: Destroy shadow environment (unless kept for debugging)
```

### Key Insight: Amplifier Testing Amplifier

The elegant part of this architecture: **the inner Amplifier has all the tools it needs**.

- `bash` tool → Run any command
- `filesystem` tool → Read/write/edit any file
- `web` tool → Fetch documentation, APIs
- `search` tool → Find code patterns
- `task` tool → Delegate subtasks

Scenario recipes don't need special "shadow-aware" tools. They just use normal Amplifier capabilities inside an isolated environment. The shadow provides:

- **Isolation** from real systems
- **"Remote" install testing** via Gitea
- **Clean slate** for each test run
- **Parallel execution** capability
- **Safe experimentation** without consequences

### Recipe Actions Reference

Shadow management recipes use these actions:

| Action | Description | Example |
|--------|-------------|---------|
| `shadow.create` | Create new shadow environment | `name: "test-foo"` |
| `shadow.destroy` | Destroy shadow environment | `name: "test-foo"` |
| `shadow.sync` | Sync modules to Gitea | `modules: all` or `["core", "cli"]` |
| `shadow.exec` | Execute command in shadow | `command: "make test"` |
| `shadow.amplifier` | Run Amplifier prompt in shadow | `prompt: "help me"` |
| `shadow.run_recipe` | Run recipe inside shadow | `recipe: "scenario.yaml"` |
| `shadow.read_file` | Read file from shadow | `path: "/workspace/x.json"` |
| `shadow.write_file` | Write file to shadow | `path: "...", content: "..."` |
| `shadow.promote` | Push changes to real remote | `to_branch: "pr/feature"` |

---

## Platform Support

### Platform Matrix

| Platform                     | Support    | Backend                   | Notes                           |
| ---------------------------- | ---------- | ------------------------- | ------------------------------- |
| **WSL2/Linux**               | Primary    | Native Docker             | Best performance, full features |
| **macOS**                    | Strong     | Docker Desktop / OrbStack | Slight VM overhead, works great |
| **Windows (Docker Desktop)** | Functional | Hyper-V / WSL2 backend    | Recommend WSL2 instead          |
| **GitHub Codespaces**        | Strong     | Docker-in-Docker          | Requires DinD feature           |

### Platform-Specific Considerations

#### WSL2/Linux

- Native Docker, best performance
- Shadow envs should live in WSL filesystem (`~/`), not Windows mounts (`/mnt/c/`)
- Network namespaces available for advanced isolation (optional enhancement)

#### macOS

- Docker Desktop or OrbStack (faster)
- All containers run in lightweight Linux VM (transparent)
- Same docker-compose files work unchanged

#### Windows (without WSL2)

- Docker Desktop uses Hyper-V or WSL2 backend
- Works but slower than native Linux
- Strongly recommend WSL2 for serious development

#### GitHub Codespaces

- Already a container environment
- Requires `docker-in-docker` feature in devcontainer.json:
  ```json
  {
    "features": {
      "ghcr.io/devcontainers/features/docker-in-docker:2": {}
    }
  }
  ```
- Shadow env becomes container-in-container (some overhead)
- Great for contributors without local Docker setup

### CLI Platform Detection (Future)

```python
# amplifier_shadow/platform.py
def detect_platform() -> str:
    """Detect current platform and return optimal backend."""
    if is_wsl():
        return "wsl2"  # Native Docker
    elif is_linux():
        return "linux"  # Native Docker
    elif is_macos():
        return "macos"  # Docker Desktop / OrbStack
    elif is_codespaces():
        return "codespaces"  # DinD
    elif is_windows():
        return "windows"  # Docker Desktop, warn about WSL2
    else:
        return "unknown"
```

---

## Module Resolution Integration

### The Problem

Amplifier's module resolution currently uses git URLs like:

```
git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
```

In shadow environments, we need these to resolve to Gitea instead.

### Solution: Environment Variable Override

Modify `amplifier-module-resolution` to support a git host override:

```python
# amplifier_module_resolution/git_source.py

def resolve_git_url(source: str) -> str:
    """Resolve git URL, respecting AMPLIFIER_GIT_HOST override."""
    shadow_host = os.environ.get("AMPLIFIER_GIT_HOST")

    if shadow_host and "github.com/microsoft/amplifier" in source:
        # Rewrite GitHub URL to shadow host
        # git+https://github.com/microsoft/amplifier-core@main
        # → git+http://gitea:3000/amplifier/amplifier-core@main
        return rewrite_to_shadow(source, shadow_host)

    return source  # Use original URL
```

**Key principle**: This is opt-in via environment variable. Production behavior unchanged.

### Alternative: URL Scheme Registration

For even higher fidelity, register a custom URL scheme:

```
shadow+amplifier-core@main
→ resolves to http://gitea:3000/amplifier/amplifier-core@main
```

This avoids modifying existing URL parsing logic.

---

## Implementation Phases

### Phase 0.1: Basic Infrastructure ✅

**Goal**: Get docker-compose stack working with Gitea.

- [x] Create `.shadow-env/` directory structure
- [x] Write `docker-compose.yaml` with Gitea + workspace
- [x] Write `Dockerfile.workspace` with Python/uv/Docker
- [x] Create `init-shadow.sh` to start the stack
- [x] Test: Can start stack, Gitea UI accessible

**Verification**: `docker-compose up -d` works, Gitea at localhost:3000

### Phase 0.2: Git Synchronization ✅

**Goal**: Publish local repos to Gitea.

- [x] Create `publish-module.sh` script
- [x] Handle Gitea repo creation via API
- [x] Handle git remote add/push
- [x] Create `sync-all.sh` to sync all amplifier-\* repos
- [x] Test: Repos visible in Gitea UI after sync

**Verification**: Can browse code in Gitea web UI

### Phase 0.3: Remote Install Testing ✅

**Goal**: Install Amplifier from shadow's Gitea via URL rewriting.

- [x] Add `AMPLIFIER_GIT_HOST` support to `amplifier-module-resolution`
- [x] Implement URL rewriting in `GitSource` class
- [x] Test `uv pip install` from rewritten Gitea URLs
- [x] Test module loading from Gitea URLs
- [x] Document URL format differences

**Verification**: Module resolution rewrites GitHub URLs to shadow Gitea

### Phase 0.4: Profile Loading Tests ✅

**Goal**: Verify profiles can install modules from shadow.

- [x] Create `amplifier-shadow/tests/test_profile_loading.py`
- [x] Test profile parsing with git sources
- [x] Test ModuleConfig source field extraction
- [x] Test environment variable propagation
- [x] 4 tests passing

**Verification**: Profile system correctly handles git sources for shadow testing

### Phase 0.5: Collection Testing ✅

**Goal**: Verify collection installs work from shadow.

- [x] Create `amplifier-shadow/tests/test_collection_install.py`
- [x] Test `InstallSourceProtocol` interface
- [x] Test `GitSource.install_to()` method
- [x] Test collection installer git source handling
- [x] 4 tests passing

**Verification**: Collection installer uses GitSource correctly for shadow installs

### Phase 0.6: CI Integration ✅

**Goal**: GitHub Actions workflow for shadow testing.

- [x] Create `.github/workflows/shadow-tests.yml`
- [x] Create `amplifier-shadow/tests/run_shadow_tests.sh` unified test runner
- [x] Configure pytest for shadow test discovery
- [x] Test workflow triggers on shadow-related changes

**Verification**: CI runs shadow tests automatically on relevant PRs

### Phase 0.7: CLI Wrapper ✅

**Goal**: Clean interface for shadow operations with isolation.

- [x] Create `amplifier-shadow` package with Click CLI
- [x] Implement `start`, `stop`, `status`, `list` commands
- [x] Implement `init` command (Gitea admin user, token, org)
- [x] Implement `publish`, `sync` commands (pure Python, no shell scripts)
- [x] Implement `exec`, `shell`, `logs` commands
- [x] Add `platform` command for platform detection
- [x] Implement `ShadowGateway` Python API for recipe integration
- [x] Remove shell script dependencies (CLI is the canonical interface)
- [x] Implement isolated-by-default architecture (copy-in on start)
- [x] Implement `diff` command (show changes vs original snapshot)
- [x] Implement `promote` command (copy changes back to host)

**Verification**: Can manage shadow envs entirely via CLI, with full isolation

---

## Future Enhancements (Post-Phase 0)

### Phase 1: Recipe Integration

- Recipes can specify `target: shadow` to run in isolated environment
- Shadow env created automatically, destroyed after
- ShadowGateway interface for recipe operations

### Phase 1: User Scenario Simulation

- Define user personas and workflows as recipes
- Run simulated "new user onboarding" in shadow
- Collect metrics on success/failure/friction

### Phase 2: Multi-Shadow Orchestration

- Run multiple shadow envs in parallel
- A/B test different approaches
- Automated comparison and selection

### Phase 3: Model Flexibility Testing

- Test same scenarios with different models
- Validate that systems (not just model power) drive improvements
- gpt-oss-20b as forcing function for system improvements
- Task-level interface (chat only at high level)

### Phase 4: Distribution & GitHub Integration (Deferred)

**Prerequisite**: Phase 3 complete and approach validated as "winner"

**Note**: Local promote (shadow → host) is already implemented in Phase 0.7. Phase 4 focuses on GitHub integration and distribution infrastructure.

- [ ] Create new repository for shadow environment distribution
- [ ] Handle branch creation on real remote
- [ ] Optionally create PR via `gh` CLI
- [ ] Document production deployment patterns

**Why deferred**: We don't invest in distribution infrastructure until we're confident the shadow environment approach delivers value. Phase 3 (higher-level abstraction, task-level interface, model flexibility) validates the full vision before we commit to productionizing it.

**Verification**: End-to-end: change in shadow → tested → PR on real GitHub

---

## Open Questions

1. **Gitea Authentication**: Should shadow Gitea require auth? (Probably not for simplicity)

2. **Persistent vs Ephemeral**: Should Gitea data persist between shadow sessions? (Probably yes for iteration speed)

3. **Branch Strategy**: When publishing to Gitea, use `main` or current branch name?

4. **Nested Docker**: In Codespaces, do we need Docker-in-Docker or Docker-from-Docker? (DinD is more isolated)

5. **Resource Limits**: Should we set memory/CPU limits on shadow containers? (Probably yes for parallelism)

---

## Near-Term TODOs

### Volume/Data Cleanup Commands

Docker volumes persist after `amplifier-shadow stop` (without `--volumes`). Users may accumulate orphaned volumes from deleted/renamed shadow environments that no longer appear in `amplifier-shadow list` but still consume disk space.

**Needed commands**:

1. **`amplifier-shadow volumes`** (or `amplifier-shadow list --volumes`)
   - List all Docker volumes associated with shadow environments
   - Show which are associated with active/known shadows vs orphaned
   - Display disk space usage per volume

2. **`amplifier-shadow cleanup`** (or `amplifier-shadow prune`)
   - Remove orphaned volumes (not associated with any shadow in list)
   - Optionally remove all shadow volumes (`--all`)
   - Interactive confirmation by default, `--force` to skip
   - Report space reclaimed

**Implementation notes**:
- Query Docker for volumes matching `amplifier-shadow-*` pattern
- Cross-reference with saved configs in `~/.amplifier/shadow-config/`
- Also clean up orphaned snapshots in `~/.amplifier/shadow-snapshots/`

---

## Success Criteria

### Phase 0 Complete When:

1. **Shadow env starts**: `amplifier-shadow start` creates working environment ✅
2. **Gitea populated**: All amplifier-\* repos synced and browsable ✅
3. **URL rewriting works**: `AMPLIFIER_GIT_HOST` rewrites GitHub URLs to Gitea ✅
4. **Profile loading tested**: Profile system handles git sources correctly ✅
5. **Collection installs tested**: Collection installer uses GitSource correctly ✅
6. **CI integration**: Shadow tests run automatically in GitHub Actions ✅
7. **CLI wrapper**: Can manage shadow envs via CLI ✅
8. **Cross-platform**: Works on WSL2, macOS, and Codespaces ✅
9. **Isolation works**: Workspace copied in, host unaffected until promote ✅
10. **Diff works**: Can see what changed vs original snapshot ✅
11. **Local promote works**: Can copy changes back to host workspace ✅

### Phase 4 Complete When (Deferred):

12. **GitHub integration**: Changes promoted can be pushed to real GitHub via PR
13. **Distribution**: Shadow environment distributed via dedicated repository

**Note**: Criteria 12-13 intentionally deferred until Phase 3 validates the approach.

---

## Appendix: Alternative Approaches Considered

For reference, other approaches were evaluated:

| Approach                | Score  | Why Not Primary                     |
| ----------------------- | ------ | ----------------------------------- |
| Network Namespace + DNS | 29/40  | Linux-only, complex setup           |
| Git Bundle + HTTP       | 30/40  | Lower fidelity, no push capability  |
| Nix Flakes              | 27/40  | Different install mechanism than uv |
| Bare Git Repos          | ~28/40 | Less realistic than full Gitea      |

The Devcontainer + Compose + Gitea approach scored highest (33/40) with best balance of fidelity, simplicity, and cross-platform support.

---

## Next Steps

### Phase 0 Complete ✅

Phase 0 infrastructure is complete:
- CLI wrapper (`amplifier-shadow`) with all lifecycle commands
- `ShadowGateway` Python API for programmatic control
- Pure Python implementation (no shell script dependencies)
- Cross-platform support (WSL2, macOS, Codespaces)
- **Isolated-by-default architecture** (workspace copied in, not mounted)
- **Change management commands** (`diff`, `promote`) for safe review/apply

### Phase 1 (Next)

1. Recipes can target shadow environments via `ShadowGateway`
2. Create user scenario simulation framework
3. Build evaluation/metrics collection

### Phase 2-3 (Parallel Experimentation & Higher-Level)

4. Multi-shadow orchestration
5. Task-level interface
6. Model flexibility testing (gpt-oss-20b forcing function)

### Phase 4 (After Approach Validated)

7. Set up new repository for distribution
8. Implement GitHub PR workflow (shadow → GitHub)
9. Document production deployment patterns

**Key principle**: We validate the full vision (Phases 0-3) before investing in distribution infrastructure (Phase 4).
