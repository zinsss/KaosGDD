# Memos Cloudflare Access relay

KaosGDD embeds the custom Memos frontend at `/memos-app`. Embedded API calls use
Brain at `/api/memos`; the browser does not receive a Memos personal access token.
The standalone Memos service remains available at `memos.kaosgdd.net` with its own
normal Memos login.

## Trust boundary

For every embedded request, Brain validates `Cf-Access-Jwt-Assertion` against the
Cloudflare Access team JWKS, issuer, and the audience assigned to the request host.
The audience for `kaosgdd.net` maps to the `zin` Memos account. The audience for
`family.kaosgdd.net` maps to the `my02` Memos account. A request without a valid
host-specific assertion is rejected before Brain reads a Memos credential.

Brain encrypts each Memos personal access token with
`MEMOS_RELAY_ENCRYPTION_KEY` and stores only the ciphertext in the existing
`brain_settings` table. Passwords and memo content are not stored in Brain.

Required environment variables:

```text
MEMOS_INTERNAL_URL=http://100.94.208.16:5230
MEMOS_PERSONAL_USERNAME=zin
MEMOS_FAMILY_USERNAME=my02
CLOUDFLARE_ACCESS_TEAM_DOMAIN=kaosgdd.cloudflareaccess.com
CLOUDFLARE_ACCESS_MAIN_AUD=<main Access application audience>
CLOUDFLARE_ACCESS_FAMILY_AUD=<family Access application audience>
MEMOS_RELAY_ENCRYPTION_KEY=<Fernet key>
```

## First connection

When a profile has no saved relay token, the frontend asks Brain to bootstrap it.
Brain first tries the pre-existing host-local Memos refresh cookie. If that session
is still valid, setup is automatic. Otherwise the embedded frontend displays the
Memos login form once. Brain exchanges those credentials for a short session token,
creates a non-expiring PAT through the supported Memos API, encrypts the PAT, and
discards the password.

The supplied username must match the configured account for that portal. A user
cannot connect the personal portal to the family Memos account or vice versa.

## Revocation and recovery

The generated tokens are named `KaosGDD Brain personal relay` and
`KaosGDD Brain family relay` in Memos account settings. Revoking one immediately
stops that portal's embedded Memos access. Delete the corresponding
`brain_settings` row with scope `memos_relay` before running the one-time connection
again.

Changing `MEMOS_RELAY_ENCRYPTION_KEY` makes existing ciphertext unreadable. Back up
the key with the other encrypted Kaos secrets. If the key is lost, revoke the two
PATs in Memos, clear their Brain settings, generate a new key, and reconnect.
