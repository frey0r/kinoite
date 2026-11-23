# Kinoite-Image

Stand: 2026-11-20

Dieses Repo baut ein eigenes Fedora-Kinoite-Image mit BlueBuild auf GitHub Actions. Es ergänzt das offizielle Kinoite um Codecs und Hardware-Werkzeuge für einen AMD-Desktop. Das README ist eine Notiz für den eigenen Gebrauch und beschreibt Inhalt, Umstieg, Updates und Rückweg.

## Inhalt des Images

Die Basis ist das Image `quay.io/fedora/fedora-kinoite` in der Version aus dem Schlüssel `image-version` im Rezept, nicht Universal Blue: ublue entfernt Discovers rpm-ostree-Backend und fedora-third-party. Discover mit automatischen Updates, Flathub und fedora-third-party bleiben wie im offiziellen Kinoite.

Die folgende Tabelle zeigt, was das Rezept `recipes/recipe.yml` gegenüber dem offiziellen Kinoite ändert:

| Änderung | Pakete oder Dateien | Herkunft |
|---|---|---|
| Volle Codecs | `ffmpeg` statt `ffmpeg-free`, `mesa-va-drivers-freeworld` (HEVC und H.264 per VA-API) | RPM Fusion free |
| Lüftersteuerung | `coolercontrol`, Dienst `coolercontrold` | COPR `codifryed/CoolerControl` |
| GPU-Undervolt und Powerlimit | `lact`, Dienst `lactd` | COPR `ilyaz/LACT` |
| Werkzeuge | `cava`, `fastfetch`, `steam-devices` | Fedora |
| Kernelmodule beim Start | `ntsync`, `nct6775` in `/usr/lib/modules-load.d` | dieses Repo |
| udev-Regeln | Tinker 75 (QMK), 8BitDo, `energy_uj` lesbar für MangoHud, in `/usr/lib/udev/rules.d` | dieses Repo |
| Entfernt | `firefox`, `firefox-langpacks` | – |

RPM Fusion und die COPRs sind nur während des Builds aktiv. Das Modul `dnf` entfernt sie am Ende wieder (`cleanup: true`).

Lokal auf dem Rechner bleiben die Kernelparameter, alle Flatpaks, die Konfigurationen in den Ordnern `/etc/lact` und `/etc/coolercontrol`, die Datei `/etc/hosts` und alles im Home-Verzeichnis.

## Auf das Image umsteigen

Für den Umstieg gelten diese Voraussetzungen:

- Der letzte Build in *Actions* ist grün, und das Paket `kinoite` unter *Packages* ist auf **Public** gestellt.
- Der Rechner läuft auf derselben Fedora-Version wie `image-version`.
- Das gebootete Deployment ist gepinnt (`sudo ostree admin pin 0`) und dient als Rückweg.
- Die Zwei-Faktor-Anmeldung für das GitHub-Konto ist aktiv. Wer das Konto übernimmt, kann sonst ein signiertes Image mit beliebigem Inhalt veröffentlichen, und der Rechner installiert es.
- Der wöchentliche Check ist eingerichtet, siehe [Wöchentlicher Check](#wöchentlicher-check).

So wird umgestiegen:

1. Auf das unsignierte Image wechseln und die gelayerten Pakete dabei entfernen:
   ```sh
   rpm-ostree rebase ostree-unverified-registry:ghcr.io/frey0r/kinoite:latest --uninstall=cava --uninstall=coolercontrol --uninstall=fastfetch --uninstall=steam-devices
   ```
2. Neu starten.
3. Die lokalen Kopien im Ordner `/etc` löschen, die das Image ersetzt: die Dateien `/etc/modules-load.d/ntsync.conf` und `/etc/modules-load.d/nct6775.conf`, die drei Regeln im Ordner `/etc/udev/rules.d`, die Datei `/etc/systemd/system/lactd.service` und die CoolerControl-Datei im Ordner `/etc/yum.repos.d`.
4. Den Befehl `sudo systemctl daemon-reload` ausführen.
5. Den Befehl `sudo systemctl enable --now lactd` ausführen.
6. Auf das signierte Image wechseln:
   ```sh
   rpm-ostree rebase ostree-image-signed:docker://ghcr.io/frey0r/kinoite:latest
   ```
7. Neu starten.

Ergebnis: Der Befehl `rpm-ostree status` zeigt als Origin `ostree-image-signed:docker://ghcr.io/frey0r/kinoite:latest` und keine Zeile `LayeredPackages`.

Der Wechsel auf das unsignierte Image läuft ohne Signaturprüfung, weil die Signaturregel und der öffentliche Schlüssel erst mit dem Image auf den Rechner kommen. Erst der Wechsel auf das signierte Image prüft die Signatur.

## Updates

GitHub Actions baut das Image jeden Tag um 06:00 UTC neu, dazu bei jedem Push und manuell über *Actions → bluebuild → Run workflow*. Discover installiert Updates einmal pro Woche automatisch.

Discover erkennt ein Update am Label `org.opencontainers.image.version`, und dieses Label erbt das Image vom Fedora-Basisimage. Eine reine Rezeptänderung zeigt Discover deshalb erst mit dem nächsten Fedora-Basisupdate an. Sofort holt sie der Befehl `rpm-ostree upgrade`.

Nach jedem Build teilt chunkah das Image nach Paketen in Layer auf, höchstens 128. Eingeschaltet ist das Rechunking mit der Einstellung `chunkah: true` im Workflow. Große Pakete bekommen einen eigenen Layer, kleine teilen sich einen. Ein Update lädt dadurch die Layer geänderter Pakete und die RPM-Datenbank, alle anderen Layer bleiben auf dem Rechner. Das fertige Image enthält keinen OSTree-Commit mehr, rpm-ostree importiert es trotzdem. Das Versionslabel bleibt erhalten.

Die folgende Tabelle zeigt die Downloadgrößen mit und ohne chunkah, ermittelt am 2026-11-20:

| Fall | ohne chunkah | mit chunkah |
|---|---|---|
| Neubau ohne Paketänderung, gemessen | 264 MB | 92 MB |
| F45-Updates vom 2026-11-13 bis 2026-11-20, hochgerechnet | 2,1 GB | 1,3 GB |
| Ganzes Image beim Umstieg | 3,58 GB | 3,26 GB |

> [!NOTE]
> Wenn sich die Aufteilung ändert, lädt das nächste Update mehr. Beim Abschalten von chunkah oder bei einer anderen Layer-Zahl ist es das ganze Image. BlueBuild verwendet chunkah ohne feste Version, deshalb kann auch eine geänderte chunkah-Version ein einzelnes Update vergrößern.

Die BlueBuild-Action ist per Commit-SHA eingebunden und nicht per Tag. Tags lassen sich verschieben, und die Action hat Zugriff auf den Signaturschlüssel. Die BlueBuild-CLI (`v0.9`) und chunkah (`latest`) holt die Action weiter ohne feste Version.

Dependabot schlägt höhere Versionen der Action jeden Samstag als Pull Request vor. Diese Pull Requests mergen, sobald der PR-Build grün ist. So folgt die Action den Releases von BlueBuild, und jeder Merge zählt als Aktivität: GitHub schaltet geplante Builds nach 60 Tagen ohne Aktivität im Repo ab.

## Wöchentlicher Check

Der Check `werkzeuge/kinoite-check.py` läuft jeden Sonntag um 11:30 Uhr Ortszeit. War der Rechner zu der Zeit aus, läuft er beim nächsten Start nach. Er meldet sich per KDE-Benachrichtigung, und zwar nur, wenn er etwas findet. Ein Klick auf die Benachrichtigung öffnet die passende Seite auf GitHub.

Die folgende Tabelle zeigt, was der Check prüft:

| Prüfung | Schwelle | Bedeutung |
|---|---|---|
| Alter des Images unter `:latest` | 3 Tage | Die täglichen Builds scheitern. |
| Alter des letzten Commits auf `main` | 45 Tage | GitHub schaltet den Nacht-Build nach 60 Tagen ab. |
| Offene Dependabot-Pull-Requests | 1 | Ein Update der Action wartet aufs Mergen. |
| Alter des jüngsten Deployments auf dem Rechner | 14 Tage | Updates kommen nicht an. |

Sind GitHub oder die Registry nach 3 Versuchen im Abstand von 1 Minute nicht erreichbar, meldet der Check das ebenfalls.

So wird der Check eingerichtet:

```sh
systemctl --user link ~/Projekte/Computer/Kinoite/werkzeuge/kinoite-check.service ~/Projekte/Computer/Kinoite/werkzeuge/kinoite-check.timer
systemctl --user enable --now kinoite-check.timer
```

Ergebnis: Der Befehl `systemctl --user list-timers` zeigt den Timer `kinoite-check.timer`.

Von Hand läuft der Check ohne Benachrichtigung mit diesem Befehl:

```sh
~/Projekte/Computer/Kinoite/werkzeuge/kinoite-check.py --keine-meldung
```

Die Schwellen lassen sich mit den Optionen `--max-image-tage`, `--max-commit-tage` und `--max-deployment-tage` ändern. Mit der Option `--max-image-tage 0` erscheint zum Testen immer eine Benachrichtigung. Der Befehl `journalctl --user -u kinoite-check` zeigt das Protokoll.

## Wenn ein Build scheitert

Ein gescheiterter Build veröffentlicht nichts. Das zuletzt gebaute Image bleibt unter dem Tag `:latest`, und der Rechner bleibt auf seinem Stand. Der wöchentliche Check meldet es, sobald das Image unter dem Tag `:latest` älter als 3 Tage ist.

Die häufigste Ursache ist das Paket `mesa-va-drivers-freeworld`. Das Paket muss exakt zur Mesa-Version von Fedora passen, und RPM Fusion zieht eine höhere Mesa-Version oft erst einige Tage später nach. Bis dahin scheitert der Build. Das Rezept setzt deshalb bewusst keine Option `skip-broken`, damit kein Image ohne Hardware-Decoding entsteht.

Wenn der Build mehrere Tage scheitert, diese Schritte ausführen:

1. Das Log unter *Actions* lesen.
2. Die Paketversionen in RPM Fusion und Fedora vergleichen.

## Auf die nächste Fedora-Version wechseln

So wird auf die nächste Fedora-Version gewechselt:

1. Einen Branch anlegen.
2. Im Rezept den Wert `image-version` erhöhen.
3. Einen Pull Request öffnen. Die Action baut das Image testweise, ohne es zu veröffentlichen.
4. Wenn der Testbuild grün ist: den Pull Request mergen.
5. Den Rechner mit dem Befehl `rpm-ostree upgrade` aktualisieren.
6. Neu starten.

Der Rechner folgt dem Tag `:latest`. Discover bietet deshalb keinen eigenen Wechsel der Fedora-Version an, der Wechsel geschieht nur über das Rezept.

## Signaturschlüssel

Der private Schlüssel liegt als Secret `SIGNING_SECRET` im Repo und als Datei im lokalen Tresor `~/Vaults/Wichtiges`. Er hat keine Passphrase, so verlangt es BlueBuild. Im Repo liegt nur der öffentliche Schlüssel `cosign.pub`.

> [!CAUTION]
> Den privaten Schlüssel nie committen. Wenn er neu erzeugt werden muss, prüft der Rechner das nächste Image gegen den alten Schlüssel und lehnt es ab. Dann führt nur der Weg über das Präfix `ostree-unverified-registry` zurück, wie beim [Umstieg](#auf-das-image-umsteigen).

## Rückweg

Im Bootmenü das gepinnte Deployment wählen. Dauerhaft zurück auf das offizielle Kinoite geht es mit diesem Befehl:

```sh
rpm-ostree rebase fedora:fedora/45/x86_64/kinoite
```

Dabei die Versionsnummer im Befehl an die laufende Fedora-Version anpassen.

## Änderungen

- 2026-11-20: Repo angelegt. Basis Fedora Kinoite 45, Inhalt wie im Abschnitt „Inhalt des Images“.
- 2026-11-20: Rechunking mit chunkah eingeschaltet, Messwerte im Abschnitt „Updates“. Vorher auf dem Branch `chunkah-test` geprüft: gleicher Inhalt, Import mit dem Befehl `ostree container image pull` erfolgreich.
- 2026-11-20: Wöchentlicher Check im Ordner `werkzeuge/`, BlueBuild-Action per Commit-SHA, Dependabot wöchentlich, Zwei-Faktor-Anmeldung als Voraussetzung für den Umstieg.
- 2026-11-22: nach dem Doku-Stil überarbeitet, Inhalt unverändert. Schritte mit zwei Handlungen sind in einzelne Schritte geteilt.
- 2026-11-23: nach den erweiterten Prüfregeln des Doku-Stils überarbeitet, Inhalt unverändert.
