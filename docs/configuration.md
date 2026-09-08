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
