#!/usr/bin/env python3
"""
Unit Tests for MELFA Robot Automatic Backup Tool
Uses mock_robot_server in a background thread to verify all backup modes.
"""

import os
import sys
import unittest
import shutil
import tempfile
import time
import subprocess
from pathlib import Path

# Add workspace to path to import local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backup_tool import RobotBackup, load_settings, clean_old_backups
from mock_robot_server import MockMelfaServer

class TestMelfaBackupTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start mock server on a dynamic port
        cls.server = MockMelfaServer(host="127.0.0.1", port=0)
        cls.server.start()
        # Give thread a brief moment to spin up
        time.sleep(0.2)
        
    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        
    def setUp(self):
        # Create temp directory for backup outputs
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        # Clean up temp directory
        try:
            shutil.rmtree(self.test_dir)
        except Exception:
            pass
        
    def test_settings_load_fallback(self):
        # Test fallback parser by writing a temporary config file
        settings_file = os.path.join(self.test_dir, "test_settings.yaml")
        with open(settings_file, "w") as f:
            f.write("""
robot:
  ip: "127.0.0.1"
  port: 10001
  timeout_seconds: 5
  name: "test_melfa"

backup:
  type: "code"
  output_dir: "./test_backups"
  retention_days: 15

version_control:
  enabled: true
""")
        config = load_settings(settings_file)
        self.assertEqual(config["robot"]["ip"], "127.0.0.1")
        self.assertEqual(config["robot"]["port"], 10001)
        self.assertEqual(config["backup"]["type"], "code")
        self.assertEqual(config["backup"]["retention_days"], 15)
        self.assertTrue(config["version_control"]["enabled"])
        
    def test_backup_type_code(self):
        # Configure code backup
        settings = {
            "robot": {
                "ip": "127.0.0.1",
                "port": self.server.port,
                "timeout_seconds": 2,
                "name": "test_robot_code",
            },
            "backup": {
                "type": "code",
                "output_dir": self.test_dir,
            },
            "version_control": {
                "enabled": False,
            }
        }
        
        backup = RobotBackup(settings)
        success = backup.run()
        self.assertTrue(success, "Backup run should succeed")
        
        # Verify only .MB6 programs are downloaded under 'programs/'
        prog_dir = backup.backup_dir / "programs"
        self.assertTrue(prog_dir.exists(), "Programs folder must exist")
        
        # MAIN.MB6 and FT1.MB6 should be downloaded (from PDIR list)
        self.assertTrue((prog_dir / "MAIN.MB6").exists())
        self.assertTrue((prog_dir / "FT1.MB6").exists())
        
        # Other types should NOT be downloaded
        self.assertFalse((backup.backup_dir / "parameters").exists(), "Parameters folder should not exist")
        self.assertFalse((backup.backup_dir / "system").exists(), "System folder should not exist")
        self.assertFalse((backup.backup_dir / "logs").exists(), "Logs folder should not exist")
        
    def test_backup_type_parameters(self):
        # Configure parameters backup
        settings = {
            "robot": {
                "ip": "127.0.0.1",
                "port": self.server.port,
                "timeout_seconds": 2,
                "name": "test_robot_param",
            },
            "backup": {
                "type": "parameters",
                "output_dir": self.test_dir,
            },
            "version_control": {
                "enabled": False,
            }
        }
        
        backup = RobotBackup(settings)
        success = backup.run()
        self.assertTrue(success, "Backup run should succeed")
        
        # Verify only .PRM files are downloaded under 'parameters/'
        param_dir = backup.backup_dir / "parameters"
        self.assertTrue(param_dir.exists(), "Parameters folder must exist")
        
        # COMMON.PRM and USER#2.PRM should exist
        self.assertTrue((param_dir / "COMMON.PRM").exists())
        self.assertTrue((param_dir / "USER#2.PRM").exists())
        
        # Non-PRM files (even from FDIR list) should NOT be downloaded
        self.assertFalse((backup.backup_dir / "programs").exists(), "Programs folder should not exist")
        self.assertFalse((backup.backup_dir / "system").exists(), "System folder should not exist")
        
    def test_backup_type_full(self):
        # Configure full backup
        settings = {
            "robot": {
                "ip": "127.0.0.1",
                "port": self.server.port,
                "timeout_seconds": 2,
                "name": "test_robot_full",
            },
            "backup": {
                "type": "full",
                "output_dir": self.test_dir,
            },
            "version_control": {
                "enabled": False,
            }
        }
        
        backup = RobotBackup(settings)
        success = backup.run()
        self.assertTrue(success, "Backup run should succeed")
        
        # Verify files are downloaded and sorted
        prog_dir = backup.backup_dir / "programs"
        param_dir = backup.backup_dir / "parameters"
        logs_dir = backup.backup_dir / "logs"
        sys_dir = backup.backup_dir / "system"
        
        # Verify folder structures and files
        # PDIR files are not downloaded in full mode (or only if they are in FDIR)
        # 1.MB6 is returned by FDIR, so it should be in programs/
        self.assertTrue((prog_dir / "1.MB6").exists())
        
        # COMMON.PRM and USER#2.PRM in parameters/
        self.assertTrue((param_dir / "COMMON.PRM").exists())
        self.assertTrue((param_dir / "USER#2.PRM").exists())
        
        # Event.log and Event.evl in logs/
        self.assertTrue((logs_dir / "Event.log").exists())
        self.assertTrue((logs_dir / "Event.evl").exists())
        
        # README.txt in system/
        self.assertTrue((sys_dir / "README.txt").exists())
        
    def test_git_integration(self):
        # Create a temp git repo structure
        repo_dir = os.path.join(self.test_dir, "backups_repo")
        os.makedirs(repo_dir, exist_ok=True)
        
        # Initialize Git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
        
        settings = {
            "robot": {
                "ip": "127.0.0.1",
                "port": self.server.port,
                "timeout_seconds": 2,
                "name": "test_robot_git",
            },
            "backup": {
                "type": "code",
                "output_dir": repo_dir,
            },
            "version_control": {
                "enabled": True,
                "git_repo_path": repo_dir,
                "auto_commit": True,
            }
        }
        
        backup = RobotBackup(settings)
        success = backup.run()
        self.assertTrue(success, "Backup run should succeed")
        
        # Check git log for auto commit
        res = subprocess.run(["git", "log", "-n", "1", "--oneline"], cwd=repo_dir, capture_output=True, text=True)
        self.assertIn("Auto backup", res.stdout)
        
    def test_cleanup_retention(self):
        robot_dir = os.path.join(self.test_dir, "test_robot")
        os.makedirs(robot_dir, exist_ok=True)
        
        # Create new backup folder
        new_backup = os.path.join(robot_dir, "2026-06-09_12-00-00_full")
        os.makedirs(new_backup, exist_ok=True)
        
        # Create old backup folder (no suffix)
        old_backup = os.path.join(robot_dir, "2026-05-09_12-00-00")
        os.makedirs(old_backup, exist_ok=True)
        
        # Create old backup folder (with suffix)
        old_backup_suffixed = os.path.join(robot_dir, "2026-05-09_13-00-00_code")
        os.makedirs(old_backup_suffixed, exist_ok=True)
        
        # Artificially set old folders mod time to 40 days ago
        forty_days_ago = time.time() - (40 * 24 * 60 * 60)
        os.utime(old_backup, (forty_days_ago, forty_days_ago))
        os.utime(old_backup_suffixed, (forty_days_ago, forty_days_ago))
        
        # Verify existences
        self.assertTrue(os.path.exists(new_backup))
        self.assertTrue(os.path.exists(old_backup))
        self.assertTrue(os.path.exists(old_backup_suffixed))
        
        # Clean backups (retention policy = 30 days)
        clean_old_backups(robot_dir, retention_days=30)
        
        # Verify old folders are removed and new folder is retained
        self.assertTrue(os.path.exists(new_backup))
        self.assertFalse(os.path.exists(old_backup))
        self.assertFalse(os.path.exists(old_backup_suffixed))

if __name__ == "__main__":
    unittest.main()
