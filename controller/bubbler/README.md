# controller.bubbler

The PlanktoScope's hardware controller for the bubbler.

## Usage

### Development

Install all dependencies including development tooling:

```sh
cd bubbler
just
```

Start controller for development:

```sh
cd bubbler
just dev
# make changes and restart
```

### API

### Start the bubbler:

**topic** `actuator/bubbler`

**payload:**
```json
{
  "action": "on",
  "value": 0.5,
}
```

`value` is a float >= `0` <= `1` that will adjust the bubbler intensity. The default is `1`.

### Stop the bubbler:

**topic** `actuator/bubbler`

**payload:**
```json
{
  "action": "off",
}
```

### status

**topic** `status/bubbler`

**payload when on:**
```json
{
  "status": "On",
  "value": 0.5,
}
```

**payload when off:**
```json
{
  "status": "Off",
}
```

The status will be automatically published to new subscribers.
