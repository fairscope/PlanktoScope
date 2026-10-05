# frontend

Parts of the PlanktoScope GUI.

### Development

Install all dependencies including development tooling:

```sh
cd frontend
just setup-dev
```

Start service for development:

```sh
just dev
```

Use `http://planktoscope-sponge-bob:3000/bookmarks` for preview.

Run the code auto-formatter on the project:

```sh
just format
```

Run all checks (including code formatting and linting):

```sh
just test
```
