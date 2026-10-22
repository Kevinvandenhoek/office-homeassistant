# Office for Home Assistant

Colleagues who share an office see in their own Home Assistant when someone skips the office: a
banner on the dashboard, and a push on the phone if they want one.

One Home Assistant hosts the office. The others join it with the host's address and a token. The
members only make requests out to the host, so no member opens a port. The host must already be
reachable from outside, for example through a Cloudflare Tunnel or Nabu Casa.

## Install

1. Add this repository to [HACS](https://hacs.xyz) as a custom repository of type Integration,
   install **Office** and restart Home Assistant.
2. Go to **Settings, Devices & services, Add integration** and pick **Office**.
   - **Join an office**: paste the host's address (for example `https://home.example.com`) and the
     token the host gave you.
   - **Host the office here**: type your name. Then open the integration, click **Configure** and
     pick **Add a colleague or renew a token** for each colleague. The token is shown once.
3. Add the card to a dashboard: edit the dashboard, add a card, and pick **Office**, or use

   ```yaml
   type: custom:office-card
   ```

## How it works

- A skip day can be set for today or for an office day up to Sunday of next week. The host picks
  the office days (Configure, **Office days**), Monday to Thursday by default.
- A change reaches the others after one minute. Undo it within that minute and nobody sees it.
- A member looks at the host once a minute. When the host is not reachable, the entities are
  unavailable and the card says so.
- Each house sends its own pushes, from what changes at the colleagues: when a colleague sets or
  clears a skip day, and a morning reminder on the day itself.

## Entities

| Entity | What it does |
| --- | --- |
| `switch.office_skip_day` | Your own skip day today; unavailable on a day without office |
| `sensor.office_skip_days` | Who of your colleagues skips today; every office day in the attribute `days` |
| `calendar.office` | Everyone's skip days as whole-day events |
| `switch.office_skip_day_notifications` | Pushes on or off |
| `select.office_skip_day_phone` | The phone that gets the pushes |
| `time.office_skip_day_morning_reminder` | Time of the morning reminder, 07:30 by default |
| `time.office_skip_day_notify_until` | A push about today only until this time, 12:00 by default |

The service `office.set_skip_day` with `date` and `skip` sets your own skip day on another day.

## Security

- The host answers on `/api/office/v1` without a Home Assistant login. The member's token is the
  key, sent as `Authorization: Bearer`. The host keeps only a hash of each token.
- A token can only read the skip days and change its own. It gives no access to anything else in
  Home Assistant.
- A wrong token counts as a failed login, so Home Assistant's IP ban applies when it is turned on.
  A member whose token was renewed must paste the new one soon: Home Assistant asks for it.
- The API only accepts a small JSON body with one boolean, for an office day in the shown weeks.

## Development

The logic without Home Assistant is in `planner.py`, tested with `pytest tests`.
