# AGENTS.md

## fp-soother-web — FastAPI + HTMX web UI

- `app.py` — application factory; creates one `DeviceManager` per app instance and wires up the `pages`, `actions`, and `ws` routers plus static file serving.
- `devices.py` — `DeviceManager` owns one persistent `SootherClient` connection per paired device (rather than connecting per-request) so status can stream live and controls feel responsive. Handles both explicit BLE disconnect callbacks and command/write failures (which don't always trigger the disconnect callback promptly) by marking a device offline and scheduling a reconnect, while suppressing that handling during intentional close/forget/shutdown (`expect_disconnect`). Startup (`connect_known_devices`, called from the app's `lifespan`) schedules connections as background tasks rather than awaiting them, since BLE connects can block 20-30+ seconds — devices expose a `connecting` state meanwhile.
- `routes/pages.py`, `routes/actions.py`, `routes/ws.py` — server-rendered HTML pages, HTMX form-post partials for control actions (pair/forget/reconnect/per-field settings), and a per-device WebSocket for pushing live state updates. WebSocket-route dependencies (see `deps.py`) accept a `WebSocket`, not an HTTP `Request`.
- `controls.py` — declarative definitions (`CONTROLS`, `TOGGLES`, `COLOR_OPTIONS`) driving both the Jinja templates and the action routes; add new controllable fields here rather than hand-wiring new routes per field where the existing pattern fits.
- `templates/` + `static/` — Jinja2 templates and vendored HTMX (`static/htmx.min.js`); no frontend build step.
