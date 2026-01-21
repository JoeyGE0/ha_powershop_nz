# ha_powershop_nz

Unofficial Home Assistant custom integration for Powershop NZ.

This integration uses **“normal person scraping”**:

- Authenticate (Cookie auth recommended; email/password also supported)
- Fetch Balance page HTML and parse the balance
- Fetch usage via the built-in CSV export endpoint: `/usage/data.csv`

This repo is HACS-ready (has `hacs.json` and version tags).

## Install (manual)

Copy `custom_components/powershop_nz/` into your Home Assistant `config/custom_components/`.

Restart Home Assistant, then:

**Settings → Devices & services → Add integration → “Powershop NZ”**

## Auth options

- **Cookie (recommended)**: paste your browser `Cookie:` header value after logging in at `https://secure.powershop.co.nz`
- **Email/password**: works for many accounts, but can be blocked by captcha/2FA/bot protection. If it fails, use Cookie auth.

## Configuration / Options

- **Update interval**: defaults to **60 minutes** and is configurable via:
  - Settings → Devices & services → Powershop NZ → Configure → **Update settings**
  - “Update interval (minutes)” (`scan_interval_min`)
- **Usage window**:
  - “Usage scale” (`day|week|month|billing`)
  - “Usage window (days)”

## Entities

All entities are created under the “Powershop NZ” device.

- **Balance**
  - Balance (NZD)
- **Usage**
  - Usage (window) kWh
  - Usage (today) kWh (last record in the CSV)
  - Usage (yesterday) kWh (previous record in the CSV)
  - Usage (week to date) kWh
  - Usage (month to date) kWh
  - Usage (rolling 30d) kWh
- **Cost**
  - Estimated cost (window) NZD
  - Estimated cost (last record) NZD
  - Estimated cost (month to date) NZD

## Local smoke test (debugging)

There’s a local script to validate the scraping/parsing without needing Home Assistant:

```bash
python3 tools/smoke_test_powershop.py --self-test
```

To test against your real account (prints minimal info by default):

```bash
python3 tools/smoke_test_powershop.py --email "you@example.com" --password "..." --customer-id 123456 --days 7 --scale day
```

## Debug logging in Home Assistant

To see what’s happening without exposing secrets:

```yaml
logger:
  default: info
  logs:
    custom_components.powershop_nz: debug
```

## Notes

- This is unofficial and may break if Powershop changes their site.
- Don’t commit HAR files, cookies, or tokens.

