import { invoke } from "@tauri-apps/api/core";

export type RuntimeInfo = {
  baseUrl: string;
  defaultOutputPath: string;
  startupError?: string | null;
};

const FALLBACK_RUNTIME: RuntimeInfo = {
  baseUrl: import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8765",
  defaultOutputPath: "output/stimulus.mp4",
  startupError: null,
};

export async function getRuntimeInfo(): Promise<RuntimeInfo> {
  try {
    return await invoke<RuntimeInfo>("get_backend_info");
  } catch {
    return FALLBACK_RUNTIME;
  }
}

export async function waitForBackend(baseUrl: string, attempts = 40): Promise<void> {
  for (let index = 0; index < attempts; index += 1) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      // Ignore and retry.
    }
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }

  throw new Error("The packaged backend did not become ready in time.");
}
