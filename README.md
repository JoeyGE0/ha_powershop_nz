# ha_powershop_nz

Unofficial Home Assistant custom integration for Powershop NZ.

This integration uses **“normal person scraping”**:

- Keep an authenticated session (recommended: paste your `Cookie:` header from a logged-in browser session)
- Fetch Balance page HTML and parse the balance
- Fetch usage via the built-in CSV export endpoint: `/usage/data.csv`

## Install (manual)

Copy `custom_components/powershop_nz/` into your Home Assistant `config/custom_components/`.

Restart Home Assistant, then:

**Settings → Devices & services → Add integration → “Powershop NZ”**

## Auth options

- **Cookie (recommended)**: paste your browser `Cookie:` header value after logging in at `https://secure.powershop.co.nz`
- **Email/password**: included as a best-effort fallback (may break if captcha/2FA)

## What it creates

- `sensor.powershop_nz_balance` (NZD)
- `sensor.powershop_nz_usage_kwh` (based on recent CSV export window)

## Notes

- This is unofficial and may break if Powershop changes their site.
- Don’t commit HAR files, cookies, or tokens.

