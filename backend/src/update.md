# software-updater service

backend automatically starts this software-updater service

### API

### Poll for an update:

**topic** `software-updater`

**payload:**
```json
{
  "action": "poll",
}
```

It will instruct the service to check for a new update.

See status below for watching availability of update.

### Info about an update:

**topic** `software-updater`

**payload:**
```json
{
  "action": "info",
  "uri": "..."
}
```

`uri` can be a http(s) URL or a path on disk.
It will respond with something like:

```json
{
  "version": "some-version-string",
  "build": "some-unique-build-id-string",
  "compatible": "PlanktoScope,rev1",
  "uri": "the uri passed to the payload"
}
```

### Install an update:

**topic** `software-updater`

**payload:**
```json
{
  "action": "install",
  "uri": "..."
}
```

`uri` can be a http(s) URL or a path on disk.

See status below for watching progress of install.

### Reboot:

**topic** `software-updater`

**payload:**
```json
{
  "action": "reboot"
}
```

Reboots the PlanktoScope.
This is necessary after an update installation completes.

### status

**topic** `software-updater/status`

**payload:**
```json
{
  "Operation": "", // https://rauc.readthedocs.io/en/v1.15.2/reference.html#operation-property
  "LastError": "", // https://rauc.readthedocs.io/en/v1.15.2/reference.html#lasterror-property
  "Progress": "" // https://rauc.readthedocs.io/en/v1.15.2/reference.html#progress-property
}
```

**topic** `software-updater/update-available`

**payload when no update available:**

```json
[false, null]
```

**payload when update available:**

```json
[true, {
  "version": "some-version-string",
  "build": "some-unique-build-id-string",
  "compatible": "PlanktoScope,rev1",
  "uri": "the uri passed to the payload"
}]
```
