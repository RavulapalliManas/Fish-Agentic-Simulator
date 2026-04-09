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

## Production Build

1. Build the packaged backend:

```bash
python3 backend/build_backend.py
```

2. Build the desktop app bundle:

```bash
npm run tauri:build
```

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
