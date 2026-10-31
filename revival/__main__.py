"""Command line: python3 -m revival {inventory,handover}."""

import argparse
import json
import sys
from pathlib import Path

from . import handover, inventory


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="revival")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inventory", help="check this machine (read-only) and save a report")
    i.add_argument("--out", help="save the full inventory as JSON here (e.g. on the kit USB)")
    i.add_argument("--jobbook", help="also save a job book machine record (JSON) here")
    h = sub.add_parser("handover", help="make the customer's printable handover sheet")
    h.add_argument("--inventory", required=True, help="inventory JSON saved earlier")
    h.add_argument("--customer", required=True)
    h.add_argument("--username", default="")
    h.add_argument("--linux", default="Linux Mint 22 Cinnamon")
    h.add_argument("--extra", action="append", default=[], help="extra line for 'What we set up' (repeatable)")
    h.add_argument("--out", default="handover.html")
    args = p.parse_args(argv)

    if args.cmd == "inventory":
        inv = inventory.collect()
        print(inventory.to_text(inv))
        if args.out:
            Path(args.out).write_text(json.dumps(inv, indent=2))
            print(f"\nSaved {args.out}")
        if args.jobbook:
            Path(args.jobbook).write_text(json.dumps(inventory.to_jobbook(inv), indent=2))
            print(f"Saved {args.jobbook} (import it in the job book)")
        return 0 if inv["verdict"]["status"] != "not suitable" else 2

    if args.cmd == "handover":
        inv = json.loads(Path(args.inventory).read_text())
        Path(args.out).write_text(handover.render(inv, args.customer, args.username, args.linux, args.extra))
        print(f"Saved {args.out}: open it in Firefox and print (Ctrl+P)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
