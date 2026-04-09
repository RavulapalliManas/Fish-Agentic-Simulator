# Fish Stimulus Generator Desktop

Lightweight desktop app for deterministic fish stimulus generation.

## Stack

- Frontend: React + Vite + Tailwind CSS
- Desktop shell: Tauri
- Backend: Python + FastAPI
- Packaging: PyInstaller for the backend, Tauri bundling for the app

## Project Structure

```text
root/
  backend/
  frontend/
  src-tauri/
```

## What the App Does

- Starts with a single desktop click
- Launches a bundled Python backend automatically
- Generates headless MP4 stimuli from a clean React interface
- Uses exact left/right split counts instead of probabilistic ratios
- Samples deterministic preview frames for aggregation, stabilization, and split layout design
- Polls progress without freezing the UI
- Streams the finished video back into the app for preview

## Backend API

- `POST /simulate`
  - queues a deterministic video-generation job
  - accepts `config` plus `output_path`
- `GET /status?job_id=...`
  - returns progress, phase, ETA, output path, and error state
- `GET /optimize`
  - recommends `number_of_agents`, `fps`, and `resolution`
- `POST /preview`
  - samples a deterministic preview frame for `center`, `stabilize`, or `split`
  - accepts the same `config` payload used for rendering
- `GET /health`
  - readiness probe for the desktop shell
- `GET /jobs/{job_id}/video`
  - returns the finished MP4 for preview

## Local Development

1. Install backend dependencies:

```bash
python3 -m pip install -r backend/requirements.txt
```

2. Install frontend and Tauri dependencies:

```bash
npm install
npm --prefix frontend install
```

3. Run the desktop app in development:

```bash
npm run tauri:dev
```

The Tauri shell will:

- choose a free localhost port
- launch `backend/main.py`
- pass the base URL to the frontend
- terminate the backend when the desktop app closes

## Browser-Only UI Preview

If you want to inspect the React UI in a browser instead of the Tauri shell, run the backend and frontend separately:

```bash
npm run backend:dev
```

In a second terminal:

```bash
npm run frontend:dev
```

The app will detect browser mode automatically and connect to `http://127.0.0.1:8765`.

## Native Installers

Create the native installer bundle for the current operating system with one command:

```bash
npm run release:desktop
```

Outputs by platform:

- macOS: zipped `.app`
- Windows: NSIS `.exe` installer
- Linux: `.AppImage` plus `.deb`

Each build also writes a `release-manifest.json` containing the artifact names and SHA-256 checksums.

The release files are written to:

```text
release/
```

The script intentionally builds the macOS `.app` bundle directly and then zips it, which is more reliable in headless/local automation than DMG creation.

## Cross-Platform CI Releases

This repository now includes a GitHub Actions workflow at:

```text
.github/workflows/build-native-installers.yml
```

It builds separate native artifacts for:

- macOS
- Windows
- Linux

How to use it:

1. Push a tag such as `v1.0.0`
2. GitHub Actions builds all three platforms
3. The workflow uploads the installers to the corresponding GitHub Release

You can also run the workflow manually with `workflow_dispatch` to test the build matrix before cutting a release.

## Distribution Targets

Tauri is configured for:

- Windows installer
- macOS app bundle / disk image
- Linux AppImage

The backend is bundled as a PyInstaller-generated standalone executable, so end users do not need Python installed.

## Notes

- The backend renderer is headless and uses OpenCV rather than Qt.
- The UI never blocks on video generation.
- The same config + seed yields the same video output.
