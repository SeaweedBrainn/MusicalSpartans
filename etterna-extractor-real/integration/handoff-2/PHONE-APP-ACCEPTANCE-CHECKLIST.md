# Phone App Production Acceptance Checklist

Use this checklist against the deployed API and the Android build.

- [ ] The API base is `https://rhythm-backend-emmanuel-hvfkdjhxfjc4d9a5.westus-01.azurewebsites.net`.
- [ ] The QR scanner accepts only the expected HTTPS origin and `/sessions/{id}/?key=...` shape.
- [ ] The scanned key is stored as the read key and never logged.
- [ ] `GET /v1/sessions/{id}/runs` sends `Authorization: Bearer <session_key>`.
- [ ] An empty session returns HTTP 200.
- [ ] Song A appears after Unity uploads it.
- [ ] Both `series.csv` and `summary.csv` download successfully.
- [ ] V2 metadata/header and note-level rows are preserved exactly.
- [ ] The app does not sum NPS to calculate total notes.
- [ ] `POST /coach` returns and displays `speech`, `phone_text`, `drill`, and `next_target`.
- [ ] A replay creates a new run and does not require another scan.
- [ ] A second song appears using the same QR/read key.
- [ ] Autoplay runs are labeled and excluded from player-performance claims.
- [ ] A 401 or 410 clears/withdraws the local session access.
- [ ] The app does not use the old Python `/runs` API.
- [ ] The app does not contain a production Gemini API key.
- [ ] Testing succeeds against the real Azure URL and Pages-origin CORS.
