# controller.display

The PlanktoScope's hardware controller for the display.

## Usage

### Development

Install all dependencies including development tooling:

```sh
cd display
just
```

Start controller for development:

```sh
cd display
just dev
# make changes and restart
```

### API

### Configure the display:

**topic** `display`

**payload:**
```json
{
  "action": "configure",
  "config": {
    "url": "http://...",
    "online": false,
  }
}
```

Make sure to send the message with `retain`.
