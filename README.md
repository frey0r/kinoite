# Kinoite-Image

Stand: 2026-11-20

Dieses Repo baut ein eigenes Fedora-Kinoite-Image mit BlueBuild auf GitHub Actions. Es ergänzt das offizielle Kinoite um Codecs und Hardware-Werkzeuge für einen AMD-Desktop. Das README richtet sich an mich selbst und beschreibt Inhalt, Umstieg, Updates und Rückweg.

## Inhalt des Images

Die Basis ist `quay.io/fedora/fedora-kinoite` in der Version aus `image-version` im Rezept, nicht Universal Blue: ublue entfernt Discovers rpm-ostree-Backend und fedora-third-party. Discover mit automatischen Updates, Flathub und fedora-third-party bleiben wie im offiziellen Kinoite.

Die folgende Tabelle zeigt, was das Rezept `recipes/recipe.yml` gegenüber dem offiziellen Kinoite ändert:

| Änderung | Pakete oder Dateien | Herkunft |
|---|---|---|
| Volle Codecs | `ffmpeg` statt `ffmpeg-free`, `mesa-va-drivers-freeworld` (HEVC und H.264 per VA-API) | RPM Fusion free |
| Lüftersteuerung | `coolercontrol`, Dienst `coolercontrold` | COPR codifryed/CoolerControl |
| GPU-Undervolt und Powerlimit | `lact`, Dienst `lactd` | COPR ilyaz/LACT |
| Werkzeuge | `cava`, `fastfetch`, `steam-devices` | Fedora |
| Kernelmodule beim Start | `ntsync`, `nct6775` in `/usr/lib/modules-load.d` | dieses Repo |
| udev-Regeln | Tinker 75 (QMK), 8BitDo, `energy_uj` lesbar für MangoHud, in `/usr/lib/udev/rules.d` | dieses Repo |
| Entfernt | `firefox`, `firefox-langpacks` | – |

RPM Fusion und die COPRs sind nur während des Builds aktiv. Das Modul `dnf` entfernt sie am Ende wieder (`cleanup: true`).

Lokal auf dem Rechner bleiben die Kernelparameter, alle Flatpaks, die Konfigurationen in `/etc/lact` und `/etc/coolercontrol`, `/etc/hosts` und alles im Home-Verzeichnis.

## Auf das Image umsteigen

Für den Umstieg gelten diese Voraussetzungen:

- Der letzte Build in *Actions* ist grün, und das Paket `kinoite` unter *Packages* ist auf **Public** gestellt.
- Der Rechner läuft auf derselben Fedora-Version wie `image-version`.
- Das gebootete Deployment ist gepinnt (`sudo ostree admin pin 0`) und dient als Rückweg.

So wird umgestiegen:

1. Auf das unsignierte Image wechseln und die gelayerten Pakete dabei entfernen:
   ```sh
   rpm-ostree rebase ostree-unverified-registry:ghcr.io/frey0r/kinoite:latest --uninstall=cava --uninstall=coolercontrol --uninstall=fastfetch --uninstall=steam-devices
   ```
2. Neu starten.
3. Die lokalen Kopien in `/etc` löschen, die das Image ersetzt: `/etc/modules-load.d/ntsync.conf`, `/etc/modules-load.d/nct6775.conf`, die drei Regeln in `/etc/udev/rules.d`, `/etc/systemd/system/lactd.service` und die CoolerControl-Datei in `/etc/yum.repos.d`. Danach `sudo systemctl daemon-reload` und `sudo systemctl enable --now lactd`.
4. Auf das signierte Image wechseln:
   ```sh
   rpm-ostree rebase ostree-image-signed:docker://ghcr.io/frey0r/kinoite:latest
   ```
5. Neu starten.

Ergebnis: `rpm-ostree status` zeigt als Origin `ostree-image-signed:docker://ghcr.io/frey0r/kinoite:latest` und keine `LayeredPackages`.

Der erste Schritt läuft ohne Signaturprüfung, weil die Signaturregel und der öffentliche Schlüssel erst mit dem Image auf den Rechner kommen. Erst der zweite Wechsel prüft die Signatur.

## Updates

GitHub Actions baut das Image jeden Tag um 06:00 UTC neu, dazu bei jedem Push und manuell über *Actions → bluebuild → Run workflow*. Discover installiert Updates einmal pro Woche automatisch.

Discover erkennt ein Update am Label `org.opencontainers.image.version`, und dieses Label erbt das Image vom Fedora-Basisimage. Eine reine Rezeptänderung zeigt Discover deshalb erst mit dem nächsten Fedora-Basisupdate an. Sofort holt sie `rpm-ostree upgrade`.

Nach jedem Build teilt chunkah das Image nach Paketen in Layer auf, höchstens 128. Eingeschaltet ist das mit `chunkah: true` im Workflow. Große Pakete bekommen einen eigenen Layer, kleine teilen sich einen. Ein Update lädt dadurch die Layer geänderter Pakete und die RPM-Datenbank, alle anderen Layer bleiben auf dem Rechner. Das fertige Image enthält keinen OSTree-Commit mehr, rpm-ostree importiert es trotzdem. Das Versionslabel bleibt erhalten.

Die folgende Tabelle zeigt die Downloadgrößen mit und ohne chunkah, ermittelt am 2026-11-20:

| Fall | ohne chunkah | mit chunkah |
|---|---|---|
| Neubau ohne Paketänderung, gemessen | 264 MB | 92 MB |
| F45-Updates vom 2026-11-13 bis 2026-11-20, hochgerechnet | 2,1 GB | 1,3 GB |
| Ganzes Image beim Umstieg | 3,58 GB | 3,26 GB |

> [!NOTE]
> Wenn sich die Aufteilung ändert, lädt das nächste Update mehr. Beim Abschalten von chunkah oder bei einer anderen Layer-Zahl ist es das ganze Image. BlueBuild verwendet chunkah ohne feste Version, deshalb kann auch eine geänderte chunkah-Version ein einzelnes Update vergrößern.

Dependabot schlägt Updates der GitHub Action als Pull Request vor. Diese Pull Requests mergen, denn GitHub schaltet geplante Builds nach 60 Tagen ohne Aktivität im Repo ab.

## Wenn ein Build scheitert

Ein gescheiterter Build veröffentlicht nichts. Das zuletzt gebaute Image bleibt unter `:latest`, und der Rechner bleibt auf seinem Stand.

Die häufigste Ursache ist `mesa-va-drivers-freeworld`. Das Paket muss exakt zur Mesa-Version von Fedora passen, und RPM Fusion zieht eine höhere Mesa-Version oft erst einige Tage später nach. Bis dahin scheitert der Build. Das Rezept setzt deshalb bewusst kein `skip-broken`, damit kein Image ohne Hardware-Decoding entsteht.

Wenn der Build mehrere Tage scheitert: das Log unter *Actions* lesen und die Paketversionen in RPM Fusion und Fedora vergleichen.

## Auf die nächste Fedora-Version wechseln

So wird auf die nächste Fedora-Version gewechselt:

1. Einen Branch anlegen und `image-version` im Rezept erhöhen.
2. Einen Pull Request öffnen. Die Action baut das Image testweise, ohne es zu veröffentlichen.
3. Wenn der Testbuild grün ist: den Pull Request mergen.
4. Den Rechner mit `rpm-ostree upgrade` aktualisieren und neu starten.

Der Rechner folgt dem Tag `:latest`. Discover bietet deshalb keinen eigenen Wechsel der Fedora-Version an, der Wechsel geschieht nur über das Rezept.

## Signaturschlüssel

Der private Schlüssel liegt als Secret `SIGNING_SECRET` im Repo und als Datei im lokalen Tresor `~/Vaults/Wichtiges`. Er hat keine Passphrase, so verlangt es BlueBuild. Im Repo liegt nur `cosign.pub`.

> [!CAUTION]
> Den privaten Schlüssel nie committen. Wenn er neu erzeugt werden muss, prüft der Rechner das nächste Image gegen den alten Schlüssel und lehnt es ab. Dann führt nur der Weg über `ostree-unverified-registry` zurück, wie beim Umstieg.

## Rückweg

Im Bootmenü das gepinnte Deployment wählen. Dauerhaft zurück auf das offizielle Kinoite geht es mit:

```sh
rpm-ostree rebase fedora:fedora/45/x86_64/kinoite
```

Dabei die Versionsnummer im Befehl an die laufende Fedora-Version anpassen.

## Änderungen

- 2026-11-20: Repo angelegt. Basis Fedora Kinoite 45, Inhalt wie im Abschnitt „Inhalt des Images“.
- 2026-11-20: Rechunking mit chunkah eingeschaltet, Messwerte im Abschnitt „Updates“. Vorher auf dem Branch `chunkah-test` geprüft: gleicher Inhalt, Import mit `ostree container image pull` erfolgreich.
