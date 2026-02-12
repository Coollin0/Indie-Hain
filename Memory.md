## Letzter Stand (2026-02-11)
- Admin Dashboard: SLA-Filterchips (>24h, >72h) und Verify-Summary inkl. Fehleranzeige pro Datei.
- Backend: Batch-Verify bricht nicht mehr komplett ab, sondern meldet Fehler pro Datei.
- Library: Legacy-Installpfade + fehlende Installationen bleiben sichtbar im Header.

## Offene naechste Aufgaben
- Optional: Library-Reparatur-Assistent (fehlende Spiele anhand Ordner-Suche wiederfinden).
- Optional: Dashboard-Fehlerliste exportierbar machen (Copy/Download).
- Optional: SLA-Filter in der URL oder Session speichern.

## Aktuelle Architektur-Situation
- Launcher nutzt lokale SQLite-DB in `~/.indie-hain`, Installationspfad in `services/env.py` inkl. Legacy-Liste und Settings.
- Backend bleibt FastAPI + SQLite; Admin-Tools lesen Manifeste/Storage direkt und schützen Pfad-Zugriffe.
- Dashboard ist Next.js mit zentraler `apiFetch`-Logik und Session-Tokens in `sessionStorage`.
