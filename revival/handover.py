"""Printable handover sheet for the customer, in plain English."""

import html
from datetime import date

E = html.escape

CSS = """
body { font:15px/1.55 Manrope, 'Segoe UI', system-ui, sans-serif; color:#1a1814; max-width:760px; margin:28px auto; padding:0 20px; }
h1, h2 { font-family:Fraunces, Georgia, serif; color:#2d4a3e; font-weight:600; }
h1 { margin:0 0 4px; } h2 { margin:22px 0 6px; font-size:19px; border-bottom:2px solid #c9bfa8; padding-bottom:3px; }
.sub { color:#5b5547; margin:0 0 18px; }
table { border-collapse:collapse; width:100%; } td { padding:4px 8px 4px 0; vertical-align:top; } td:first-child { color:#5b5547; width:190px; }
.box { border:1px solid #c9bfa8; border-radius:8px; padding:10px 14px; background:#fbf7ef; }
.write { display:inline-block; min-width:220px; border-bottom:1px solid #999; }
li { margin:4px 0; }
footer { margin-top:28px; color:#5b5547; font-size:13px; }
@media print { body { margin:0 auto; } }
"""


def render(inv: dict, customer: str, username: str = "", linux: str = "Linux Mint 22 Cinnamon",
           extras: list[str] | None = None, contact: str = "hello@seconwind.com · seconwind.co.uk",
           when: date | None = None) -> str:
    when = when or date.today()
    s, c = inv["system"], inv["cpu"]
    main = max(inv["disks"], key=lambda d: d["size_gb"], default=None)
    disk = f"{main['size_gb']} GB {main['kind']}" if main else ""
    user_row = f"<tr><td>Your username</td><td>{E(username)}</td></tr>" if username else ""
    extra_items = "".join(f"<li>{E(x)}</li>" for x in (extras or []))
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Your computer: handover sheet</title><style>{CSS}</style></head><body>
<h1>Your computer has a second wind</h1>
<p class="sub">Prepared for {E(customer)} on {when.strftime('%d %B %Y')} by Seconwind</p>

<h2>Your computer</h2>
<table>
<tr><td>Computer</td><td>{E(s['make_model'])}</td></tr>
{"<tr><td>Serial number</td><td>" + E(s['serial']) + "</td></tr>" if s.get('serial') else ""}
<tr><td>Processor</td><td>{E(c['model'])}</td></tr>
<tr><td>Memory</td><td>{E(str(inv['ram_gb']))} GB</td></tr>
<tr><td>Storage</td><td>{E(disk)}</td></tr>
<tr><td>System</td><td>{E(linux)}</td></tr>
{user_row}
</table>

<h2>Your password</h2>
<div class="box">Write your password somewhere safe that only you can find (not on this sheet if it stays with the computer).
Seconwind does not keep a copy. If you forget it, we can help you reset it.</div>

<h2>What we set up</h2>
<ul>
<li>{E(linux)}, fully updated.</li>
<li>Automatic updates, so you don't have to remember them.</li>
<li>The firewall, switched on.</li>
<li>Firefox for the web, LibreOffice for documents and spreadsheets, and a media player for music and video.</li>
{extra_items}
</ul>

<h2>Everyday tips</h2>
<ul>
<li><strong>Updates:</strong> updates install themselves in the background. If a shield icon near the clock shows a dot, you can click it to install them straight away.</li>
<li><strong>Finding programs:</strong> click the menu button in the bottom-left corner and start typing what you want, for example "email" or "photos".</li>
<li><strong>Your files</strong> are in the Home folder (Documents, Pictures, Music, Downloads).</li>
<li><strong>Turning off:</strong> menu button, then the power icon. Please don't just hold the power button.</li>
<li><strong>Backups:</strong> keep copies of photos and important documents on a USB drive or a cloud service. Ask us if you'd like this set up.</li>
</ul>

<h2>Staying safe</h2>
<ul>
<li>Nobody genuine will phone you about a "virus on your computer". Hang up, and never let a caller onto your computer.</li>
<li>Only type your password when you started the action yourself, such as installing an update.</li>
<li>If an email or message rushes you to click or pay, stop and check with someone first.</li>
</ul>

<h2>Getting help</h2>
<div class="box">Seconwind: {E(contact)}<br>
Please mention your computer ({E(s['make_model'])}) when you get in touch.</div>

<footer>Handed over by <span class="write">&nbsp;</span> &nbsp; Customer <span class="write">&nbsp;</span></footer>
</body></html>
"""
