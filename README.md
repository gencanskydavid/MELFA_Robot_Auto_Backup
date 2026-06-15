# MELFA CR800 Robot Automatic Backup Tool

A lightweight, high-performance Python-based command-line backup tool for **Mitsubishi Electric CR800 Series** robot controllers (MELFA series). 

This tool communicates directly with the controller over TCP/IP using the reverse-engineered RT ToolBox3 protocol. It performs automated backups of user programs (`.MB6`) and configuration profiles, making it ideal for scheduled backups, remote maintenance, and change tracking under version control (Git).

---

## ⚠️ Critical Requirement

> [!IMPORTANT]
> **RT ToolBox3 must be CLOSED** on your computer (and any other PC on the network) before running this backup tool. The CR800 controller only permits a single active connection on the PC Support port (`10001` or `10002`) at a time. If RT ToolBox3 is open, the tool will fail to connect.

---

## Features

- **Direct Communication:** No reliance on RT ToolBox3 software, third-party libraries, or Linux-only APIs (`libmelfa_api.so`). Works directly over TCP sockets.
- **Auto-Discovery & Pagination:** Queries the robot file directory page-by-page to dynamically build the download queue.
- **Robust Transmission:** Downloads files block-by-block using rolling sequences and checksum validation.
- **Git Version Control Integration:** Automatically initializes a Git repository in the backup folder, stages changes, and makes commits on successful backups.
- **Detailed Log Audits:** Clear output detailing execution, connection status, file sizes (line counts), and transfer rates.

---

## Quick Start

### 1. Prerequisites
- **Python 3.10** or newer.
- Installing YAML parser dependencies:
  ```bash
  pip install pyyaml
  ```
- **Git** installed and available in the system PATH (optional, but highly recommended for tracking file history).

### 2. Configuration
Create or modify `settings.yaml` in the directory of the script. Set your robot IP address and backup preferences:

```yaml
robot:
  ip: "192.168.10.201"       # IP address of the CR800 controller
  port: 10001                # PC Support port (typically 10001 or 10002)
  timeout_seconds: 15        # Network socket timeout limit
  name: "melfa_robot"        # Subfolder name for this robot's backups

backup:
  type: "programs"           # Type of backup (see Note below)
  output_dir: "./backups"    # Root directory where backups will be stored

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

## Backup Directory Structure

Upon completion, your backup folder will be structured as follows:
```
backups/
└── cr800_robot/
    └── YYYY-MM-DD_HH-MM-SS/      <-- Timestamped folder
        ├── robot_info.txt        (Controller model, serial, and firmware version)
        ├── program_list.txt      (Text file listing all downloaded programs)
        └── programs/             (Directory containing program files)
            ├── MAIN.MB6
            ├── PICK_PLACE.MB6
            └── ...
```

---

## 📝 Note on Parameter Backups (Experimental)

> [!WARNING]
> Parameter backups (`type: "full"` in config) are **currently unverified and experimental**. 
> The Wireshark packet capture used to write this tool was taken during a programs-only backup. The parameter download sequences (`.PAR` and `.VRB` files) have not yet been fully verified. 
> 
> Currently, the tool is fully verified only for downloading and backing up user programs (`.MB6` files). If you require critical system parameter backups, please continue using RT ToolBox3 until parameter verification is completed.

---

## 🛠️ Technical Protocol Specifications

For a detailed, low-level breakdown of the packet structures, HC frame layouts, XOR checksum calculation, and file transaction states, please read [PROTOCOL.md](./PROTOCOL.md).

---

## Troubleshooting

- **Connection Refused / Timeout:** 
  1. Ping the robot IP (e.g. `ping 192.168.10.201`) to verify physical network connectivity.
  2. Verify that **RT ToolBox3 is completely closed**.
  3. Ensure no other scripts or tools are connected to port `10001` or `10002`.
- **ModuleNotFoundError: No module named 'yaml':**
  Run `pip install pyyaml` in your terminal.
- **Git Commit fails:**
  Make sure you have Git installed, and you have run `git config --global user.name` and `git config --global user.email` to configure your Git profile on Windows.
