import sys
from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but we can fine-tune packages and excludes to keep the build light.
build_exe_options = {
    "packages": ["yaml", "shutil", "socket", "re", "logging", "subprocess", "datetime", "pathlib"],
    "excludes": ["tkinter", "unittest", "email", "pydoc_data", "html", "http", "urllib", "xml"],
    "include_files": ["settings.yaml"],
}

setup(
    name="MELFA_Backup_Tool",
    version="1.1",
    description="MELFA CR800 Robot Automatic Backup Tool",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "backup_tool.py",
            target_name="backup_tool.exe",
            base=None,  # Console application (use "Win32GUI" for GUI apps)
        )
    ],
)
