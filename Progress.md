## Project: Indie-Hain
Last updated: 2026-01-29

### Overview
- Active workspaces: `/Users/collinpaul/VSC/Indie-Hain` (launcher), `/Users/collinpaul/VSC/Indie-Hain-git` (repo), `/Users/collinpaul/VSC/Indie-Hain-Distribution` (backend), `/Users/collinpaul/VSC/Indie-Hain-git/indie-hain-dashboard` (dashboard).
- Launcher builds live in `/Users/collinpaul/VSC/Indie-Hain/dist` (`IndieHain-mac.zip`).
- VPS paths: `/home/cornelius/Indie-Hain` (repo), `/Dashboard` (dashboard), backend at `/home/cornelius/Indie-Hain/Indie-Hain-Distribution/backend`.

### Launcher (macOS)
- Profile page redesigned: login/register gate, registration form without avatar, login supports username/email, back buttons.
- Game upload moved to "Meine Games" with label "Game Upload".
- Password-reset-required flow supported by launcher.
- Shop refreshes on open and every 30s; manual Reload button added.
- API base now reads from `settings.json` via `services.env` (`uploader_client/admin_api/shop_api`).

### Backend
- Auth: JWT/refresh tokens, username login, password reset flow.
- Admin reset: temp password hash only (no plaintext stored), sessions revoked on reset.
- Security hardening:
  - Dev ownership checks for app/build mutation endpoints.
  - Path traversal protections and slug/component validation.
  - Manifest access requires entitlement (admin/dev-owner/free/purchased).
  - Purchase report uses server price.
  - JWT_SECRET required (no dev default).
- Admin delete user endpoint added (cannot delete self/admin/owners).

### Dashboard (Next.js)
- Admin dashboard (Users, Game Anfragen, Games).
- User role change, password reset, temp password shown only from reset response.
- Game Anfragen split into pending/approved/rejected.
- Auth fetch with refresh; tokens stored in `sessionStorage` (not `localStorage`).
- CSP/security headers added in `next.config.ts`.
- User delete action added in table.

### CI / Releases
- GitHub Actions builds macOS/Windows/Linux on tag `v*` and uploads release artifacts.
- Fixes: include `IndieHain.spec` in repo; `settings.json` creation uses bash.

### VPS / Ops
- Nginx dashboard subdomain with SSL.
- IP allowlist used for dashboard access.
- Node upgraded to 20.x for dashboard.
- Backend schema init uses `ensure_schema()`.

### Known issues / notes
- Launcher library cache stored inside app bundle; deleting `~/.indie-hain` does not clear library.
- Backend DB was reset; users/apps likely need re-init/bootstrap.
- Admin bootstrap endpoint is `/api/auth/bootstrap-admin`.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Lokale Library/Cart-Datenbank in `~/.indie-hain/indiehain.db` statt im App-Bundle.
- Geänderte Dateien: `services/env.py`, `data/store.py`
- Technische Begründung: Entkoppelt persistente Nutzerdaten vom App-Bundle, sodass Cache/DB durch Löschen von `~/.indie-hain` zuverlässig zurückgesetzt werden können.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: `mini_service.py` nutzt nun die Nutzer-DB unter `~/.indie-hain/indiehain.db` mit Fallback auf die alte `data/indiehain.db`.
- Geänderte Dateien: `mini_service.py`
- Technische Begruendung: Dev-Lizenzservice folgt der neuen DB-Location und bleibt fuer bestehende lokale Daten kompatibel.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Automatische Migration der alten `data/indiehain.db` in `~/.indie-hain/indiehain.db` beim Start.
- Geänderte Dateien: `services/env.py`, `data/store.py`, `mini_service.py`
- Technische Begründung: Reduziert manuelle Schritte nach Pfadwechsel und sorgt dafür, dass Launcher und Lizenzservice denselben aktuellen Datenbestand nutzen.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Diagnosebereich im Profil mit API-Base/Datenordner sowie Reset-Button für lokale Daten (Session/Cart/Library).
- Geänderte Dateien: `pages/profile_page.py`, `services/env.py`
- Technische Begründung: Vereinfacht Support/Debugging durch sichtbare Pfade und ermöglicht ein sauberes Zurücksetzen ohne Legacy-Migration.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Standard-Installationsordner nach `~/.indie-hain/Installed` verlegt (konfigurierbar), Legacy-Installationen werden weiterhin erkannt; Profil zeigt Installationspfad inkl. Öffnen-Button.
- Geänderte Dateien: `services/env.py`, `gui.py`, `pages/game_info_page.py`, `pages/profile_page.py`
- Technische Begründung: Installationen liegen außerhalb des App-Bundles, sind updatesicher und zentral konfigurierbar; Legacy-Pfade bleiben kompatibel.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Profil-Diagnose erlaubt das Ändern des Installationsordners inkl. Legacy-Merkung alter Pfade.
- Geänderte Dateien: `services/env.py`, `pages/profile_page.py`
- Technische Begründung: Nutzer können den Installationspfad selbst wählen; alte Installationen bleiben auffindbar, ohne das App-Bundle zu belasten.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Legacy-Installationsordner im Profil anzeigen und verwalten (öffnen/entfernen/leer).
- Geänderte Dateien: `services/env.py`, `pages/profile_page.py`
- Technische Begründung: Transparenz über alte Installationspfade, einfache Bereinigung ohne Funktionsverlust für bestehende Installationen.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Legacy-Installationspfade prüfen und fehlende Pfade im Profil hervorheben inkl. Schnell-Entfernen.
- Geänderte Dateien: `services/env.py`, `pages/profile_page.py`
- Technische Begründung: Verhindert verwaiste Legacy-Einträge, reduziert Suchpfade und verbessert die Diagnose bei verschwundenen Installationen.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Admin Dashboard mit Filter- und Suchleisten pro Tab, Status-Header (API/Sync), Manifest-Preview, UX-Polish und konsistenter Session-Token-Logik.
- Geänderte Dateien: `indie-hain-dashboard/src/app/page.tsx`, `indie-hain-dashboard/src/app/globals.css`
- Technische Begründung: Schnellere Ops-Workflows durch gezieltes Filtern/Suchen, bessere Sichtbarkeit des Systemstatus und weniger Token-Inkonsistenzen bei Refresh.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Library-Rescan + "Ordner"-Button pro Game, inkl. Schnellzugriff auf Installationspfade.
- Geänderte Dateien: `pages/library_page.py`, `gui.py`
- Technische Begründung: Beschleunigt Diagnose bei verschobenen Installationen und ermöglicht direkten Zugriff auf den Installationsordner.

### 2026-02-11
- Datum: 2026-02-11
- Umgesetztes Feature: Admin Dashboard mit Auswahl-Checkboxen und Bulk-Approve/Reject für Submissions.
- Geänderte Dateien: `indie-hain-dashboard/src/app/page.tsx`
- Technische Begründung: Moderation mehrerer Uploads in einem Schritt reduziert Klicks und beschleunigt Ops-Workflows.
