import type { AppConfig } from "./defaults";

export type SimulateResponse = {
  job_id: string;
  status: string;
  output_path: string;
  status_url: string;
  video_url: string;
};

export type StatusResponse = {
  job_id: string;
  status: string;
  progress: number;
  eta_seconds: number | null;
  phase: string | null;
  output_path: string | null;
  metadata_path: string | null;
  video_url: string | null;
  error: string | null;
};

export type OptimizeResponse = {
  number_of_agents: number;
  fps: number;
  output_width: number;
  output_height: number;
  cpu_cores: number;
  ram_gb: number;
};

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Request failed");
  }
  return (await response.json()) as T;
}

export async function startSimulation(baseUrl: string, config: AppConfig): Promise<SimulateResponse> {
  return parseJson<SimulateResponse>(
    await fetch(`${baseUrl}/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_path: config.output_path,
        config,
      }),
    }),
  );
}

export async function fetchStatus(baseUrl: string, jobId: string): Promise<StatusResponse> {
  return parseJson<StatusResponse>(await fetch(`${baseUrl}/status?job_id=${encodeURIComponent(jobId)}`));
}

export async function fetchOptimization(
  baseUrl: string,
  screenWidth?: number,
  screenHeight?: number,
): Promise<OptimizeResponse> {
  const params = new URLSearchParams();
  if (screenWidth) {
    params.set("screen_width", String(screenWidth));
  }
  if (screenHeight) {
    params.set("screen_height", String(screenHeight));
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return parseJson<OptimizeResponse>(await fetch(`${baseUrl}/optimize${suffix}`));
}
