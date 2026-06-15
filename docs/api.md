# MELFA Robot Automatic Backup Tool - API Reference

This document provides documentation for developers extending or integrating the MELFA CR800 Backup Tool code.

---

## 1. Class: `MelfaProtocol`

Implements the low-level raw socket TCP connection and framing transactions.

### Methods:

#### `__init__(self, ip: str, port: int, timeout: float) -> None`
Initializes connection coordinates.

#### `connect(self) -> None`
Opens a TCP stream socket.

#### `disconnect(self) -> None`
Closes the active TCP socket.

#### `open_session(self) -> str`
Sends plaintext `1;1;OPEN=TOOLBOX` handshake. Returns controller model info.

#### `switch_to_hc(self) -> None`
Sends plaintext `1;1;CHGPRT=HC` protocol driver switch command.

#### `start_backup(self) -> str`
Sends HC-framed `1;1;OPEN=TOOLBOX;ENG` to unlock engineering mode.

#### `get_filesystem_info(self) -> str`
Sends HC-framed `1;1;MESTRD02` to retrieve filesystem header.

#### `get_directory_page(self, page: int) -> str`
Sends HC-framed `PDIR` command (using hex suffix for pages >= 1).

#### `get_fdir_page(self, page: int, area: str) -> str`
Sends HC-framed `FDIR` command (using `<` for page 0, and `0{page}` for page >= 1).

#### `open_file(self, filename: str) -> bool`
Sends `1;1;FOPEN{filename};r`.

#### `read_file_block(self, block_num: int) -> bytes`
Sends `1;1;FREAD{counter:02X}` (where counter cycles `0x30`-`0x3F` on 16 blocks). Returns decoded block bytes.

#### `close_file(self) -> None`
Sends `1;1;FCLOSE`.

#### `quit_file_mode(self) -> None`
Sends `1;1;FQUIT`.

#### `close_session(self) -> None`
Sends HC-framed `1;1;CLOSE`.

---

## 2. Class: `RobotBackup`

Orchestrates the backup procedure lifecycle.

### Methods:

#### `__init__(self, settings: dict) -> None`
Parses configuration dict, configures paths, and instantiates the protocol driver.

#### `run(self) -> bool`
Runs the backup queue: connects, handshakes, queries files, downloads, commits to Git, and performs retention cleanup.

#### `_list_programs(self) -> List[dict]`
Scans programs using PDIR.

#### `_list_files_fdir(self, area: str) -> List[dict]`
Scans files using FDIR, parses total count, and filters out duplicates.

#### `_download_files(self, files: List[dict]) -> None`
Downloads files in the queue and writes them to categorized subdirectories (`programs/`, `parameters/`, `logs/`, `system/`).

#### `_read_file(self) -> bytes`
Sequentially reads FREAD blocks until a partial block is encountered.

#### `_git_commit(self) -> None`
Stages files and commits changes with the current timestamp.

---

## 3. Utility Functions

#### `load_settings(path: str = "settings.yaml") -> dict`
Parses configuration settings from YAML, merging over defaults.

#### `parse_pdir_entry(payload: str) -> Optional[dict]`
Parses PDIR semicolon-separated entry.

#### `parse_fdir_entry(payload: str) -> Optional[dict]`
Parses FDIR semicolon-separated entry.

#### `parse_fdir_count(payload: str) -> Optional[int]`
Extracts total count value from FDIR page 0 response.

#### `clean_old_backups(robot_backup_dir: Union[str, Path], retention_days: int) -> None`
Deletes backup timestamp directories older than `retention_days`.
