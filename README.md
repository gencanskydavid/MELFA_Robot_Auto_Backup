# MELFA CR800 Robot Automatic Backup Tool

A lightweight, high-performance Python-based command-line backup tool for **Mitsubishi Electric CR800 Series** robot controllers (MELFA series).

This tool communicates directly with the controller over TCP/IP using the reverse-engineered RT ToolBox3 protocol. It performs automated backups of user programs (`.MB6`), system configuration parameters (`.PRM`), and event logs (`.LOG`, `.EVL`), making it ideal for scheduled backups, remote maintenance, and change tracking under version control (Git).

---

## ⚠️ Critical Requirement

> [!IMPORTANT]
> **RT ToolBox3 must be CLOSED** on your computer (and any other PC on the network) before running this backup tool. The CR800 controller only permits a single active connection on the PC Support port (`10001` or `10002`) at a time. If RT ToolBox3 is open, the tool will fail to connect.

---

## Features

- **Direct Communication:** No reliance on RT ToolBox3 software, third-party libraries, or Linux-only APIs (`libmelfa_api.so`). Works directly over TCP sockets.
- **Multiple Backup Types:** Fully supports `"code"` (programs), `"parameters"`, and `"full"` backup scopes.
- **Auto-Discovery & Pagination:** Queries the robot file directory using `PDIR` or `FDIR` page-by-page to dynamically build the download queue.
- **Extension-Based Subfolder Sorting:** Automatically organizes downloaded files into `programs/`, `parameters/`, `logs/`, and `system/` folders.
- **Robust Transmission:** Downloads files block-by-block using rolling sequences and checksum validation.
- **Git Version Control Integration:** Automatically initializes a Git repository in the backup folder, stages changes, and makes commits on successful backups to track historical differences.
- **Retention Policies:** Cleans up older backup directories based on a customizable cutoff (when Git is disabled).

---

## Quick Start

### 1. Prerequisites
- **Python 3.10** or newer.
- Install YAML parser dependency:
  ```bash
  pip install pyyaml
  ```
- **Git** installed and configured in your system PATH (optional, but highly recommended for tracking file history).

### 2. Configuration
Create or modify `settings.yaml` in the directory of the script. Set your robot IP address and backup preferences:

```yaml
robot:
  ip: "192.168.10.201"       # IP address of the CR800 controller
  port: 10001                # PC Support port (typically 10001 or 10002)
  timeout_seconds: 15        # Network socket timeout limit
  name: "melfa_robot"        # Subfolder name for this robot's backups

backup:
  type: "full"               # Options: "full", "parameters", "code"
  output_dir: "./backups"    # Root directory where backups will be stored
  retention_days: 30         # Backups retention policy

version_control:
  enabled: true              # Initialize/track backups inside a Git repository
  git_repo_path: "./backups" # Git repository path
  auto_commit: true          # Automatically commit backups after successful completion
```

### 3. Run the Tool
Ensure RT ToolBox3 is closed, and run:
```bash
python backup_tool.py
```

---

## Project Documentation Index

For in-depth guides and technical details, please read:

1. **[Installation Manual](./docs/installation.md):** Preparing physical connections, setting up Python, and configuring the `PC Support` protocol driver on the CR800 controller using RT ToolBox3 parameters.
2. **[User Manual](./docs/user_manual.md):** Configuration settings, CLI parameters override, log interpretation, directory structures, and Git history change diffs inspection.
3. **[Software Architecture Overview](./docs/architecture.md):** System block diagrams, handshake protocol transitions (Plaintext to HC-framed), commands comparison (PDIR vs FDIR), download sequential state machine, and mock testing layer.
4. **[API Reference](./docs/api.md):** Class structures, method definitions, parameter types, and utilities reference for developers.
5. **[Protocol Reference Guide](./PROTOCOL.md):** Direct packet specification of R3/HC framing, sequence numbers, XOR checksum equation, and FREAD rolling offsets.
6. **[RAG Index File](./llms.txt):** Structured index for AI crawlers mapping files, dependencies, and protocol mechanics.

---

## Troubleshooting

- **Connection Refused / Timeout:**
  1. Ping the robot IP (e.g. `ping 192.168.10.201`) to verify network connectivity.
  2. Verify that **RT ToolBox3 is completely closed**.
  3. Ensure no other scripts or tools are connected to port `10001` or `10002`.
- **ModuleNotFoundError: No module named 'yaml':**
  Run `pip install pyyaml` in your terminal.
- **Git Commit fails:**
  Make sure you have Git installed, and you have configured Git:
  ```bash
  git config --global user.name "Your Name"
  git config --global user.email "your@email.com"
  ```
