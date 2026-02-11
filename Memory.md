## Letzter Stand (2026-02-11)
- Library hat Rescan-Button sowie Ordner-Shortcut je Game; GUI öffnet Installationspfade direkt.
- Admin Dashboard unterstützt Auswahl + Bulk-Approve/Reject für Submissions inkl. Selektions-Toolbar.

## Offene naechste Aufgaben
- Optional: Backend-Admin-Overview-Endpoint fuer KPIs (Revenue, neue Users, aktive Submissions).
- Optional: Library-Reparaturfunktion, die fehlende Installationspfade automatisch den Legacy-Pfaden hinzufuegt.

## Aktuelle Architektur-Situation
- Launcher nutzt lokale SQLite-DB in `~/.indie-hain`, Installationspfade ueber `services/env.py` (inkl. Legacy-Liste).
- Dashboard ist Next.js mit zentraler `apiFetch`-Logik und Session-Tokens in `sessionStorage`.
