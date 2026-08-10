# KaosHWP iOS Shortcut

`KaosHWP` receives an HWP, HWPX, or HML file from the iOS share sheet, uploads
it to Brain's temporary handoff area, and opens it in RHWP. Handoffs expire after
30 minutes and are not added to Paperless.

## Cloudflare Access

Create a Cloudflare Access service token for `Kaos Shortcuts`. Give it access
only to a self-hosted application whose destination is:

```text
kaosgdd.net/api/hwp-handoff/upload
```

Do not use a public Bypass policy. Store the generated client ID and client
secret only in the private Shortcut.

## Shortcut Actions

1. Name the shortcut `KaosHWP`.
2. Enable **Show in Share Sheet** and accept **Files** only.
3. Add **Get Name** for `Shortcut Input`.
4. Add a URL containing:

   ```text
   https://kaosgdd.net/api/hwp-handoff/upload?filename=[Name]
   ```

5. Add **Get Contents of URL**:
   - Method: `POST`
   - Request Body: `File`
   - File: `Shortcut Input`
   - Header `Content-Type`: `application/octet-stream`
   - Header `CF-Access-Client-Id`: the Access service-token client ID
   - Header `CF-Access-Client-Secret`: the Access service-token secret
6. Get dictionary value `openUrl` from the response.
7. Add **Open URLs** using `openUrl`.

RHWP fetches the temporary file through the user's normal Cloudflare Access
browser session. If that session has expired, Safari asks the user to sign in
before RHWP opens the document.

## API Contract

```text
POST /api/hwp-handoff/upload?filename=example.hwp
Content-Type: application/octet-stream

<raw file bytes>
```

Successful response:

```json
{
  "ok": true,
  "openUrl": "https://kaosgdd.net/rhwp/?url=...&filename=example.hwp"
}
```
