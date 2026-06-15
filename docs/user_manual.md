# MELFA Robot Automatic Backup Tool - User Manual

This manual explains how to configure, execute, and verify backups using the automatic backup tool.

---

## 1. Configuration (`settings.yaml`)

The tool's behavior is customized using the [settings.yaml](file:///c:/Users/alcz11702216/Documents/Python/Auto%20backup/settings.yaml) file, located in the same directory as the script.

### Configuration Options:

```yaml
robot:
  ip: "192.168.10.201"       # IP address of the CR800 controller
  port: 10001                # PC Support TCP port (commonly 10001 or 10002)
  timeout_seconds: 15        # Timeout limit for network communication
  name: "melfa_robot"        # Subfolder name created under the output directory

backup:
  # Backup Type Options:
  # - "code": Backs up only program container files (.MB6)
  # - "parameters": Backs up parameter profile files (.PRM)
  # - "full": Backs up all files on the controller filesystem (.MB6, .PRM, .log, .evl, etc.)
  type: "full"
  output_dir: "./backups"    # Root destination directory for backups
  retention_days: 30         # Days to keep backups (only active if git is disabled)

version_control:
  enabled: true              # Track backups inside a Git repository
  git_repo_path: "./backups" # Path to the Git repository
  auto_commit: true          # Commit changed files automatically after backup
```

---

## 2. Executing Backups

Open a terminal (Command Prompt or PowerShell) inside the directory of the script and run:

```powershell
python backup_tool.py
```

### CLI Overrides (Ad-hoc Runs)
You can override settings values directly from the CLI without editing `settings.yaml`:
* **Change Backup Type:**
  ```powershell
  python backup_tool.py --type parameters
  ```
* **Override IP Address:**
  ```powershell
  python backup_tool.py --ip 192.168.10.202
  ```

---

## 3. Directory Layout and File Categorization

Downloaded files are automatically sorted into categorized folders based on their extensions:

```
backups/
└── melfa_robot/
    └── YYYY-MM-DD_HH-MM-SS_full/  <-- Backup Timestamp with Type Suffix (e.g. _full, _code, _parameters)
        ├── robot_info.txt        (System firmware info)
        ├── program_list.txt      (Manifest of downloaded files)
        ├── programs/             (.MB6 program container files)
        │   ├── MAIN.MB6
        │   └── FT1.MB6
        ├── parameters/           (.PRM configuration parameters files)
        │   ├── COMMON.PRM
        │   └── USER#2.PRM
        ├── logs/                 (.LOG and .EVL system logs)
        │   ├── Event.log
        │   └── Event.evl
        └── system/               (All other extensions: .txt, .trp, etc.)
            └── README.txt
```

---

## 4. Understanding Log Outputs

The console outputs real-time logs indicating execution status. 

### Successful Run Example:
```
09:29:00 [INFO] Connecting to 127.0.0.1:10001 ...
09:29:00 [INFO] TCP connected.
09:29:00 [INFO] PLAIN TX: '1;1;OPEN=TOOLBOX'
09:29:00 [INFO] PLAIN RX: 'QoK3F;3F;7,0;0060;RV-2FRL-D;RV-2FRL-D.LST;000037'
09:29:00 [INFO] Session open - 3F;3F;7,0;0060;RV-2FRL-D;RV-2FRL-D.LST;000037
09:29:00 [INFO] PLAIN TX: '1;1;CHGPRT=HC'
09:29:00 [INFO] HC framing active.
09:29:00 [INFO] Backup mode active
09:29:00 [INFO] Filesystem info: 3F;3F;7,0;0060;RV-2FRL-D;RV-2FRL-D.LST;000037
09:29:00 [INFO] Starting backup with type: full
09:29:00 [INFO] Listing files via FDIR with area=*.*...
09:29:00 [INFO] Reported total files count: 6
09:29:00 [INFO]   [001] COMMON.PRM (modified 25-10-1309:42:52)
...
09:29:00 [INFO] Found 6 unique file(s) after deduplication.
09:29:00 [INFO] Downloading COMMON.PRM (parameters) ...
09:29:00 [INFO]   Saved 240 bytes -> backups/melfa_robot/2026-06-15_09-29-00/parameters/COMMON.PRM
09:29:00 [INFO] Session closed.
09:29:00 [INFO] TCP disconnected.
09:29:00 [INFO] Git: committed - 'Auto backup 2026-06-15 09:29:00'
09:29:00 [INFO] ✓ Backup complete.
```

---

## 5. Version History (Git integration)

If `version_control.enabled` is set to `true`, the tool initializes and commits changes to a Git repository located at `output_dir`.

### 1. View Backup Commit History:
Open a terminal in the `./backups` folder and run:
```bash
git log --oneline
```
Output:
```
a6a6d57 Auto backup 2026-06-15 09:29:01
92bc71c Auto backup 2026-06-14 09:30:12
```

### 2. View Line-by-Line Changes:
To inspect what changed inside parameters or program files between backups:
```bash
git log -p
```
Or view diffs for a specific file:
```bash
git diff HEAD~1 HEAD -- melfa_robot/2026-06-15_09-29-00/parameters/COMMON.PRM
```
