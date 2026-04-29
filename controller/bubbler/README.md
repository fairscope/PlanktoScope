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
  // float between 0 and 1
  // 0 is same as "action": "off"
  "value": 0.5,
}
```

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

**payload when started:**
```json
{
  "status": "On",
  "value": 0.5,
}
```

**payload when stopped:**
```json
{
  "status": "Off",
}
```

The status will be automatically published to new subscribers.
