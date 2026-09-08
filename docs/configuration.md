# Publish-Time Configuration

Use INI files for deployment-controlled settings:

- Backend: copy `backend/config.ini.example` to `backend/config.ini` on the server.
- Frontend: copy `frontend/public/app-config.ini.example` to `frontend/public/app-config.ini` before building, or place `app-config.ini` beside `index.html` in the published `frontend/dist` folder.

Backend precedence is:

1. Real environment variables
2. `backend/config.ini`, or the path in `APP_CONFIG_INI`
3. `.env`
4. Code defaults

Do not put secrets in the frontend INI file. It is served publicly by the browser.

## Local development

For the local backend on port 8000, set `API_BASE_URL=http://127.0.0.1:8000` in `frontend/public/app-config.ini`. This runtime file overrides the Vite API URL, including during local development. Reload the browser after changing it because the frontend caches the value for the page session.

Before a production build, set the INI to the production API URL, or replace `dist/app-config.ini` after building. Vite copies the public INI into the build, where it overrides `.env.production`.

Local configuration correction, 2026-09-08 11:17 IST: changed the local INI from the production API to loopback. The backend health and localhost CORS checks passed; credential-based sign-in was not tested. No API contracts, database schema, or frontend design changed. No reindexing is needed.
