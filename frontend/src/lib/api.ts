import type { AppConfig, PreviewPhase } from "./defaults";

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
  recommended_parallel_jobs: number;
};

export type PreviewPoint = {
  x: number;
  y: number;
};

export type PreviewAgent = {
  x: number;
  y: number;
  heading: number;
  group: string;
};

export type PreviewResponse = {
  phase: string;
  width: number;
  height: number;
  attractors: Record<string, PreviewPoint>;
  agents: PreviewAgent[];
  metrics: Record<string, string | number>;
};

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const responseText = await response.text();
    let detail: string | undefined;
    try {
      const payload = JSON.parse(responseText) as { detail?: string };
      detail = payload.detail;
    } catch {
      detail = undefined;
    }
    throw new Error(detail || responseText || "Request failed");
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

export async function fetchPreview(
  baseUrl: string,
  config: AppConfig,
  phase: PreviewPhase,
  signal?: AbortSignal,
): Promise<PreviewResponse> {
  return parseJson<PreviewResponse>(
    await fetch(`${baseUrl}/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config, phase }),
      signal,
    }),
  );
}
