# MELFA Robot Automatic Backup Tool - Installation Manual

This manual provides instructions for preparing the Mitsubishi Electric CR800 controller, configuring the network topology, setting up Python, and preparing Git version control.

---

## 1. Network Topology & Hardware Setup

For the backup script to communicate with the robot controller, they must be connected on the same physical Ethernet network (typically via an industrial switch or direct RJ-45 patch cable).

### Subnet Alignment
Ensure that your computer's network interface card (NIC) is configured with a static IP address in the same subnet as the controller.
* **Controller Default IP:** `192.168.0.20` (or `192.168.10.201` as configured in settings.yaml)
* **Recommended PC Settings:**
  * IP Address: `192.168.10.100` (or matching the subnet of your controller)
  * Subnet Mask: `255.255.255.0`

---

## 2. Controller Configuration (PC Support Protocol)

The CR800 controller must have its Ethernet parameters configured to open a TCP listening port assigned to the **PC Support** protocol. This is done using **RT ToolBox3**.

### Steps to Configure in RT ToolBox3:
1. Open **RT ToolBox3** and connect to your robot.
2. In the project tree, double-click on **Parameter** -> **Ethernet Setting**.
3. Select an open port index (commonly Line 1 or Line 2).
4. Set the following fields:
   * **Protocol:** `PC Support` (R3 protocol)
   * **Port Number:** `10001` or `10002` (as defined by the `NETPORT` system parameter)
   * **Host IP Address:** Leave blank (or specify your PC's IP address if you wish to restrict access)
5. Click **Write** to save parameters to the controller.
6. **Reboot the Controller** to apply the settings.

> [!CRITICAL]
> **Single Connection Limit:**
> The CR800 controller allows only **one active socket connection** per PC Support port at a time. Before running the backup script, you **must close RT ToolBox3** or any other monitoring software on your network. Otherwise, the socket connection will be refused.

---

## 3. PC software Prerequisites

### 1. Python Installation
* Install **Python 3.10** or newer from the [official site](https://www.python.org/downloads/).
* Ensure the installer option **"Add Python to PATH"** is selected.

### 2. Dependency Setup
The tool requires the `PyYAML` package to load configuration settings.
Open PowerShell/CMD and run:
```powershell
pip install pyyaml
```

### 3. Git Version Control Installation
To use the auto-commit version tracking:
1. Download and install **Git for Windows** from [git-scm.com](https://git-scm.com/).
2. Confirm the installation by running:
   ```cmd
   git --version
   ```
3. Configure your Git identity (required for committing backups):
   ```cmd
   git config --global user.name "Your Name"
   git config --global user.email "your.email@example.com"
   ```
