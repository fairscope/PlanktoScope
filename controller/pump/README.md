# controller.pump

The PlanktoScope's hardware controller for the pump.

## Usage

### Development

Install all dependencies including development tooling:

```sh
cd pump
just
```

Start controller for development:

```sh
cd pump
just dev
# make changes and restart
```

### API

### Start the pump:

**topic** `actuator/pump`

**payload:**
```json
{
  "action": "move",
  "direction": "FORWARD", // "FORWARD" or "BACKWARD"
  "volume": 0.5, // volume to pump in mL
  "flowrate": 0.5, // speed of pumping, in mL/min
}
```

### Stop the pump:

**topic** `actuator/pump`

**payload:**
```json
{
  "action": "stop",
}
```

### Set pump configuration

**topic** `actuator/pump`

**payload:**
```json
{
  "action": "set-configuration",
  "pump_steps_per_ml": 3408,
}
```

### Read pump configuration

**topic** `actuator/pump`

**payload:**
```json
{
  "action": "get-configuration",
}
```

**response**

```json
{
  "pump_steps_per_ml": 3408,
}
```

### status

**topic** `status/pump`

**payload when started:**
```json
{
  "status": "Started",
  "duration": 10, // duration in seconds
}
```

**payload when completed:**
```json
{
  "status": "Done",
}
```

**payload when stopped:**
```json
{
  "status": "Interrupted",
}
```

The status will be automatically published to new subscribers.
