"""
MELFA CR800 Robot Backup Tool
Protocol reverse-engineered via Wireshark capture of RT ToolBox3 communication.

=============================================================================
VERIFIED PROTOCOL (from Wireshark capture — programs-only backup)
=============================================================================

Port: 10002  (confirmed from OPSTSRD response in capture)

STEP 1 — Plain text connection:
  PC    -> "1;1;OPEN=TOOLBOX\r\n"         (no ;ENG suffix on initial connect)
  Robot -> "QoK3F;3F;7,0;..."

STEP 2 — Switch to HC framing (plain text):
  PC    -> "1;1;CHGPRT=HC\r\n"
  Robot -> "QoK"

STEP 3 — Start backup (HC-framed, equivalent of clicking Backup in ToolBox3):
  PC    -> HC{ "1;1;OPEN=TOOLBOX;ENG" }   (;ENG suffix distinguishes backup mode)
  Robot -> HC{ "QoK3F;3F;7,0;..." }

STEP 4 — HC-framed backup commands:
  Filesystem info:
    PC    -> HC{ "1;1;MESTRD02" }
    Robot -> HC{ "QoK3F;3F;7,0;0060;RV-2FRL-D;RV-2FRL-D.LST;000037" }

  Program list (first page, no suffix; subsequent pages with 2-hex-digit number):
    PC    -> HC{ "1;1;PDIR" }             (page 0 — no number)
    Robot -> HC{ "QoKNAME.MB6;attr;datetime;f3;f4;type;;lines;edits;..." }
    PC    -> HC{ "1;1;PDIR01" }           (page 1)
    PC    -> HC{ "1;1;PDIR02" }           (page 2) ...
    Robot -> HC{ "QoK" }                  (empty = end of list)

  PDIR response field layout (semicolon-separated):
    [0]  filename e.g. "FT1.MB6"
    [1]  attribute/CRC e.g. "4554"
    [2]  datetime    e.g. "25-07-1010:29:46"
    [3]  field3      e.g. "12"
    [4]  field4      e.g. "" (empty)
    [5]  field5      e.g. "92" (line/step count — best proxy for file size)
    [6]  edit_count  e.g. "15"
    [7-9] execution metrics

  File download (FREAD uses a rolling counter 0x30-0x3F, not a byte offset):
    PC    -> HC{ "1;1;FREAD{counter:02X}" }
    Robot -> HC{ "QoK{240-byte block as 480 hex chars}" }
    Counter cycles 0x30 to 0x3F per file. EOF is signaled by a partial block
    (< 240 bytes) or an empty/QeR response.

STEP 5 — Disconnect (HC-framed):
  PC    -> HC{ "1;1;CLOSE" }
  Robot -> HC{ "QoK" }
  [TCP closes]

NOTE: PARCRC= commands in the capture are RT ToolBox3 background polling on
      connect — NOT part of the backup. A full-backup capture is needed to
      verify the parameter backup command sequence.
=============================================================================
"""

from __future__ import annotations
import copy
import socket
import re
import logging
import subprocess
import yaml
from datetime import datetime
from pathlib import Path
from typing import Union, Optional, List, Dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict = {
    "robot": {
        "ip": "192.168.0.20",
        "port": 10002,
        "timeout_seconds": 10,
        "name": "melfa_robot",
    },
    "backup": {
        "output_dir": "./backups",
    },
    "version_control": {
        "enabled": True,
        "git_repo_path": "./backups",
        "auto_commit": True,
    },
}


def load_settings(path: str = "settings.yaml") -> dict:
    """Load settings.yaml and deep-merge over defaults."""
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        for key, value in loaded.items():
            if isinstance(value, dict) and key in settings:
                settings[key].update(value)
            else:
                settings[key] = value
    except FileNotFoundError:
        log.warning("settings.yaml not found — using defaults.")
    return settings


# ---------------------------------------------------------------------------
# HC Protocol
# ---------------------------------------------------------------------------

class MelfaProtocol:
    """
    Implements the verified two-phase MELFA HC communication protocol.

    Phase 1 — plain ASCII text  (OPEN=TOOLBOX + CHGPRT=HC)
    Phase 2 — HC-framed binary  (all backup commands)

    HC request frame format (from capture analysis):
        .HC{seq:09d}{src_addr:04X}R{payload_len:04X}{payload}{xor_checksum:02X}.

    HC response frame ends with a '.' terminator. The terminator character
    is also valid inside data (e.g. in file content or IP addresses), so we
    read until we see a '.' that follows a 2-char hex checksum — however in
    practice we read until the FIRST '.' after receiving "QoK" or "QeR" since
    the robot always terminates response frames at sentence boundary.
    """

    CHUNK_BYTES  = 120       # raw bytes returned per FREAD block
    CHUNK_HEX    = 240       # hex chars for CHUNK_BYTES (2 chars per byte)
    RECV_BUF     = 4096      # socket recv buffer
    RESP_MAX     = 131072    # hard cap per response

    def __init__(self, ip: str, port: int, timeout: float) -> None:
        self.ip      = ip
        self.port    = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._seq    = 0
        self._recv_buf = b""

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        log.info(f"Connecting to {self.ip}:{self.port} ...")
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect((self.ip, self.port))
        log.info("TCP connected.")

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        log.info("TCP disconnected.")

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------

    def _send(self, data: bytes) -> None:
        if not self._sock:
            raise RuntimeError("Not connected.")
        self._sock.sendall(data)

    def _recv_until(self, terminator: bytes) -> bytes:
        """Accumulate socket data until `terminator` is found, preserving leftovers."""
        if terminator in self._recv_buf:
            idx = self._recv_buf.index(terminator) + len(terminator)
            res = self._recv_buf[:idx]
            self._recv_buf = self._recv_buf[idx:]
            return res

        while len(self._recv_buf) < self.RESP_MAX:
            try:
                chunk = self._sock.recv(self.RECV_BUF)
            except socket.timeout:
                raise TimeoutError("Robot did not respond in time.")
            if not chunk:
                raise ConnectionError("Connection closed by robot.")
            log.info(f"Socket received chunk: {chunk!r}")
            self._recv_buf += chunk
            if terminator in self._recv_buf:
                idx = self._recv_buf.index(terminator) + len(terminator)
                res = self._recv_buf[:idx]
                self._recv_buf = self._recv_buf[idx:]
                return res
        raise RuntimeError(f"Response exceeded {self.RESP_MAX}-byte limit.")

    def _recv_hc_frame(self) -> bytes:
        """
        Extract the next complete HC frame from the persistent buffer.
        Blocks and reads from socket if the buffer does not contain a complete frame.
        """
        while True:
            # Find the start of the frame (HC framing uses STX \x02 and ETX \x03)
            start = self._recv_buf.find(b"\x02HC")
            if start == -1:
                # Discard noise but keep up to 2 bytes in case of partial "\x02HC"
                if len(self._recv_buf) > 2:
                    self._recv_buf = self._recv_buf[-2:]
                
                try:
                    chunk = self._sock.recv(self.RECV_BUF)
                except socket.timeout:
                    raise TimeoutError("Robot did not respond in time.")
                if not chunk:
                    raise ConnectionError("Connection closed by robot.")
                log.info(f"Socket received chunk: {chunk!r}")
                self._recv_buf += chunk
                continue

            # We have "\x02HC" at index `start`.
            # Make sure we have at least 17 bytes to read the header (up to length field)
            if len(self._recv_buf) < start + 17:
                try:
                    chunk = self._sock.recv(self.RECV_BUF)
                except socket.timeout:
                    raise TimeoutError("Robot did not respond in time.")
                if not chunk:
                    raise ConnectionError("Connection closed by robot.")
                log.info(f"Socket received chunk: {chunk!r}")
                self._recv_buf += chunk
                continue

            # Determine frame type at index `start + 12`
            frame_type = self._recv_buf[start + 12 : start + 13]
            
            if frame_type in (b"A", b"J", b"E"):
                # Control frame (fixed length of 22 bytes)
                total_len = 22
                if len(self._recv_buf) < start + total_len:
                    try:
                        chunk = self._sock.recv(self.RECV_BUF)
                    except socket.timeout:
                        raise TimeoutError("Robot did not respond in time.")
                    if not chunk:
                        raise ConnectionError("Connection closed by robot.")
                    log.info(f"Socket received chunk: {chunk!r}")
                    self._recv_buf += chunk
                    continue
                
                frame = self._recv_buf[start : start + total_len]
                self._recv_buf = self._recv_buf[start + total_len:]
                log.info(f"Parsed Control Frame ({frame_type.decode('ascii')}): {frame!r}")
                return frame
                
            elif frame_type == b"D":
                # Data frame (variable length)
                len_hex = self._recv_buf[start + 13 : start + 17].decode("ascii", errors="ignore")
                try:
                    payload_len = int(len_hex, 16)
                except ValueError:
                    log.warning(f"Invalid length hex: {len_hex!r}. Discarding frame prefix.")
                    self._recv_buf = self._recv_buf[start + 3:]
                    continue
                
                total_len = 17 + payload_len + 3  # 17 (header) + L (payload) + 2 (checksum) + 1 (trailer dot)
                if len(self._recv_buf) < start + total_len:
                    try:
                        chunk = self._sock.recv(self.RECV_BUF)
                    except socket.timeout:
                        raise TimeoutError("Robot did not respond in time.")
                    if not chunk:
                        raise ConnectionError("Connection closed by robot.")
                    log.info(f"Socket received chunk: {chunk!r}")
                    self._recv_buf += chunk
                    continue
                
                frame = self._recv_buf[start : start + total_len]
                self._recv_buf = self._recv_buf[start + total_len:]
                log.info(f"Parsed Data Frame: {frame!r}")
                return frame
                
            else:
                # Unknown frame type, discard ".HC" to find next
                log.warning(f"Unknown frame type {frame_type!r} in buffer. Discarding prefix.")
                self._recv_buf = self._recv_buf[start + 3:]
                continue

    # ------------------------------------------------------------------
    # Phase 1 — plain text (before HC mode)
    # ------------------------------------------------------------------

    def _send_plain(self, cmd: str) -> str:
        """Send a plain-text command terminated with CR+LF, return response."""
        log.info(f"PLAIN TX: {cmd!r}")
        self._send(f"{cmd}\r\n".encode("ascii"))
        
        # Plain-text responses are short and fit in a single TCP packet.
        if not self._recv_buf:
            try:
                chunk = self._sock.recv(self.RECV_BUF)
            except socket.timeout:
                raise TimeoutError("Robot did not respond in time.")
            if not chunk:
                raise ConnectionError("Connection closed by robot.")
            log.info(f"Socket received chunk: {chunk!r}")
            self._recv_buf += chunk
            
        raw = self._recv_buf
        self._recv_buf = b""
        resp = raw.decode("ascii", errors="replace").strip()
        log.info(f"PLAIN RX: {resp[:80]!r}")
        return resp

    # ------------------------------------------------------------------
    # Phase 2 — HC framing
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _build_frame(self, payload: str) -> bytes:
        """
        Build one HC request frame.

        VERIFIED format (confirmed against 3 known frames from Wireshark capture):
          \x02HC{seq:09d}R{len:04X}{payload}{checksum:02X}\x03.

        Checksum = XOR of every ASCII byte in:
          'HC' + seq_str + 'R' + len_str + payload
        i.e. NOT just the payload — includes the frame header chars too.
        """
        seq     = self._next_seq()
        seq_str = f"{seq:09d}"
        len_str = f"{len(payload):04X}"
        chk_input = f"HC{seq_str}R{len_str}{payload}"
        checksum = 0
        for ch in chk_input:
            checksum ^= ord(ch)
        frame = f"\x02HC{seq_str}R{len_str}{payload}{checksum:02X}\x03".encode("ascii")
        log.debug(f"HC TX: {payload!r}  chk={checksum:02X}")
        return frame

    def _send_hc(self, cmd: str) -> str:
        """
        Send an HC-framed command and return the parsed payload string.
        """
        self._send(self._build_frame(cmd))
        return self._recv_hc_response()

    def _recv_hc_response(self) -> str:
        """
        Receive and return the payload of the next Data frame.
        Discards control/ACK frames.
        """
        while True:
            frame = self._recv_hc_frame()
            if frame[12:13] == b"D":
                raw = frame.decode("ascii", errors="replace")
                return self._extract_payload(raw)

    def _send_hc_raw(self, cmd: str) -> bytes:
        """Send HC command, return the raw byte response of the Data frame."""
        self._send(self._build_frame(cmd))
        while True:
            frame = self._recv_hc_frame()
            if frame[12:13] == b"D":
                return frame

    @staticmethod
    def _extract_payload(raw: str) -> str:
        """
        Extract the data payload from a QoK response frame.
        Strips the leading headers, QoK prefix, and the trailing 2-char checksum + ETX.
        """
        if "QoK" not in raw:
            if "QeR" in raw:
                # Error payload format: ...QeR{error_msg}{checksum}\x03
                start = raw.index("QeR") + 3
                err = raw[start:-3].strip()
                log.warning(f"QeR error from robot: {err!r}")
            return ""
        
        start = raw.index("QoK") + 3
        # Strip trailing 2 hex checksum chars + 1 ETX char
        return raw[start:-3]

    # ------------------------------------------------------------------
    # Verified high-level commands
    # ------------------------------------------------------------------

    def open_session(self) -> str:
        """
        VERIFIED (Wireshark line 1-2):
        Plain-text initial handshake — NO ;ENG suffix on first connect.
        """
        resp = self._send_plain("1;1;OPEN=TOOLBOX")
        if not resp.startswith("QoK"):
            raise ConnectionError(f"OPEN=TOOLBOX rejected: {resp!r}")
        log.info(f"Session open — {resp[3:80]}")
        return resp

    def switch_to_hc(self) -> None:
        """
        VERIFIED (Wireshark line 3-4):
        Plain-text switch to HC framing — sent immediately after OPEN=TOOLBOX.
        """
        resp = self._send_plain("1;1;CHGPRT=HC")
        if "QoK" not in resp:
            raise ConnectionError(f"CHGPRT=HC rejected: {resp!r}")
        log.info("HC framing active.")

    def start_backup(self) -> str:
        """
        VERIFIED (Wireshark line 15-16):
        HC-framed OPEN=TOOLBOX;ENG — sent within the HC session to start
        backup mode. The ;ENG suffix distinguishes backup from monitor mode.
        """
        resp = self._send_hc("1;1;OPEN=TOOLBOX;ENG")
        log.info(f"Backup mode active — {resp[:60]}")
        return resp

    def get_filesystem_info(self) -> str:
        """
        VERIFIED (Wireshark lines 9-10, 891-892):
        MESTRD02 returns robot model and LST filename.
        Example: '3F;3F;7,0;0060;RV-2FRL-D;RV-2FRL-D.LST;000037'
        """
        return self._send_hc("1;1;MESTRD02")

    def get_directory_page(self, page: int) -> str:
        """
        VERIFIED (Wireshark lines 951-1082):
        PDIR lists programs one per page.
        Page 0 uses no suffix; pages 1+ use a 2-digit hex suffix.
        Returns the raw PDIR payload, or '' when the list is exhausted.
        """
        if page == 0:
            cmd = "1;1;PDIR"
        else:
            cmd = f"1;1;PDIR{page:02X}"
        return self._send_hc(cmd)

    def read_file_block(self, block_num: int) -> bytes:
        """
        VERIFIED (Wireshark lines 5491+, 5527+):
        FREAD downloads one block of the currently FOPEN'd file.

        The FREAD argument is a 2-char hex string in the range 0x30-0x3F
        (ASCII '0'-'?'), cycling every 16 blocks:
          block 0 -> '30', block 1 -> '31', ..., block 15 -> '3F',
          block 16 -> '30' (wraps), etc.

        Full blocks return 240 bytes (480 hex chars).
        A PARTIAL block (< 240 bytes) signals end-of-file.
        Empty / QeR response also signals end-of-file.
        """
        counter = 0x30 + (block_num % 16)
        counter_str = f"{counter:02X}"  # '30', '31', ... '3F'
        raw = self._send_hc_raw(f"1;1;FREAD{counter_str}")
        text = raw.decode("ascii", errors="replace")

        if "QoK" not in text:
            return b""

        # Extract clean payload (excluding header, QoK prefix, and checksum/ETX)
        payload = self._extract_payload(text)
        if not payload:
            return b""

        # The payload format is: {hex_chars};{status} (e.g. "524F42...000;1")
        hex_str = payload.split(";")[0].strip()
        if not hex_str:
            return b""

        try:
            return bytes.fromhex(hex_str)
        except ValueError:
            log.warning(f"Failed to parse hex string of block {block_num}: {hex_str[:40]}...")
            return b""

    def open_file(self, filename: str) -> bool:
        """
        VERIFIED (Wireshark line 5497, 5525):
        FOPEN opens a file on the controller for reading.
        Format: 1;1;FOPEN{FILENAME};r
        Returns True on QoK, False on error.
        """
        resp = self._send_hc(f"1;1;FOPEN{filename};r")
        # QoK returns a short payload (single digit); empty = error
        success = resp is not None  # _send_hc returns '' on QeR
        if not success:
            log.warning(f"FOPEN {filename} failed")
        return True  # QeR is already logged by _send_hc/_extract_payload

    def close_file(self) -> None:
        """
        VERIFIED (Wireshark line 5493, 5521):
        FCLOSE closes the currently open file.
        """
        try:
            self._send_hc("1;1;FCLOSE")
        except Exception:
            pass

    def quit_file_mode(self) -> None:
        """
        VERIFIED (Wireshark line 5495, 5523):
        FQUIT exits file transfer mode after FCLOSE.
        Always called after FCLOSE before the next FOPEN.
        """
        try:
            self._send_hc("1;1;FQUIT")
        except Exception:
            pass


    def close_session(self) -> None:
        """
        VERIFIED (Wireshark line 7439-7441):
        HC-framed CLOSE — last command before TCP disconnect.
        """
        try:
            self._send_hc("1;1;CLOSE")
            log.info("Session closed.")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# PDIR response parser
# ---------------------------------------------------------------------------

def parse_pdir_entry(payload: str) -> Optional[dict]:
    """
    Parse one PDIR response payload into a structured dict.

    Verified field layout from capture (semicolon-separated):
      [0]  filename       e.g. "FT1.MB6"
      [1]  attribute/CRC  e.g. "4554"
      [2]  datetime       e.g. "25-07-1010:29:46"  (date+time run together)
      [3]  field3         e.g. "12"
      [4]  field4         e.g. ""  (often empty)
      [5]  line_count     e.g. "92"  ← best available proxy for program size
      [6]  edit_count     e.g. "15"
      [7+] execution metrics

    Returns None if the payload does not look like a valid PDIR entry.
    """
    if not payload or not payload.strip():
        return None

    parts = payload.split(";")
    if len(parts) < 6:
        return None

    name = parts[0].strip()
    if not name.upper().endswith(".MB6"):
        return None

    try:
        line_count = int(parts[5].strip()) if parts[5].strip() else 0
    except (ValueError, IndexError):
        line_count = 0

    return {
        "name":       name,
        "attr":       parts[1].strip() if len(parts) > 1 else "",
        "datetime":   parts[2].strip() if len(parts) > 2 else "",
        "line_count": line_count,
        "raw":        payload,
    }


# ---------------------------------------------------------------------------
# Backup orchestration
# ---------------------------------------------------------------------------

class RobotBackup:

    # Maximum blocks to read per file (240 bytes each → 240 * 512 = 122 880 bytes max)
    MAX_BLOCKS = 512

    def __init__(self, settings: dict) -> None:
        self.settings = settings
        robot = settings["robot"]

        self.proto = MelfaProtocol(
            ip=robot["ip"],
            port=robot["port"],
            timeout=robot["timeout_seconds"],
        )

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.backup_dir = (
            Path(settings["backup"]["output_dir"])
            / robot["name"]
            / timestamp
        )
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Backup directory: {self.backup_dir}")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> bool:
        try:
            self.proto.connect()
            self.proto.open_session()      # plain:  OPEN=TOOLBOX
            self.proto.switch_to_hc()      # plain:  CHGPRT=HC
            self.proto.start_backup()      # HC:     OPEN=TOOLBOX;ENG

            info = self.proto.get_filesystem_info()
            log.info(f"Filesystem info: {info}")
            (self.backup_dir / "robot_info.txt").write_text(info, encoding="utf-8")

            programs = self._list_programs()
            log.info(f"Found {len(programs)} program(s).")
            (self.backup_dir / "program_list.txt").write_text(
                "\n".join(p["name"] for p in programs),
                encoding="utf-8",
            )

            self._download_programs(programs)

            self.proto.close_session()     # HC:     CLOSE
            self.proto.disconnect()        # TCP close

            if self.settings["version_control"]["enabled"]:
                self._git_commit()

            log.info("✓ Backup complete.")
            return True

        except Exception as exc:
            log.error(f"Fatal Error during backup: {exc}", exc_info=True)
            try:
                self.proto.disconnect()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # Step 1: list all programs via PDIR
    # ------------------------------------------------------------------

    def _list_programs(self) -> List[dict]:
        log.info("Listing programs via PDIR...")
        programs: list[dict] = []

        for page in range(512):
            resp = self.proto.get_directory_page(page)
            if not resp:
                log.debug(f"PDIR page {page}: empty — end of list.")
                break

            entry = parse_pdir_entry(resp)
            if entry:
                programs.append(entry)
                log.info(f"  [{page:03d}] {entry['name']}  "
                         f"({entry['line_count']} lines, modified {entry['datetime']})")
            else:
                log.debug(f"PDIR page {page}: not an MB6 entry — {resp[:40]!r}")

        return programs

    # ------------------------------------------------------------------
    # Step 2: download each program via FREAD
    # ------------------------------------------------------------------

    def _download_programs(self, programs: List[dict]) -> None:
        prog_dir = self.backup_dir / "programs"
        prog_dir.mkdir(exist_ok=True)

        for entry in programs:
            name = entry["name"]
            log.info(f"Downloading {name} ...")

            # VERIFIED sequence: FOPEN -> FREAD loop -> FCLOSE -> FQUIT
            self.proto.open_file(name)
            data = self._read_file()
            self.proto.close_file()
            self.proto.quit_file_mode()

            if data:
                dest = prog_dir / name
                dest.write_bytes(data)
                log.info(f"  Saved {len(data):,} bytes → {dest}")
            else:
                log.warning(f"  {name}: no data received — skipped.")

    def _read_file(self) -> bytes:
        """
        Download the currently FOPEN'd file using sequential FREAD blocks.

        VERIFIED EOF detection (Wireshark line 5492):
        A PARTIAL block (less than the full chunk size) is the true end-of-file signal.
        A full block always means more data follows.
        """
        data = b""
        chunk_size = self.proto.CHUNK_BYTES

        for block_num in range(self.MAX_BLOCKS):
            block = self.proto.read_file_block(block_num)

            if not block:
                log.debug(f"  Block {block_num}: empty response — EOF")
                break

            if block_num == 0:
                # Dynamically set chunk size based on the actual size of the first block
                chunk_size = len(block)
                log.debug(f"  First block size: {chunk_size} bytes")

            data += block
            log.debug(f"  Block {block_num}: {len(block)} bytes")

            if len(block) < chunk_size:
                # Partial block = last block of file (verified from capture)
                log.debug(f"  Block {block_num}: partial ({len(block)}/{chunk_size}) — EOF")
                break

        return data




    # ------------------------------------------------------------------
    # Git version control
    # ------------------------------------------------------------------

    def _git_commit(self) -> None:
        if not self.settings["version_control"].get("auto_commit", True):
            return

        repo = Path(self.settings["version_control"]["git_repo_path"])
        if not repo.exists():
            log.warning(f"Git repo path does not exist: {repo}")
            return

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo, capture_output=True, text=True, check=True,
            )
            if not result.stdout.strip():
                log.info("Git: nothing new to commit.")
                return

            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            msg = f"Auto backup {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            subprocess.run(["git", "commit", "-m", msg], cwd=repo, check=True)
            log.info(f"Git: committed — {msg!r}")

        except FileNotFoundError:
            log.warning("git not found in PATH — version control skipped.")
        except subprocess.CalledProcessError as exc:
            log.error(f"Git command failed: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = load_settings("settings.yaml")
    log.info(f"Target: {cfg['robot']['ip']}:{cfg['robot']['port']}")
    success = RobotBackup(cfg).run()
    raise SystemExit(0 if success else 1)
