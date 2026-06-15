#!/usr/bin/env python3
"""
Mock MELFA Robot Server
Simulates a CR800 controller socket server for local testing of the backup tool.
Supports plaintext handshakes and HC-framed binary engineering commands.
"""

import socket
import threading
import sys
import time
import re

class MockMelfaServer:
    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port
        self.sock = None
        self.thread = None
        self.running = False
        
        # Simulated controller file system
        self.files = {
            "MAIN.MB6": "10 Mov P1\n20 Mov P2\n30 End",
            "FT1.MB6": "10 Mov P1\n20 End",
            "1.MB6": "10 Mov P1",
            "COMMON.PRM": "VAL1=12.34\nNETPORT=10001",
            "USER#2.PRM": "VAL2=56.78",
            "Event.log": "System OK",
            "Event.evl": "Event logged",
            "README.txt": "Melfa backup tool"
        }
        
        self.programs = ["MAIN.MB6", "FT1.MB6"]
        self.all_files = [
            "1.MB6", "COMMON.PRM", "USER#2.PRM", "Event.log", "Event.evl", "README.txt"
        ]
        
    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        # Retrieve actual port if bound to 0
        self.port = self.sock.getsockname()[1]
        self.sock.listen(1)
        self.running = True
        
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        print(f"Mock MELFA Server started on {self.host}:{self.port}")
        
    def stop(self):
        self.running = False
        if self.sock:
            try:
                temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                temp_sock.settimeout(0.1)
                temp_sock.connect((self.host, self.port))
                temp_sock.close()
            except Exception:
                pass
            self.sock.close()
            self.sock = None
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        print("Mock MELFA Server stopped.")
        
    def _listen_loop(self):
        while self.running:
            try:
                self.sock.settimeout(0.5)
                conn, addr = self.sock.accept()
            except socket.timeout:
                continue
            except Exception:
                break
                
            conn.settimeout(2.0)
            try:
                self._handle_client(conn)
            except Exception as e:
                print(f"Error handling mock client: {e}")
            finally:
                conn.close()
                
    def _make_ack_frame(self, seq: str) -> bytes:
        chk_input = f"HC{seq}A000200"
        checksum = 0
        for ch in chk_input:
            checksum ^= ord(ch)
        return f"\x02HC{seq}A000200{checksum:02X}\x03".encode('ascii')

    def _make_data_frame(self, seq: str, payload: str) -> bytes:
        len_str = f"{len(payload):04X}"
        chk_input = f"HC{seq}D{len_str}{payload}"
        checksum = 0
        for ch in chk_input:
            checksum ^= ord(ch)
        return f"\x02HC{seq}D{len_str}{payload}{checksum:02X}\x03".encode('ascii')

    def _handle_client(self, conn):
        buffer = bytearray()
        hc_mode = False
        active_file = None
        active_file_content = b""
        active_file_block = 0
        
        while self.running:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                buffer.extend(data)
                
                if not hc_mode:
                    # Plaintext mode
                    while b'\n' in buffer:
                        line_bytes, buffer = buffer.split(b'\n', 1)
                        line = line_bytes.decode('ascii', errors='ignore').strip()
                        if not line:
                            continue
                        
                        if line == "1;1;OPEN=TOOLBOX":
                            conn.sendall(b"QoK3F;3F;7,0;0060;RV-2FRL-D;RV-2FRL-D.LST;000037\r\n")
                        elif line == "1;1;CHGPRT=HC":
                            conn.sendall(b"QoK\r\n")
                            hc_mode = True
                            buffer = bytearray(buffer.lstrip(b'\r\n\x00'))
                else:
                    # HC-framed mode
                    while True:
                        start = buffer.find(b"\x02HC")
                        if start == -1:
                            break
                        
                        if len(buffer) < start + 17:
                            break
                            
                        len_hex = buffer[start + 13 : start + 17].decode('ascii', errors='ignore')
                        try:
                            payload_len = int(len_hex, 16)
                        except ValueError:
                            buffer = buffer[start + 3:]
                            continue
                            
                        total_len = 17 + payload_len + 3
                        if len(buffer) < start + total_len:
                            break
                            
                        frame = buffer[start : start + total_len]
                        buffer = buffer[start + total_len:]
                        
                        seq = frame[3:12].decode('ascii', errors='ignore')
                        payload = frame[17:17+payload_len].decode('ascii', errors='ignore')
                        
                        response_payload = ""
                        
                        if payload == "1;1;OPEN=TOOLBOX;ENG":
                            response_payload = "QoK3F;3F;7,0;3,5,A,1E,32,46,64;MB6;PRM;RV-2FRL-D;CR8xx-D;MELFA;26-01-22;Ver.E4;ENG"
                        elif payload == "1;1;MESTRD02":
                            response_payload = "QoK3F;3F;7,0;0060;RV-2FRL-D;RV-2FRL-D.LST;000037"
                        elif payload == "1;1;PDIR":
                            response_payload = "QoKMAIN.MB6;4554;25-07-1010:29:46;12;;92;15"
                        elif payload.startswith("1;1;PDIR"):
                            page_hex = payload[8:]
                            try:
                                page = int(page_hex, 16)
                            except ValueError:
                                page = 999
                            if page == 1:
                                response_payload = "QoKFT1.MB6;4554;25-07-1010:29:46;12;;42;5"
                            else:
                                response_payload = "QoK"
                                
                        elif payload.startswith("1;1;FDIR<"):
                            response_payload = f"QoK{self.all_files[0]};5555;25-10-1309:42:52;{len(self.all_files)};15027392;126C"
                        elif payload.startswith("1;1;FDIR0"):
                            m = re.match(r"1;1;FDIR0(\d+)(.*)", payload)
                            if m:
                                page = int(m.group(1))
                                if page <= len(self.all_files):
                                    response_payload = f"QoK{self.all_files[page-1]};5555;25-10-1309:42:52;1211"
                                else:
                                    response_payload = "QoK"
                            else:
                                response_payload = "QoK"
                                
                        elif payload.startswith("1;1;FOPEN"):
                            filename = payload[9:].split(";")[0].strip()
                            if filename in self.files:
                                active_file = filename
                                active_file_content = self.files[filename].encode('ascii')
                                active_file_block = 0
                                response_payload = "QoK1"
                            else:
                                response_payload = "QeR0404 (File Not Found)"
                                
                        elif payload.startswith("1;1;FREAD"):
                            if active_file is not None:
                                offset = active_file_block * 120
                                if offset < len(active_file_content):
                                    chunk = active_file_content[offset : offset + 120]
                                    hex_data = chunk.hex().upper()
                                    response_payload = f"QoK{hex_data};1"
                                    active_file_block += 1
                                else:
                                    response_payload = "QoK;1"
                            else:
                                response_payload = "QeR0103 (File Not Open)"
                                
                        elif payload == "1;1;FCLOSE":
                            active_file = None
                            response_payload = "QoK"
                        elif payload == "1;1;FQUIT":
                            response_payload = "QoK"
                        elif payload == "1;1;CLOSE":
                            ack_frame = self._make_ack_frame(seq)
                            data_frame = self._make_data_frame(seq, "QoK")
                            conn.sendall(ack_frame + data_frame)
                            return
                        else:
                            response_payload = "QeR9999 (Unknown Command)"
                            
                        ack_frame = self._make_ack_frame(seq)
                        data_frame = self._make_data_frame(seq, response_payload)
                        conn.sendall(ack_frame + data_frame)
                        
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Socket error in mock server: {e}")
                break
