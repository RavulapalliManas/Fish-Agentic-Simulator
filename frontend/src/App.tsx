import { useEffect, useMemo, useState } from "react";

import { fetchOptimization, fetchStatus, startSimulation, type StatusResponse } from "./lib/api";
import { DEFAULT_CONFIG, MODEL_OPTIONS, SHAPE_OPTIONS, type AppConfig } from "./lib/defaults";
import { getRuntimeInfo, waitForBackend, type RuntimeInfo } from "./lib/runtime";

type TabId = "simulation" | "paradigm" | "rendering" | "appearance" | "output";

const TABS: Array<{ id: TabId; title: string; description: string }> = [
  { id: "simulation", title: "Simulation", description: "School dynamics and deterministic seed control." },
  { id: "paradigm", title: "Paradigm", description: "Timing and branching behavior for the split stimulus." },
  { id: "rendering", title: "Rendering", description: "Video duration, frame rate, and export resolution." },
  { id: "appearance", title: "Appearance", description: "Agent geometry and display styling." },
  { id: "output", title: "Output", description: "Destination path, progress, and final preview." },
];

function App() {
  const [activeTab, setActiveTab] = useState<TabId>("simulation");
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [backendReady, setBackendReady] = useState(false);
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState("Starting backend…");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const busy = status?.status === "queued" || status?.status === "running";
  const progressValue = Math.round(status?.progress ?? 0);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const nextRuntime = await getRuntimeInfo();
        if (!active) {
          return;
        }
        setRuntime(nextRuntime);
        setConfig((current) => ({
          ...current,
          output_path: current.output_path || nextRuntime.defaultOutputPath,
        }));
        if (nextRuntime.startupError) {
          setErrorMessage(nextRuntime.startupError);
          setInfoMessage("Backend unavailable.");
          return;
        }
        await waitForBackend(nextRuntime.baseUrl);
        if (!active) {
          return;
        }
        setBackendReady(true);
        setInfoMessage("Backend ready. Configure the stimulus and generate a video.");
      } catch (error) {
        if (!active) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Failed to start the backend.");
        setInfoMessage("Backend unavailable.");
      }
    })();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!runtime || !jobId || !busy) {
      return;
    }

    const handle = window.setInterval(async () => {
      try {
        const nextStatus = await fetchStatus(runtime.baseUrl, jobId);
        setStatus(nextStatus);
        if (nextStatus.status === "completed") {
          window.clearInterval(handle);
          setPreviewUrl(`${runtime.baseUrl}${nextStatus.video_url}?t=${Date.now()}`);
          setInfoMessage("Video complete. Preview is ready.");
          setActiveTab("output");
        } else if (nextStatus.status === "failed") {
          window.clearInterval(handle);
          setErrorMessage(nextStatus.error ?? "Video generation failed.");
        }
      } catch (error) {
        window.clearInterval(handle);
        setErrorMessage(error instanceof Error ? error.message : "Failed to read job status.");
      }
    }, 500);

    return () => window.clearInterval(handle);
  }, [busy, jobId, runtime]);

  const summaryRows = useMemo(
    () => [
      { label: "Model", value: config.model_type },
      { label: "Agents", value: String(config.number_of_agents) },
      { label: "Resolution", value: `${config.output_width} × ${config.output_height}` },
      { label: "Duration", value: `${config.video_duration}s @ ${config.fps} FPS` },
      { label: "Split", value: `${Math.round(config.split_ratio * 100)}% left` },
    ],
    [config],
  );

  const updateConfig = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => {
    setConfig((current) => ({ ...current, [key]: value }));
  };

  const handleGenerate = async () => {
    if (!runtime) {
      return;
    }
    setErrorMessage(null);
    setPreviewUrl(null);
    setInfoMessage("Queueing deterministic export…");

    try {
      const response = await startSimulation(runtime.baseUrl, config);
      setJobId(response.job_id);
      setStatus({
        job_id: response.job_id,
        status: "queued",
        progress: 0,
        eta_seconds: null,
        phase: "queued",
        output_path: response.output_path,
        metadata_path: null,
        video_url: response.video_url,
        error: null,
      });
      setInfoMessage("Rendering started. Polling progress every 0.5 seconds.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to start simulation.");
    }
  };

  const handleAutoOptimize = async () => {
    if (!runtime) {
      return;
    }
    setErrorMessage(null);
    setInfoMessage("Applying backend optimization recommendations…");

    try {
      const suggestion = await fetchOptimization(runtime.baseUrl, window.innerWidth, window.innerHeight);
      setConfig((current) => ({
        ...current,
        number_of_agents: suggestion.number_of_agents,
        fps: suggestion.fps,
        output_width: suggestion.output_width,
        output_height: suggestion.output_height,
      }));
      setInfoMessage(
        `Optimized for ${suggestion.cpu_cores} CPU cores and ${suggestion.ram_gb.toFixed(1)} GB RAM.`,
      );
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unable to fetch optimized settings.");
    }
  };

  return (
    <div className="min-h-screen px-5 py-6 text-slate-800 lg:px-8">
      <div className="mx-auto flex max-w-[1580px] flex-col gap-5">
        <header className="rounded-[28px] border border-white/70 bg-white/80 px-6 py-5 shadow-panel backdrop-blur">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-accent-600">
                Fish Stimulus Desktop
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">
                Headless video generation, packaged as a one-click desktop tool.
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">
                Configure the stimulus, export a deterministic MP4, and keep the Python service hidden behind the desktop shell.
              </p>
            </div>

            <div className="flex flex-col gap-3 lg:min-w-[360px]">
              <div className="flex items-center justify-between rounded-2xl bg-slate-950 px-4 py-3 text-white">
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-slate-300">Backend</p>
                  <p className="text-sm font-medium">
                    {errorMessage ? "Startup failed" : backendReady ? "Ready on localhost" : "Starting service"}
                  </p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    errorMessage
                      ? "bg-rose-500/20 text-rose-100"
                      : backendReady
                        ? "bg-emerald-500/20 text-emerald-200"
                        : "bg-slate-700 text-slate-200"
                  }`}
                >
                  {errorMessage ? "Error" : backendReady ? "Online" : "Booting"}
                </span>
              </div>

              <div className="flex gap-3">
                <button
                  className="rounded-xl bg-accent-500 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-accent-600 disabled:cursor-not-allowed disabled:bg-slate-300"
                  disabled={!backendReady || busy}
                  onClick={handleAutoOptimize}
                >
                  Auto Optimize
                </button>
                <button
                  className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!backendReady || busy}
                  onClick={() => setActiveTab("output")}
                >
                  Review Output
                </button>
              </div>
            </div>
          </div>
        </header>

        <main className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)_360px]">
          <aside className="rounded-[28px] border border-white/70 bg-white/80 p-4 shadow-panel backdrop-blur">
            <div className="space-y-2">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  className={`w-full rounded-2xl px-4 py-4 text-left transition ${
                    activeTab === tab.id
                      ? "bg-slate-950 text-white shadow-sm"
                      : "bg-slate-50 text-slate-700 hover:bg-slate-100"
                  }`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <p className="text-sm font-semibold">{tab.title}</p>
                  <p className={`mt-1 text-xs leading-5 ${activeTab === tab.id ? "text-slate-300" : "text-slate-500"}`}>
                    {tab.description}
                  </p>
                </button>
              ))}
            </div>

            <div className="mt-6 rounded-2xl bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Current preset</p>
              <div className="mt-4 space-y-3">
                {summaryRows.map((row) => (
                  <div key={row.label} className="flex items-center justify-between text-sm">
                    <span className="text-slate-500">{row.label}</span>
                    <span className="font-medium text-slate-800">{row.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </aside>

          <section className="rounded-[28px] border border-white/70 bg-white/85 p-6 shadow-panel backdrop-blur">
            <fieldset disabled={!backendReady || busy} className={busy ? "opacity-70" : ""}>
              {activeTab === "simulation" && (
                <div className="space-y-5">
                  <SectionHeader title="Simulation" description="Deterministic school dynamics for lightweight generation." />
                  <div className="grid gap-4 md:grid-cols-2">
                    <NumberField label="Random Seed" value={config.random_seed} onChange={(value) => updateConfig("random_seed", value)} min={0} step={1} />
                    <SelectField label="Model Type" value={config.model_type} options={MODEL_OPTIONS} onChange={(value) => updateConfig("model_type", value)} />
                    <NumberField label="Number of Agents" value={config.number_of_agents} onChange={(value) => updateConfig("number_of_agents", value)} min={2} step={1} />
                    <NumberField label="Noise" value={config.noise} onChange={(value) => updateConfig("noise", value)} min={0} max={2} step={0.01} />
                    <NumberField label="Cohesion" value={config.cohesion} onChange={(value) => updateConfig("cohesion", value)} min={0} max={4} step={0.05} />
                    <NumberField label="Alignment" value={config.alignment} onChange={(value) => updateConfig("alignment", value)} min={0} max={4} step={0.05} />
                    <NumberField label="Separation" value={config.separation} onChange={(value) => updateConfig("separation", value)} min={0} max={4} step={0.05} />
                  </div>
                </div>
              )}

              {activeTab === "paradigm" && (
                <div className="space-y-5">
                  <SectionHeader title="Paradigm" description="Timing controls for the center hold and branch split." />
                  <div className="grid gap-4 md:grid-cols-2">
                    <NumberField label="Split Ratio" value={config.split_ratio} onChange={(value) => updateConfig("split_ratio", value)} min={0} max={1} step={0.01} />
                    <NumberField label="Time in Center (s)" value={config.time_in_center} onChange={(value) => updateConfig("time_in_center", value)} min={0} step={0.1} />
                    <NumberField label="Time to Split (s)" value={config.time_to_split} onChange={(value) => updateConfig("time_to_split", value)} min={0.1} step={0.1} />
                    <NumberField label="Rotation Strength" value={config.rotation_strength} onChange={(value) => updateConfig("rotation_strength", value)} min={0} step={1} />
                    <NumberField label="Attractor Strength" value={config.attractor_strength} onChange={(value) => updateConfig("attractor_strength", value)} min={0} step={5} />
                  </div>
                </div>
              )}

              {activeTab === "rendering" && (
                <div className="space-y-5">
                  <SectionHeader title="Rendering" description="Frame-locked export settings for standard laptop hardware." />
                  <div className="grid gap-4 md:grid-cols-2">
                    <NumberField label="Duration (s)" value={config.video_duration} onChange={(value) => updateConfig("video_duration", value)} min={0.1} step={0.5} />
                    <NumberField label="FPS" value={config.fps} onChange={(value) => updateConfig("fps", value)} min={1} step={1} />
                    <NumberField label="Width" value={config.output_width} onChange={(value) => updateConfig("output_width", value)} min={160} step={10} />
                    <NumberField label="Height" value={config.output_height} onChange={(value) => updateConfig("output_height", value)} min={120} step={10} />
                  </div>
                </div>
              )}

              {activeTab === "appearance" && (
                <div className="space-y-5">
                  <SectionHeader title="Appearance" description="Simple geometry and clean display styling for the exported video." />
                  <div className="grid gap-4 md:grid-cols-2">
                    <SelectField label="Shape" value={config.shape} options={SHAPE_OPTIONS} onChange={(value) => updateConfig("shape", value)} />
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                      <div className="flex items-center justify-between">
                        <label className="text-sm font-medium text-slate-700">Size</label>
                        <span className="text-sm text-slate-500">{config.size.toFixed(1)}</span>
                      </div>
                      <input
                        className="mt-5 w-full"
                        type="range"
                        min={2}
                        max={40}
                        step={0.5}
                        value={config.size}
                        onChange={(event) => updateConfig("size", Number(event.target.value))}
                      />
                    </div>
                    <TextField label="Background Color" value={config.background_color} onChange={(value) => updateConfig("background_color", value)} />
                  </div>
                </div>
              )}

              {activeTab === "output" && (
                <div className="space-y-5">
                  <SectionHeader title="Output" description="Choose where the video goes, then launch a headless export." />
                  <div className="space-y-4">
                    <TextField label="File Location" value={config.output_path} onChange={(value) => updateConfig("output_path", value)} />
                    <button
                      className="rounded-xl bg-accent-500 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-accent-600 disabled:cursor-not-allowed disabled:bg-slate-300"
                      disabled={!backendReady || busy}
                      onClick={handleGenerate}
                    >
                      {busy ? "Generating…" : "Generate Video"}
                    </button>
                    <div className="rounded-2xl bg-slate-50 p-4">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium text-slate-700">Export progress</span>
                        <span className="text-slate-500">{progressValue}%</span>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
                        <div
                          className="h-full rounded-full bg-accent-500 transition-all duration-300"
                          style={{ width: `${progressValue}%` }}
                        />
                      </div>
                      <p className="mt-3 text-sm text-slate-500">
                        {status?.phase ? `Phase: ${status.phase}. ` : ""}
                        {status?.eta_seconds != null ? `ETA ${status.eta_seconds.toFixed(1)} seconds.` : "Waiting for the next export."}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </fieldset>
          </section>

          <aside className="rounded-[28px] border border-white/70 bg-white/85 p-5 shadow-panel backdrop-blur">
            <div className="space-y-5">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Status</p>
                <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-900">
                  {busy ? "Rendering stimulus video" : "Ready for export"}
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">{infoMessage}</p>
                {errorMessage && (
                  <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    {errorMessage}
                  </div>
                )}
              </div>

              <div className="rounded-3xl bg-slate-950 p-4 text-white">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Progress</span>
                  <span className="text-sm text-slate-300">{progressValue}%</span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-accent-500 transition-all duration-300"
                    style={{ width: `${progressValue}%` }}
                  />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <StatTile label="Job" value={jobId ? jobId.slice(0, 8) : "--"} />
                  <StatTile label="Phase" value={status?.phase ?? "--"} />
                  <StatTile label="ETA" value={status?.eta_seconds != null ? `${status.eta_seconds.toFixed(1)}s` : "--"} />
                  <StatTile label="Status" value={status?.status ?? (backendReady ? "idle" : "booting")} />
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Video Preview</p>
                    <p className="text-xs text-slate-500">Preview is streamed from the local backend when the job finishes.</p>
                  </div>
                </div>

                {previewUrl ? (
                  <video
                    key={previewUrl}
                    className="aspect-video w-full rounded-[24px] border border-slate-200 bg-slate-950 object-cover shadow-sm"
                    controls
                    preload="metadata"
                    src={previewUrl}
                  />
                ) : (
                  <div className="flex aspect-video items-center justify-center rounded-[24px] border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-500">
                    Generate a video to see the preview here.
                  </div>
                )}

                <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
                  <div className="flex justify-between gap-3">
                    <span>Output path</span>
                    <span className="max-w-[180px] truncate text-right font-medium text-slate-800">
                      {(status?.output_path ?? config.output_path) || "--"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}

type SectionHeaderProps = {
  title: string;
  description: string;
};

function SectionHeader({ title, description }: SectionHeaderProps) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-accent-600">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
    </div>
  );
}

type NumberFieldProps = {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
};

function NumberField({ label, value, onChange, min, max, step }: NumberFieldProps) {
  return (
    <label className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
      <span className="block text-sm font-medium text-slate-700">{label}</span>
      <input
        className="mt-3 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-800 outline-none transition focus:border-accent-300 focus:ring-4 focus:ring-accent-50"
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

type TextFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
};

function TextField({ label, value, onChange }: TextFieldProps) {
  return (
    <label className="block rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
      <span className="block text-sm font-medium text-slate-700">{label}</span>
      <input
        className="mt-3 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-800 outline-none transition focus:border-accent-300 focus:ring-4 focus:ring-accent-50"
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

type SelectFieldProps = {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
};

function SelectField({ label, value, options, onChange }: SelectFieldProps) {
  return (
    <label className="block rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
      <span className="block text-sm font-medium text-slate-700">{label}</span>
      <select
        className="mt-3 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-800 outline-none transition focus:border-accent-300 focus:ring-4 focus:ring-accent-50"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

type StatTileProps = {
  label: string;
  value: string;
};

function StatTile({ label, value }: StatTileProps) {
  return (
    <div className="rounded-2xl bg-slate-900/70 px-3 py-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{label}</p>
      <p className="mt-2 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

export default App;
