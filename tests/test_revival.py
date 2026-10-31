import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from revival import handover, inventory as inv

CPUINFO = """processor\t: 0
model name\t: Intel(R) Core(TM) i5-5300U CPU @ 2.30GHz
flags\t\t: fpu vme lm sse2
processor\t: 1
model name\t: Intel(R) Core(TM) i5-5300U CPU @ 2.30GHz
"""
LSBLK = json.dumps({"blockdevices": [
    {"name": "sda", "type": "disk", "size": 500107862016, "rota": True, "tran": "sata", "model": "ST500LM021", "rm": False,
     "children": [{"name": "sda1", "fstype": "vfat"}, {"name": "sda3", "fstype": "ntfs", "label": "Windows"}]},
    {"name": "sdb", "type": "disk", "size": 16008609792, "rota": False, "tran": "usb", "model": "Cruzer", "rm": True},
    {"name": "loop0", "type": "loop", "size": 1000},
    {"name": "nvme0n1", "type": "disk", "size": 0, "rota": False, "tran": "nvme"},
]})
LSPCI = """00:02.0 VGA compatible controller: Intel Corporation HD Graphics 5500 (rev 09)
02:00.0 Network controller: Broadcom Inc. and subsidiaries BCM4352 802.11ac Wireless Network Adapter (rev 03)
00:19.0 Ethernet controller: Intel Corporation Ethernet Connection (3) I218-LM (rev 03)
"""


def make_inv(ram=8.0, disks=None, is64=True, uefi=True, battery=None):
    return {"system": {"make_model": "Dell Latitude E7450", "serial": "ABC123", "uefi": uefi},
            "cpu": {"model": "Intel Core i5-5300U @ 2.30GHz", "threads": 4, "is_64bit": is64}, "ram_gb": ram,
            "disks": disks if disks is not None else [{"name": "sda", "size_gb": 240, "kind": "SSD", "model": "", "existing_os": "Windows", "health": "passed"}],
            "battery": battery, "pci": {"graphics": [], "wifi": [], "ethernet": []}}


class ParserTests(unittest.TestCase):
    def test_cpu(self):
        c = inv.cpu_info(CPUINFO)
        self.assertEqual(c["model"], "Intel Core i5-5300U @ 2.30GHz")
        self.assertEqual(c["threads"], 2)
        self.assertTrue(c["is_64bit"])
        self.assertFalse(inv.cpu_info("processor : 0\nflags : fpu vme\n")["is_64bit"] and False)

    def test_ram_rounding(self):
        self.assertEqual(inv.ram_gb("MemTotal:        7895540 kB\n"), 7.5)
        self.assertEqual(inv.ram_gb("MemTotal:        8040000 kB\n"), 8.0)
        self.assertEqual(inv.ram_gb(""), 0.0)

    def test_disks_skip_usb_loop_and_empty(self):
        d = inv.disks(LSBLK)
        self.assertEqual([x["name"] for x in d], ["sda"])
        self.assertEqual((d[0]["kind"], d[0]["size_gb"], d[0]["existing_os"]), ("HDD", 500, "Windows"))

    def test_smart(self):
        self.assertEqual(inv.smart_health("sda", "SMART overall-health self-assessment test result: PASSED\n"), "passed")
        out = "test result: PASSED\n  5 Reallocated_Sector_Ct   0x0033   100   100   036    Pre-fail  Always       -       24\n"
        self.assertIn("24 reallocated", inv.smart_health("sda", out))
        self.assertIn("FAILING", inv.smart_health("sda", "test result: FAILED!\n"))

    def test_pci(self):
        p = inv.pci_devices(LSPCI)
        self.assertEqual(len(p["graphics"]), 1)
        self.assertIn("BCM4352", p["wifi"][0])

    def test_dmi_and_battery(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dmi = root / "class/dmi/id"
            dmi.mkdir(parents=True)
            (dmi / "sys_vendor").write_text("LENOVO\n")
            (dmi / "product_name").write_text("20AN006VUK\n")
            (dmi / "product_version").write_text("ThinkPad T440p\n")
            (dmi / "product_serial").write_text("To be filled by O.E.M.\n")
            bat = root / "class/power_supply/BAT0"
            bat.mkdir(parents=True)
            (bat / "energy_full").write_text("23000000")
            (bat / "energy_full_design").write_text("46000000")
            s = inv.system_info(root)
            self.assertEqual(s["make_model"], "LENOVO ThinkPad T440p")
            self.assertEqual(s["serial"], "")
            self.assertFalse(s["uefi"])
            self.assertEqual(inv.battery(root)["health_percent"], 50)


class VerdictTests(unittest.TestCase):
    def test_good(self):
        v = inv.verdict(make_inv())
        self.assertEqual(v["status"], "good")
        self.assertTrue(any("backed up" in n for n in v["notes"]))

    def test_upgrade_for_low_ram_and_hdd(self):
        v = inv.verdict(make_inv(ram=3, disks=[{"name": "sda", "size_gb": 320, "kind": "HDD", "existing_os": "empty", "health": "passed"}]))
        self.assertEqual(v["status"], "works with upgrade")
        self.assertEqual(len(v["reasons"]), 2)

    def test_not_suitable(self):
        self.assertEqual(inv.verdict(make_inv(is64=False))["status"], "not suitable")
        self.assertEqual(inv.verdict(make_inv(ram=1))["status"], "not suitable")
        self.assertEqual(inv.verdict(make_inv(disks=[]))["status"], "not suitable")

    def test_notes(self):
        i = make_inv(uefi=False, battery={"health_percent": 41})
        i["pci"]["wifi"] = ["Broadcom Inc. BCM4352 802.11ac"]
        notes = " ".join(inv.verdict(i)["notes"])
        for word in ("Broadcom", "41%", "legacy BIOS"):
            self.assertIn(word, notes)

    def test_jobbook_record(self):
        rec = inv.to_jobbook({**make_inv(), "verdict": inv.verdict(make_inv())})
        self.assertEqual(rec["disk"], "240 GB SSD")
        self.assertEqual(rec["original_os"], "Windows")
        self.assertEqual(rec["ram_gb"], 8)


class HandoverTests(unittest.TestCase):
    def test_render_escapes_and_includes(self):
        page = handover.render(make_inv(), "<Mrs> O'Neil", "oneil", extras=["Printer: HP <Deskjet>"], when=date(2026, 11, 4))
        self.assertIn("&lt;Mrs&gt;", page)
        self.assertNotIn("<Mrs>", page)
        self.assertIn("04 November 2026", page)
        self.assertIn("HP &lt;Deskjet&gt;", page)
        self.assertIn("Dell Latitude E7450", page)


if __name__ == "__main__":
    unittest.main()
