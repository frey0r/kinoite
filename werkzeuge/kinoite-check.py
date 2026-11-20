#!/usr/bin/env python3
"""Wöchentlicher Check für das Kinoite-Image ghcr.io/frey0r/kinoite.

Warnt per KDE-Benachrichtigung, wenn
  - das neueste Image älter ist als --max-image-tage (die täglichen Builds scheitern),
  - der letzte Commit auf main älter ist als --max-commit-tage (GitHub schaltet geplante
    Builds nach 60 Tagen ohne Aktivität im Repo ab),
  - Dependabot-Pull-Requests offen sind,
  - das neueste Deployment auf dem Rechner älter ist als --max-deployment-tage
    (Updates kommen nicht an).

Ohne Fund bleibt der Check still. Alles Weitere steht im Journal:
journalctl --user -u kinoite-check
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = "frey0r/kinoite"
IMAGE = "docker://ghcr.io/frey0r/kinoite:latest"
ACTIONS_URL = f"https://github.com/{REPO}/actions"
PULLS_URL = f"https://github.com/{REPO}/pulls"
VERSUCHE = 3          # Netz nach dem Login eventuell noch nicht da
PAUSE_S = 60


class Fund:
    def __init__(self, titel, detail, url):
        self.titel, self.detail, self.url = titel, detail, url


def zeitpunkt(text):
    """ISO 8601 aus GitHub, skopeo oder rpm-ostree als aware datetime (Nanosekunden gekürzt)."""
    text = re.sub(r"(\.\d{6})\d+", r"\1", text.replace("Z", "+00:00"))
    return dt.datetime.fromisoformat(text)


def alter_tage(zeit):
    return (dt.datetime.now(dt.timezone.utc) - zeit).total_seconds() / 86400


def mit_wiederholung(funktion):
    letzter = None
    for versuch in range(VERSUCHE):
        try:
            return funktion()
        except (urllib.error.URLError, subprocess.CalledProcessError, TimeoutError, OSError) as fehler:
            letzter = fehler
            if versuch < VERSUCHE - 1:
                time.sleep(PAUSE_S)
    raise letzter


def github(pfad):
    anfrage = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{pfad}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "kinoite-check"})
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:
        return json.load(antwort)


def pruefe_image(max_tage):
    def lesen():
        r = subprocess.run(["skopeo", "inspect", "--no-creds", IMAGE],
                           capture_output=True, text=True, timeout=120, check=True)
        return json.loads(r.stdout)
    daten = mit_wiederholung(lesen)
    alter = alter_tage(zeitpunkt(daten["Created"]))
    version = daten["Labels"].get("org.opencontainers.image.version", "?")
    print(f"Image: gebaut vor {alter:.1f} Tagen, Fedora-Basis {version}")
    if alter > max_tage:
        return Fund(f"Kein neues Image seit {alter:.0f} Tagen",
                    "Die täglichen Builds scheitern vermutlich. Log unter Actions lesen.", ACTIONS_URL)
    return None


def pruefe_commit(max_tage):
    daten = mit_wiederholung(lambda: github("commits/main"))
    alter = alter_tage(zeitpunkt(daten["commit"]["committer"]["date"]))
    print(f"Repo: letzter Commit auf main vor {alter:.1f} Tagen")
    if alter > max_tage:
        return Fund(f"Letzter Commit vor {alter:.0f} Tagen",
                    "Nach 60 Tagen ohne Aktivität schaltet GitHub den Nacht-Build ab. "
                    "Einen Dependabot-PR mergen oder committen.", ACTIONS_URL)
    return None


def pruefe_dependabot():
    pulls = mit_wiederholung(lambda: github("pulls?state=open&per_page=50"))
    offen = [p for p in pulls if p["user"]["login"] == "dependabot[bot]"]
    print(f"Dependabot: {len(offen)} offene Pull Requests")
    if offen:
        titel = "; ".join(p["title"] for p in offen[:3])
        return Fund(f"{len(offen)} Dependabot-PR offen",
                    f"Mergen, wenn der PR-Build grün ist: {titel}", PULLS_URL)
    return None


def pruefe_deployment(max_tage):
    r = subprocess.run(["rpm-ostree", "status", "--json"],
                       capture_output=True, text=True, timeout=120, check=True)
    deployments = json.loads(r.stdout)["deployments"]
    neuestes = max(deployments, key=lambda d: d["timestamp"])
    alter = alter_tage(dt.datetime.fromtimestamp(neuestes["timestamp"], dt.timezone.utc))
    zustand = "gestaged" if neuestes.get("staged") else ("gebootet" if neuestes.get("booted") else "vorhanden")
    print(f"Rechner: neuestes Deployment {neuestes.get('version', '?')} ({zustand}) von vor {alter:.1f} Tagen")
    if alter > max_tage:
        return Fund(f"Kein System-Update seit {alter:.0f} Tagen",
                    "Discover installiert keine Updates. `rpm-ostree upgrade --check` prüfen.", ACTIONS_URL)
    return None


def melden(funde):
    # Nach dem Login (Persistent=true holt einen verpassten Lauf nach) fehlt der Dienst eventuell noch
    subprocess.run(["gdbus", "wait", "--session", "--timeout", "180", "org.freedesktop.Notifications"],
                   capture_output=True, timeout=200)
    titel = f"Kinoite-Image: {len(funde)} {'Fund' if len(funde) == 1 else 'Funde'} beim Check"
    text = "\n".join(f"• {f.titel}" for f in funde)
    try:
        r = subprocess.run(["notify-send", "--app-name=Kinoite-Image", "--icon=system-software-update",
                            "--action=oeffnen=Auf GitHub öffnen", titel, text],
                           capture_output=True, text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        return
    if r.stdout.strip() == "oeffnen":
        # Eigener Scope: systemd beendet beim Ende des Oneshot-Dienstes alles in dessen cgroup
        try:
            subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "--collect", "--",
                            "xdg-open", funde[0].url],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            pass


def main():
    sys.stdout.reconfigure(line_buffering=True)  # Zeilen sofort ins Journal, auch während notify-send wartet
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--max-image-tage", type=float, default=3)
    p.add_argument("--max-commit-tage", type=float, default=45)
    p.add_argument("--max-deployment-tage", type=float, default=14)
    p.add_argument("--keine-meldung", action="store_true", help="nur ausgeben, keine Benachrichtigung")
    a = p.parse_args()

    pruefungen = [
        ("Image", lambda: pruefe_image(a.max_image_tage)),
        ("Repo", lambda: pruefe_commit(a.max_commit_tage)),
        ("Dependabot", pruefe_dependabot),
        ("Rechner", lambda: pruefe_deployment(a.max_deployment_tage)),
    ]
    funde = []
    for name, pruefung in pruefungen:
        try:
            fund = pruefung()
        except Exception as fehler:  # ein stiller Ausfall wäre schlimmer als eine Meldung
            fund = Fund(f"{name}: nicht prüfbar", str(fehler), ACTIONS_URL)
            print(f"{name}: nicht prüfbar: {fehler}", file=sys.stderr)
        if fund:
            funde.append(fund)
            print(f"FUND: {fund.titel}. {fund.detail}")

    if not funde:
        print("Keine Funde.")
    elif not a.keine_meldung:
        melden(funde)


if __name__ == "__main__":
    main()
