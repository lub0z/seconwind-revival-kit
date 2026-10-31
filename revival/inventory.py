"""Hardware inventory for a customer machine, read-only.

Run from a Linux Mint live USB (or after install):  python3 -m revival inventory
Root is optional; with sudo it can also read the serial number and disk health (SMART).
"""

import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

SYS = Path("/sys")
PROC = Path("/proc")

# Linux Mint 22 guidance: 2 GB RAM minimum (4 GB recommended), 20 GB disk minimum (100 GB recommended), 64-bit CPU.
MIN_RAM_GB, GOOD_RAM_GB = 2, 4
MIN_DISK_GB, GOOD_DISK_GB = 20, 100


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _run(cmd: list[str], timeout: int = 20) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def system_info(sys_root: Path = SYS) -> dict:
    dmi = sys_root / "class/dmi/id"
    vendor = _read(dmi / "sys_vendor")
    product = _read(dmi / "product_name")
    version = _read(dmi / "product_version")
    # Lenovo puts the friendly model name in product_version
    model = f"{vendor} {version}" if vendor.lower().startswith("lenovo") and version else f"{vendor} {product}"
    serial = _read(dmi / "product_serial")  # root only
    return {
        "make_model": model.strip() or "Unknown",
        "vendor": vendor,
        "product": product,
        "serial": serial if serial and "o.e.m" not in serial.lower() and "default" not in serial.lower() else "",
        "bios_date": _read(dmi / "bios_date"),
        "chassis_type": _read(dmi / "chassis_type"),
        "uefi": (sys_root / "firmware/efi").exists(),
    }


def cpu_info(cpuinfo_text: str | None = None) -> dict:
    text = cpuinfo_text if cpuinfo_text is not None else _read(PROC / "cpuinfo")
    model = ""
    flags = ""
    cores = 0
    for line in text.splitlines():
        if line.startswith("model name") and not model:
            model = line.split(":", 1)[1].strip()
        elif line.startswith("flags") and not flags:
            flags = line.split(":", 1)[1]
        elif line.startswith("processor"):
            cores += 1
    model = re.sub(r"\s+", " ", re.sub(r"\((R|TM)\)|CPU ", "", model)).strip()
    return {"model": model or platform.processor() or "Unknown", "threads": cores or os.cpu_count() or 0,
            "is_64bit": " lm " in f" {flags} " or platform.machine() in ("x86_64", "aarch64")}


def ram_gb(meminfo_text: str | None = None) -> float:
    text = meminfo_text if meminfo_text is not None else _read(PROC / "meminfo")
    m = re.search(r"MemTotal:\s+(\d+) kB", text)
    if not m:
        return 0.0
    # MemTotal excludes firmware-reserved memory; round to the nearest 0.5 GB of installed RAM.
    return round(int(m.group(1)) / 1024 / 1024 * 2 + 0.4) / 2


def disks(lsblk_json: str | None = None) -> list[dict]:
    raw = lsblk_json if lsblk_json is not None else _run(
        ["lsblk", "-J", "-b", "-o", "NAME,TYPE,SIZE,ROTA,TRAN,MODEL,FSTYPE,LABEL,RM"]
    )
    try:
        devices = json.loads(raw or "{}").get("blockdevices", [])
    except ValueError:
        return []
    out = []
    for d in devices:
        if d.get("type") != "disk" or str(d.get("rm")) in ("1", "True", "true"):
            continue  # skip USB sticks and card readers (removable)
        if d.get("name", "").startswith(("loop", "zram", "sr")) or not int(d.get("size") or 0):
            continue
        if (d.get("tran") or "").lower() == "usb":
            continue  # the live USB itself, or an external drive
        parts = d.get("children") or []
        fstypes = sorted({p.get("fstype") for p in parts if p.get("fstype")})
        labels = [p.get("label") for p in parts if p.get("label")]
        size_gb = round(int(d.get("size") or 0) / 1e9)
        rota = str(d.get("rota")) in ("1", "True", "true")
        tran = (d.get("tran") or "").lower()
        kind = "NVMe SSD" if tran == "nvme" or d.get("name", "").startswith("nvme") else ("HDD" if rota else "SSD")
        existing = "Windows" if "ntfs" in fstypes else ("Linux" if {"ext4", "btrfs", "xfs"} & set(fstypes) else ("empty" if not parts else "other"))
        out.append({
            "name": d.get("name"), "model": (d.get("model") or "").strip(), "size_gb": size_gb, "kind": kind,
            "filesystems": fstypes, "labels": labels, "existing_os": existing, "health": smart_health(d.get("name")),
        })
    return out


def smart_health(name: str | None, smartctl_out: str | None = None) -> str:
    if smartctl_out is None:
        if not name or os.geteuid() != 0:
            return "not checked (run with sudo)" if name else ""
        smartctl_out = _run(["smartctl", "-H", "-A", f"/dev/{name}"])
        if not smartctl_out:
            return "not checked (smartctl not installed)"
    if re.search(r"(PASSED|: OK)\b", smartctl_out):
        realloc = re.search(r"Reallocated_Sector_Ct.*\s(\d+)\s*$", smartctl_out, re.M)
        if realloc and int(realloc.group(1)) > 0:
            return f"passed, but {realloc.group(1)} reallocated sectors (replace soon)"
        return "passed"
    if "FAILED" in smartctl_out:
        return "FAILING (replace before installing)"
    return "unknown"


def battery(sys_root: Path = SYS) -> dict | None:
    for bat in sorted((sys_root / "class/power_supply").glob("BAT*")):
        full = _read(bat / "energy_full") or _read(bat / "charge_full")
        design = _read(bat / "energy_full_design") or _read(bat / "charge_full_design")
        health = round(int(full) * 100 / int(design)) if full.isdigit() and design.isdigit() and int(design) else None
        return {"health_percent": health, "cycles": _read(bat / "cycle_count") or None, "status": _read(bat / "status")}
    return None


def pci_devices(lspci_text: str | None = None) -> dict:
    text = lspci_text if lspci_text is not None else _run(["lspci"])
    gpu, wifi, eth = [], [], []
    for line in text.splitlines():
        desc = line.split(": ", 1)[-1]
        low = line.lower()
        if "vga compatible" in low or "3d controller" in low or "display controller" in low:
            gpu.append(desc)
        elif "network controller" in low or "wireless" in low:
            wifi.append(desc)
        elif "ethernet controller" in low:
            eth.append(desc)
    return {"graphics": gpu, "wifi": wifi, "ethernet": eth}


# Chipsets that commonly need extra steps on Linux Mint. Advice only; always test on the day.
WATCH_LIST = [
    (r"broadcom.*bcm43", "Broadcom Wi-Fi: usually needs the bcmwl-kernel-source driver (Driver Manager, needs a cable or tethered phone first)."),
    (r"realtek.*rtl8821ce|rtl8821ce", "Realtek RTL8821CE Wi-Fi: may need the rtl8821ce-dkms driver."),
    (r"nvidia", "NVIDIA graphics: install the recommended driver from Driver Manager after first boot."),
]


def verdict(inv: dict) -> dict:
    reasons, notes = [], []
    status = "good"
    if not inv["cpu"]["is_64bit"]:
        return {"status": "not suitable", "reasons": ["32-bit CPU: current Linux Mint needs a 64-bit processor."], "notes": []}
    if inv["ram_gb"] < MIN_RAM_GB:
        status = "not suitable"
        reasons.append(f"Only {inv['ram_gb']} GB RAM; Mint needs at least {MIN_RAM_GB} GB.")
    elif inv["ram_gb"] < GOOD_RAM_GB:
        status = "works with upgrade"
        reasons.append(f"{inv['ram_gb']} GB RAM will be slow; {GOOD_RAM_GB} GB or more recommended.")
    main = max(inv["disks"], key=lambda d: d["size_gb"], default=None)
    if main is None:
        status = "not suitable" if status != "not suitable" else status
        reasons.append("No internal disk found.")
    else:
        if main["size_gb"] < MIN_DISK_GB:
            status = "not suitable"
            reasons.append(f"Disk is only {main['size_gb']} GB; at least {MIN_DISK_GB} GB needed.")
        if main["kind"] == "HDD":
            if status == "good":
                status = "works with upgrade"
            reasons.append("Spinning hard disk: an SSD will make the biggest speed difference.")
        if "FAILING" in main["health"] or "replace" in main["health"]:
            status = "works with upgrade" if status == "good" else status
            reasons.append(f"Disk health: {main['health']}.")
        if main["existing_os"] == "Windows":
            notes.append("Windows is on the disk: confirm the customer's files are backed up before installing.")
    bat = inv.get("battery")
    if bat and bat.get("health_percent") is not None and bat["health_percent"] < 60:
        notes.append(f"Battery holds {bat['health_percent']}% of its original charge; suggest a replacement.")
    pci_text = " ".join(sum(inv["pci"].values(), [])).lower()
    for pattern, advice in WATCH_LIST:
        if re.search(pattern, pci_text):
            notes.append(advice)
    if not inv["system"]["uefi"]:
        notes.append("Booted in legacy BIOS mode: install in the same mode, or switch to UEFI first if the machine supports it.")
    if not reasons:
        reasons.append("Meets the recommended specification for Linux Mint.")
    return {"status": status, "reasons": reasons, "notes": notes}


def collect() -> dict:
    inv = {
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "kit_version": __import__("revival").VERSION,
        "system": system_info(),
        "cpu": cpu_info(),
        "ram_gb": ram_gb(),
        "disks": disks(),
        "battery": battery(),
        "pci": pci_devices(),
        "ran_as_root": os.geteuid() == 0,
    }
    inv["verdict"] = verdict(inv)
    return inv


def to_text(inv: dict) -> str:
    s, c, v = inv["system"], inv["cpu"], inv["verdict"]
    lines = [
        f"Machine:   {s['make_model']}" + (f"  (serial {s['serial']})" if s["serial"] else ""),
        f"CPU:       {c['model']}, {c['threads']} threads, {'64-bit' if c['is_64bit'] else '32-bit'}",
        f"RAM:       {inv['ram_gb']} GB",
    ]
    for d in inv["disks"]:
        lines.append(f"Disk:      {d['name']} {d['size_gb']} GB {d['kind']} {d['model']} | has: {d['existing_os']} | health: {d['health']}")
    if inv["battery"]:
        b = inv["battery"]
        lines.append(f"Battery:   {b['health_percent']}% of design capacity" if b["health_percent"] is not None else "Battery:   present")
    for k in ("graphics", "wifi", "ethernet"):
        for dev in inv["pci"][k]:
            lines.append(f"{k.capitalize() + ':':10} {dev}")
    lines.append(f"Firmware:  {'UEFI' if s['uefi'] else 'Legacy BIOS'}")
    lines.append("")
    lines.append(f"VERDICT:   {v['status'].upper()}")
    lines += [f"  - {r}" for r in v["reasons"]]
    if v["notes"]:
        lines.append("Notes:")
        lines += [f"  - {n}" for n in v["notes"]]
    if not inv["ran_as_root"]:
        lines.append("\n(Run with sudo to include the serial number and disk health.)")
    return "\n".join(lines)


def to_jobbook(inv: dict) -> dict:
    """Fields matching the job book's Machine record."""
    main = max(inv["disks"], key=lambda d: d["size_gb"], default=None)
    return {
        "make_model": inv["system"]["make_model"],
        "serial": inv["system"]["serial"],
        "cpu": inv["cpu"]["model"],
        "ram_gb": int(round(inv["ram_gb"])),
        "disk": f"{main['size_gb']} GB {main['kind']}" if main else "",
        "disk_health": main["health"] if main else "",
        "original_os": main["existing_os"] if main and main["existing_os"] not in ("empty", "other") else "",
        "notes": "Revival kit: " + inv["verdict"]["status"] + ". " + " ".join(inv["verdict"]["reasons"] + inv["verdict"]["notes"]),
    }
