import { useEffect, useMemo, useState, type ReactNode } from "react";

import StimulusPreview from "./components/StimulusPreview";
import Tooltip from "./components/Tooltip";
import {
  fetchOptimization,
  fetchPreview,
  fetchStatus,
  startSimulation,
  type PreviewResponse,
  type StatusResponse,
} from "./lib/api";
import {
  applyLayoutPreset,
  attractorCoordinateKey,
  ATTRACTOR_OPTIONS,
  DEFAULT_CONFIG,
  DEFAULT_LAYOUT_PRESET_ID,
  LAYOUT_PRESETS,
  MODEL_OPTIONS,
  PREVIEW_PHASE_OPTIONS,
  rebalanceSplit,
  scaleArenaLayout,
  SHAPE_OPTIONS,
  TAB_COPY,
  type AppConfig,
  type AttractorKey,
  type PreviewPhase,
  type TabId,
} from "./lib/defaults";
import { getRuntimeInfo, waitForBackend, type RuntimeInfo } from "./lib/runtime";

function App() {
  const [activeTab, setActiveTab] = useState<TabId>("dynamics");
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [backendReady, setBackendReady] = useState(false);
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewPhase, setPreviewPhase] = useState<PreviewPhase>("split");
  const [previewMessage, setPreviewMessage] = useState("Sampling deterministic preview…");
  const [designMode, setDesignMode] = useState(false);
  const [selectedAttractor, setSelectedAttractor] = useState<AttractorKey>("left");
  const [layoutPresetId, setLayoutPresetId] = useState(DEFAULT_LAYOUT_PRESET_ID);
  const [ghostAgentsEnabled, setGhostAgentsEnabled] = useState(true);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState("Starting backend…");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const busy = status?.status === "queued" || status?.status === "running";
  const progressValue = Math.round(status?.progress ?? 0);
  const currentPresetLabel = layoutPresetId === "custom"
    ? "Custom Layout"
    : (LAYOUT_PRESETS.find((entry) => entry.id === layoutPresetId)?.name ?? "Custom Layout");

  useEffect(() => {
    let active = true;
    let detectedMode: RuntimeInfo["mode"] = "tauri";

    (async () => {
      try {
        const nextRuntime = await getRuntimeInfo();
        if (!active) {
          return;
        }
        detectedMode = nextRuntime.mode;
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

        if (nextRuntime.mode === "browser") {
          setInfoMessage("Browser mode detected. Start the backend manually or launch the full Tauri desktop app.");
        }

        await waitForBackend(nextRuntime.baseUrl);
        if (!active) {
          return;
        }
        setBackendReady(true);
        setInfoMessage(
          nextRuntime.mode === "browser"
            ? "Browser mode connected to the manual backend. You can now preview and export stimuli."
            : "Backend ready. Configure a deterministic stimulus and sample the preview.",
        );
      } catch (error) {
        if (!active) {
          return;
        }
        const fallbackMessage =
          detectedMode === "browser"
            ? "Browser mode could not reach http://127.0.0.1:8765. Start `python3 backend/main.py --host 127.0.0.1 --port 8765` or use `npm run tauri:dev`."
            : "Failed to start the backend.";
        const nextMessage = error instanceof Error ? error.message : fallbackMessage;
        setErrorMessage(
          detectedMode === "browser" && nextMessage === "The packaged backend did not become ready in time."
            ? fallbackMessage
            : nextMessage,
        );
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

  useEffect(() => {
    if (!runtime || !backendReady) {
      return;
    }

    const controller = new AbortController();
    const handle = window.setTimeout(async () => {
      try {
        setPreviewError(null);
        setPreviewMessage("Sampling deterministic preview…");
        const nextPreview = await fetchPreview(runtime.baseUrl, config, previewPhase, controller.signal);
        setPreview(nextPreview);
        setPreviewMessage(
          designMode
            ? "Design mode is paused on this layout snapshot."
            : "Preview sampled from the live simulation engine.",
        );
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setPreviewError(error instanceof Error ? error.message : "Unable to refresh preview.");
        setPreviewMessage("Preview unavailable.");
      }
    }, 140);

    return () => {
      controller.abort();
      window.clearTimeout(handle);
    };
  }, [backendReady, config, designMode, previewPhase, runtime]);

  const summaryRows = useMemo(
    () => [
      { label: "Model", value: config.model_type },
      { label: "Shoal", value: `${config.number_of_agents} agents` },
      { label: "Split", value: `${config.left_count} left / ${config.right_count} right` },
      { label: "Cluster", value: `${config.target_cluster_radius}px radius` },
      { label: "Layout", value: currentPresetLabel },
    ],
    [config, currentPresetLabel],
  );

  const previewMetrics = useMemo(
    () => [
      { label: "Phase", value: preview?.phase ?? previewPhase },
      {
        label: "Spread",
        value: typeof preview?.metrics.spread === "number" ? preview.metrics.spread.toFixed(1) : "--",
      },
      {
        label: "Avg speed",
        value: typeof preview?.metrics.avg_speed === "number" ? preview.metrics.avg_speed.toFixed(1) : "--",
      },
      {
        label: "Left count",
        value: typeof preview?.metrics.left_count === "number" ? String(preview.metrics.left_count) : String(config.left_count),
      },
      {
        label: "Right count",
        value: typeof preview?.metrics.right_count === "number" ? String(preview.metrics.right_count) : String(config.right_count),
      },
    ],
    [config.left_count, config.right_count, preview, previewPhase],
  );

  const updateConfigValue = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => {
    setConfig((current) => ({ ...current, [key]: value }));
  };

  const handleAgentCountChange = (nextValue: number) => {
    setConfig((current) => {
      const preservedShare = current.left_count / Math.max(current.number_of_agents, 1);
      return {
        ...current,
        ...rebalanceSplit(nextValue, Math.round(Math.max(nextValue, 2) * preservedShare)),
      };
    });
  };

  const handleLeftCountChange = (nextValue: number) => {
    setConfig((current) => ({
      ...current,
      ...rebalanceSplit(current.number_of_agents, nextValue),
    }));
  };

  const handleRightCountChange = (nextValue: number) => {
    setConfig((current) => ({
      ...current,
      ...rebalanceSplit(current.number_of_agents, current.number_of_agents - Math.round(nextValue)),
    }));
  };

  const handleResolutionChange = (dimension: "width" | "height", nextValue: number) => {
    setConfig((current) => {
      const nextWidth = dimension === "width" ? Math.max(160, Math.round(nextValue)) : current.output_width;
      const nextHeight = dimension === "height" ? Math.max(120, Math.round(nextValue)) : current.output_height;
      return scaleArenaLayout(current, nextWidth, nextHeight);
    });
  };

  const handleLayoutPresetChange = (nextPresetId: string) => {
    setLayoutPresetId(nextPresetId);
    setConfig((current) => applyLayoutPreset(current, nextPresetId));
  };

  const handleAttractorPlacement = (point: { x: number; y: number }) => {
    const xKey = attractorCoordinateKey(selectedAttractor, "x");
    const yKey = attractorCoordinateKey(selectedAttractor, "y");
    setLayoutPresetId("custom");
    setConfig((current) => ({
      ...current,
      [xKey]: point.x,
      [yKey]: point.y,
    }));
  };

  const handleDesignModeToggle = () => {
    setDesignMode((current) => {
      const nextValue = !current;
      if (nextValue) {
        setActiveTab("layout");
        setInfoMessage("Design mode active. Layout editing is isolated from rendering controls.");
      } else {
        setInfoMessage("Design mode off. Full parameter editing restored.");
      }
      return nextValue;
    });
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
    setInfoMessage("Applying device-aware recommendations…");

    try {
      const suggestion = await fetchOptimization(runtime.baseUrl, window.innerWidth, window.innerHeight);
      setConfig((current) => {
        const preservedShare = current.left_count / Math.max(current.number_of_agents, 1);
        const resized = scaleArenaLayout(current, suggestion.output_width, suggestion.output_height);
        return {
          ...resized,
          ...rebalanceSplit(suggestion.number_of_agents, Math.round(suggestion.number_of_agents * preservedShare)),
          fps: suggestion.fps,
        };
      });
      setInfoMessage(
        `Optimized for ${suggestion.cpu_cores} CPU cores, ${suggestion.ram_gb.toFixed(1)} GB RAM, and ${suggestion.recommended_parallel_jobs} parallel sweep workers.`,
      );
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unable to fetch optimized settings.");
    }
  };

  const lockedOutsideLayout = !backendReady || busy || designMode;

  return (
    <div className="min-h-screen px-4 py-4 text-[color:var(--ink)] md:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1640px] flex-col gap-5">
        <header className="panel-surface overflow-hidden rounded-[34px] px-6 py-6 md:px-8">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_420px]">
            <div className="relative">
              <p className="eyebrow">Collective Motion Stimulus Console</p>
              <h1 className="mt-3 max-w-4xl font-display text-4xl leading-[0.98] tracking-[-0.04em] text-[color:var(--ink)] md:text-6xl">
                Research-grade control over aggregation, stabilization, and deterministic split dynamics.
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-[color:var(--ink-muted)] md:text-base">
                Build reproducible MP4 stimuli with exact branch counts, seeded motion, and a dedicated layout lab for attractor placement before export.
              </p>
            </div>

            <div className="grid gap-4">
              <div className="status-panel">
                <div>
                  <p className="eyebrow text-[color:var(--ink-muted)]">Backend</p>
                  <p className="mt-2 text-lg font-semibold text-[color:var(--ink)]">
                    {errorMessage ? "Startup failed" : backendReady ? "Local engine online" : "Booting service"}
                  </p>
                  <p className="mt-2 text-sm text-[color:var(--ink-muted)]">{infoMessage}</p>
                </div>
                <span className={`status-pill ${errorMessage ? "bg-rose-100 text-rose-700" : backendReady ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                  {errorMessage ? "Error" : backendReady ? "Ready" : "Starting"}
                </span>
              </div>

              <div className="panel-soft flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  <div className={`toggle-ring ${designMode ? "toggle-ring-on" : ""}`}>
                    <button
                      aria-pressed={designMode}
                      className={`toggle-knob ${designMode ? "translate-x-6" : ""}`}
                      disabled={!backendReady || busy}
                      type="button"
                      onClick={handleDesignModeToggle}
                    />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-[color:var(--ink)]">Design mode</span>
                      <Tooltip content="Pauses the preview loop and locks the app into layout editing so attractor placement can be adjusted without changing the rest of the simulation." />
                    </div>
                    <p className="mt-1 text-xs uppercase tracking-[0.2em] text-[color:var(--ink-faint)]">
                      {designMode ? "Layout editing isolated" : "Full console unlocked"}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    className="action-button action-button-secondary"
                    disabled={!backendReady || busy}
                    onClick={handleAutoOptimize}
                  >
                    Auto optimize
                  </button>
                  <button
                    className="action-button"
                    disabled={!backendReady || busy || designMode}
                    onClick={handleGenerate}
                  >
                    {busy ? "Generating…" : "Generate MP4"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </header>

        <main className="grid gap-5 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
          <aside className="panel-surface flex flex-col rounded-[30px] p-4">
            <div className="space-y-2">
              {TAB_COPY.map((tab) => {
                const disabled = designMode && tab.id !== "layout";
                return (
                  <button
                    key={tab.id}
                    className={`tab-button ${activeTab === tab.id ? "tab-button-active" : ""}`}
                    disabled={disabled}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    <p className="text-sm font-semibold">{tab.title}</p>
                    <p className="mt-1 text-xs leading-5 opacity-70">{tab.description}</p>
                  </button>
                );
              })}
            </div>

            <div className="mt-5 panel-soft space-y-3">
              <p className="eyebrow text-[color:var(--ink-faint)]">Study Summary</p>
              {summaryRows.map((row) => (
                <div key={row.label} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-[color:var(--ink-muted)]">{row.label}</span>
                  <span className="text-right font-semibold text-[color:var(--ink)]">{row.value}</span>
                </div>
              ))}
            </div>
          </aside>

          <section className="flex flex-col gap-5">
            <div className="panel-surface rounded-[30px] p-5 md:p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="eyebrow">Live Preview</p>
                  <h2 className="mt-2 font-display text-3xl tracking-[-0.04em] text-[color:var(--ink)]">Layout lab and phase sampler</h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--ink-muted)]">
                    Preview is sampled from the deterministic backend so the layout panel reflects the real split logic and shoal constraints rather than a toy approximation.
                  </p>
                </div>

                <div className="flex flex-wrap gap-3">
                  <ToggleControl
                    checked={ghostAgentsEnabled}
                    disabled={!backendReady}
                    label="Ghost agents"
                    tooltip="Shows a sampled shoal snapshot so you can judge cohesion, spacing, and branch separation before committing to export."
                    onChange={setGhostAgentsEnabled}
                  />
                </div>
              </div>

              <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
                <StimulusPreview
                  config={config}
                  designMode={designMode}
                  ghostAgentsEnabled={ghostAgentsEnabled}
                  preview={preview}
                  selectedAttractor={selectedAttractor}
                  onPlaceAttractor={handleAttractorPlacement}
                />

                <div className="flex flex-col gap-4">
                  <div className="panel-soft">
                    <LabelRow
                      label="Preview phase"
                      tooltip="Samples a representative frame from the selected phase of the experiment so you can inspect convergence, stabilization, or the final branch geometry."
                    />
                    <div className="mt-3 flex flex-wrap gap-2">
                      {PREVIEW_PHASE_OPTIONS.map((option) => (
                        <button
                          key={option.id}
                          className={`chip-button ${previewPhase === option.id ? "chip-button-active" : ""}`}
                          disabled={!backendReady}
                          onClick={() => setPreviewPhase(option.id)}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="panel-soft">
                    <LabelRow
                      label="Preset layout"
                      tooltip="Applies a reproducible attractor arrangement in normalized arena coordinates. Presets change only the attractor geometry, not the motion seed or split counts."
                    />
                    <select
                      className="input-control mt-3"
                      disabled={!backendReady || busy}
                      value={layoutPresetId}
                      onChange={(event) => handleLayoutPresetChange(event.target.value)}
                    >
                      {layoutPresetId === "custom" && <option value="custom">Custom layout</option>}
                      {LAYOUT_PRESETS.map((preset) => (
                        <option key={preset.id} value={preset.id}>
                          {preset.name}
                        </option>
                      ))}
                    </select>
                    <p className="mt-3 text-sm leading-6 text-[color:var(--ink-muted)]">
                      {layoutPresetId === "custom"
                        ? "Attractor positions are currently hand-edited from the canvas."
                        : (LAYOUT_PRESETS.find((entry) => entry.id === layoutPresetId)?.description ?? "")}
                    </p>
                  </div>

                  <div className="panel-soft">
                    <LabelRow
                      label="Placement target"
                      tooltip="Selects which attractor the canvas click will update while design mode is active."
                    />
                    <div className="mt-3 flex flex-wrap gap-2">
                      {ATTRACTOR_OPTIONS.map((option) => (
                        <button
                          key={option.id}
                          className={`chip-button ${selectedAttractor === option.id ? "chip-button-active" : ""}`}
                          disabled={!backendReady || busy}
                          onClick={() => setSelectedAttractor(option.id)}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="panel-soft">
                    <p className="eyebrow text-[color:var(--ink-faint)]">Preview status</p>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--ink-muted)]">{previewMessage}</p>
                    {previewError && (
                      <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                        {previewError}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="panel-surface rounded-[30px] p-5 md:p-6">
              {activeTab === "dynamics" && (
                <fieldset disabled={lockedOutsideLayout} className={lockedOutsideLayout ? "opacity-55" : ""}>
                  <SectionHeader
                    title="Dynamics"
                    description="Tune the local interaction model, baseline speed, and deterministic seed. These controls govern how strongly the shoal behaves like a cohesive animal group instead of a loose particle cloud."
                  />
                  <div className="mt-5 grid gap-4 md:grid-cols-2">
                    <NumberField label="Random seed" tooltip="Sets the pseudo-random seed used for initialization and motion noise. The same seed and config reproduce the same video and exact split assignment." value={config.random_seed} min={0} step={1} onChange={(value) => updateConfigValue("random_seed", Math.max(0, Math.round(value)))} />
                    <SelectField label="Model type" tooltip="Selects the interaction model used underneath the shared integrator. All models respect the same phase schedule and exact left/right counts." value={config.model_type} options={MODEL_OPTIONS} onChange={(value) => updateConfigValue("model_type", value)} />
                    <NumberField label="Number of agents" tooltip="Sets the total shoal size in the arena. Left and right counts are automatically kept consistent with this total." value={config.number_of_agents} min={2} step={1} onChange={handleAgentCountChange} />
                    <NumberField label="Baseline speed" tooltip="Sets the nominal cruising speed away from attractors. The paradigm will still reduce speed near targets during stabilization and post-split settling." value={config.speed} min={20} step={1} onChange={(value) => updateConfigValue("speed", Math.max(20, value))} />
                    <NumberField label="Noise amplitude" tooltip="Controls correlated randomness in movement. Higher values increase disorder and weaken cluster stability, especially during stabilization." value={config.noise} min={0} max={2} step={0.01} onChange={(value) => updateConfigValue("noise", Math.max(0, value))} />
                    <NumberField label="Cohesion strength" tooltip="Controls how strongly agents are pulled toward nearby neighbors. Higher values produce tighter clusters." value={config.cohesion} min={0} max={4} step={0.01} onChange={(value) => updateConfigValue("cohesion", Math.max(0, value))} />
                    <NumberField label="Alignment strength" tooltip="Controls how strongly agents align their direction with neighbors. Higher values make each shoal travel as a coordinated unit." value={config.alignment} min={0} max={4} step={0.01} onChange={(value) => updateConfigValue("alignment", Math.max(0, value))} />
                    <NumberField label="Separation strength" tooltip="Controls short-range repulsion between neighbors. Higher values prevent overlap, but excessive separation can broaden the shoal." value={config.separation} min={0} max={4} step={0.01} onChange={(value) => updateConfigValue("separation", Math.max(0, value))} />
                  </div>
                </fieldset>
              )}

              {activeTab === "split" && (
                <fieldset disabled={lockedOutsideLayout} className={lockedOutsideLayout ? "opacity-55" : ""}>
                  <SectionHeader
                    title="Split Logic"
                    description="Specify exact branch membership and the constraints that keep each post-split shoal compact, legible, and biologically plausible."
                  />
                  <div className="mt-5 grid gap-4 md:grid-cols-2">
                    <NumberField label="Left count" tooltip="Exact number of agents assigned to the left branch during the split phase. The right count is automatically updated so the total remains valid." value={config.left_count} min={0} max={config.number_of_agents} step={1} onChange={handleLeftCountChange} />
                    <NumberField label="Right count" tooltip="Exact number of agents assigned to the right branch during the split phase. Adjusting this field updates the left count to preserve the total." value={config.right_count} min={0} max={config.number_of_agents} step={1} onChange={handleRightCountChange} />
                    <NumberField label="Time in center (s)" tooltip="Duration of the aggregation phase before the shoal transitions into stabilization. Longer values give the school more time to converge." value={config.time_in_center} min={0} step={0.1} onChange={(value) => updateConfigValue("time_in_center", Math.max(0, value))} />
                    <NumberField label="Time to split (s)" tooltip="Absolute time when the paradigm changes from center stabilization to left/right branch attraction." value={config.time_to_split} min={0.1} step={0.1} onChange={(value) => updateConfigValue("time_to_split", Math.max(0.1, value))} />
                    <NumberField label="Neighbor radius" tooltip="Maximum distance for social interactions. Lower values emphasize local shoaling and help prevent overextended, diffuse clusters." value={config.neighbor_radius} min={10} step={1} onChange={(value) => updateConfigValue("neighbor_radius", Math.max(10, value))} />
                    <NumberField label="Separation radius" tooltip="Distance at which repulsive steering engages. Smaller values let the cluster pack more tightly before separation pushes fish apart." value={config.separation_radius} min={2} step={1} onChange={(value) => updateConfigValue("separation_radius", Math.max(2, value))} />
                    <NumberField label="Target cluster radius" tooltip="Desired maximum radius around each active attractor. Agents beyond this boundary receive an additional smooth restoring force instead of a hard clamp." value={config.target_cluster_radius} min={24} step={1} onChange={(value) => updateConfigValue("target_cluster_radius", Math.max(24, value))} />
                    <NumberField label="Attractor strength" tooltip="Controls how strongly the active target pulls on each agent. Higher values speed convergence and sharpen branch commitment." value={config.attractor_strength} min={0} step={1} onChange={(value) => updateConfigValue("attractor_strength", Math.max(0, value))} />
                    <NumberField label="Rotation strength" tooltip="Controls tangential steering around attractors. Keep this low to preserve natural arcing motion without reintroducing split-phase orbiting." value={config.rotation_strength} min={0} step={1} onChange={(value) => updateConfigValue("rotation_strength", Math.max(0, value))} />
                  </div>
                </fieldset>
              )}

              {activeTab === "layout" && (
                <fieldset disabled={!backendReady || busy} className={!backendReady || busy ? "opacity-55" : ""}>
                  <SectionHeader
                    title="Layout Coordinates"
                    description="Refine exact attractor coordinates numerically after placing them on the preview canvas. Coordinates are stored directly in the config and therefore stay reproducible with the seed."
                  />
                  <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <NumberField label="Center X" tooltip="Horizontal position of the aggregation attractor in arena pixels." value={config.center_attractor_x} min={0} step={1} onChange={(value) => { setLayoutPresetId("custom"); updateConfigValue("center_attractor_x", Math.max(0, value)); }} />
                    <NumberField label="Center Y" tooltip="Vertical position of the aggregation attractor in arena pixels." value={config.center_attractor_y} min={0} step={1} onChange={(value) => { setLayoutPresetId("custom"); updateConfigValue("center_attractor_y", Math.max(0, value)); }} />
                    <div className="hidden xl:block" />
                    <NumberField label="Left X" tooltip="Horizontal position of the left split attractor in arena pixels." value={config.left_attractor_x} min={0} step={1} onChange={(value) => { setLayoutPresetId("custom"); updateConfigValue("left_attractor_x", Math.max(0, value)); }} />
                    <NumberField label="Left Y" tooltip="Vertical position of the left split attractor in arena pixels." value={config.left_attractor_y} min={0} step={1} onChange={(value) => { setLayoutPresetId("custom"); updateConfigValue("left_attractor_y", Math.max(0, value)); }} />
                    <div className="hidden xl:block" />
                    <NumberField label="Right X" tooltip="Horizontal position of the right split attractor in arena pixels." value={config.right_attractor_x} min={0} step={1} onChange={(value) => { setLayoutPresetId("custom"); updateConfigValue("right_attractor_x", Math.max(0, value)); }} />
                    <NumberField label="Right Y" tooltip="Vertical position of the right split attractor in arena pixels." value={config.right_attractor_y} min={0} step={1} onChange={(value) => { setLayoutPresetId("custom"); updateConfigValue("right_attractor_y", Math.max(0, value)); }} />
                  </div>
                </fieldset>
              )}

              {activeTab === "rendering" && (
                <fieldset disabled={lockedOutsideLayout} className={lockedOutsideLayout ? "opacity-55" : ""}>
                  <SectionHeader
                    title="Rendering"
                    description="Lock the exported stimulus duration, temporal resolution, and arena size. Layout coordinates are rescaled proportionally when you change the output resolution."
                  />
                  <div className="mt-5 grid gap-4 md:grid-cols-2">
                    <NumberField label="Duration (s)" tooltip="Final MP4 duration. Combined with FPS, this determines the total number of simulated frames." value={config.video_duration} min={0.1} step={0.1} onChange={(value) => updateConfigValue("video_duration", Math.max(0.1, value))} />
                    <NumberField label="FPS" tooltip="Frames per second for both simulation stepping and MP4 export. Higher values create smoother motion but increase compute time." value={config.fps} min={1} step={1} onChange={(value) => updateConfigValue("fps", Math.max(1, Math.round(value)))} />
                    <NumberField label="Output width" tooltip="Arena width in pixels. Attractor positions are scaled proportionally when this value changes." value={config.output_width} min={160} step={10} onChange={(value) => handleResolutionChange("width", value)} />
                    <NumberField label="Output height" tooltip="Arena height in pixels. Attractor positions are scaled proportionally when this value changes." value={config.output_height} min={120} step={10} onChange={(value) => handleResolutionChange("height", value)} />
                  </div>
                </fieldset>
              )}

              {activeTab === "appearance" && (
                <fieldset disabled={lockedOutsideLayout} className={lockedOutsideLayout ? "opacity-55" : ""}>
                  <SectionHeader
                    title="Appearance"
                    description="Choose the rendered geometry for each fish and the export surface color. These settings affect the MP4 presentation but not the underlying motion dynamics."
                  />
                  <div className="mt-5 grid gap-4 md:grid-cols-2">
                    <SelectField label="Shape" tooltip="Rendered body geometry for each agent in the output video and preview panel." value={config.shape} options={SHAPE_OPTIONS} onChange={(value) => updateConfigValue("shape", value)} />
                    <RangeField label="Size" tooltip="Visual size of each rendered fish shape in pixels. Larger values make the shoal easier to inspect at a distance." value={config.size} min={2} max={40} step={0.5} onChange={(value) => updateConfigValue("size", Math.max(2, value))} />
                    <TextField label="Background color" tooltip="Hex color used for the arena background in both the preview and exported MP4." value={config.background_color} onChange={(value) => updateConfigValue("background_color", value)} />
                  </div>
                </fieldset>
              )}

              {activeTab === "output" && (
                <fieldset disabled={!backendReady || busy || designMode} className={!backendReady || busy || designMode ? "opacity-55" : ""}>
                  <SectionHeader
                    title="Output"
                    description="Choose the export destination, then launch a headless deterministic render. Progress is tracked without blocking the desktop shell."
                  />
                  <div className="mt-5 space-y-4">
                    <TextField label="Output path" tooltip="Absolute or relative MP4 destination. Metadata is written beside the MP4 when JSON sidecar export is enabled." value={config.output_path} onChange={(value) => updateConfigValue("output_path", value)} />
                    <button
                      className="action-button w-full justify-center md:w-auto"
                      disabled={!backendReady || busy || designMode}
                      onClick={handleGenerate}
                    >
                      {busy ? "Generating stimulus…" : "Generate deterministic MP4"}
                    </button>
                  </div>
                </fieldset>
              )}
            </div>
          </section>

          <aside className="panel-surface flex flex-col gap-5 rounded-[30px] p-5">
            <div>
              <p className="eyebrow">Run Status</p>
              <h2 className="mt-2 font-display text-3xl tracking-[-0.04em] text-[color:var(--ink)]">
                {busy ? "Rendering stimulus" : "Console ready"}
              </h2>
              <p className="mt-2 text-sm leading-6 text-[color:var(--ink-muted)]">{infoMessage}</p>
              {errorMessage && (
                <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {errorMessage}
                </div>
              )}
            </div>

            <div className="status-panel-dark">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-white">Render progress</span>
                <span className="text-sm text-white/70">{progressValue}%</span>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-[color:var(--accent)] transition-all duration-300" style={{ width: `${progressValue}%` }} />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <StatTile label="Job" value={jobId ? jobId.slice(0, 8) : "--"} />
                <StatTile label="Phase" value={status?.phase ?? preview?.phase ?? "--"} />
                <StatTile label="ETA" value={status?.eta_seconds != null ? `${status.eta_seconds.toFixed(1)}s` : "--"} />
                <StatTile label="Status" value={status?.status ?? (backendReady ? "idle" : "booting")} />
              </div>
            </div>

            <div className="panel-soft">
              <p className="eyebrow text-[color:var(--ink-faint)]">Preview metrics</p>
              <div className="mt-4 space-y-3">
                {previewMetrics.map((metric) => (
                  <div key={metric.label} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-[color:var(--ink-muted)]">{metric.label}</span>
                    <span className="font-semibold text-[color:var(--ink)]">{metric.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-[color:var(--ink)]">Video preview</p>
                  <p className="text-xs text-[color:var(--ink-muted)]">The final MP4 is streamed back from the local backend after completion.</p>
                </div>
              </div>

              {previewUrl ? (
                <video
                  key={previewUrl}
                  className="aspect-video w-full rounded-[24px] border border-[color:var(--line-strong)] bg-slate-950 object-cover shadow-[0_18px_40px_rgba(15,33,46,0.14)]"
                  controls
                  preload="metadata"
                  src={previewUrl}
                />
              ) : (
                <div className="flex aspect-video items-center justify-center rounded-[24px] border border-dashed border-[color:var(--line-strong)] bg-white/60 text-sm text-[color:var(--ink-muted)]">
                  Generate a stimulus to inspect the final MP4 here.
                </div>
              )}

              <div className="mt-4 panel-soft text-sm text-[color:var(--ink-muted)]">
                <div className="flex justify-between gap-3">
                  <span>Output path</span>
                  <span className="max-w-[180px] truncate text-right font-semibold text-[color:var(--ink)]">
                    {(status?.output_path ?? config.output_path) || "--"}
                  </span>
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
      <p className="eyebrow">{title}</p>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ink-muted)]">{description}</p>
    </div>
  );
}

type LabelRowProps = {
  label: string;
  tooltip: string;
  value?: string;
};

function LabelRow({ label, tooltip, value }: LabelRowProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-[color:var(--ink)]">{label}</span>
        <Tooltip content={tooltip} />
      </div>
      {value && <span className="text-sm font-semibold text-[color:var(--ink-muted)]">{value}</span>}
    </div>
  );
}

type FieldChromeProps = {
  label: string;
  tooltip: string;
  valueText?: string;
  children: ReactNode;
};

function FieldChrome({ label, tooltip, valueText, children }: FieldChromeProps) {
  return (
    <div className="panel-soft">
      <LabelRow label={label} tooltip={tooltip} value={valueText} />
      <div className="mt-3">{children}</div>
    </div>
  );
}

type NumberFieldProps = {
  label: string;
  tooltip: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
};

function NumberField({ label, tooltip, value, onChange, min, max, step }: NumberFieldProps) {
  return (
    <FieldChrome label={label} tooltip={tooltip}>
      <input
        className="input-control"
        type="number"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(event) => {
          const nextValue = Number(event.target.value);
          if (Number.isFinite(nextValue)) {
            onChange(nextValue);
          }
        }}
      />
    </FieldChrome>
  );
}

type TextFieldProps = {
  label: string;
  tooltip: string;
  value: string;
  onChange: (value: string) => void;
};

function TextField({ label, tooltip, value, onChange }: TextFieldProps) {
  return (
    <FieldChrome label={label} tooltip={tooltip}>
      <input className="input-control" type="text" value={value} onChange={(event) => onChange(event.target.value)} />
    </FieldChrome>
  );
}

type SelectFieldProps = {
  label: string;
  tooltip: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
};

function SelectField({ label, tooltip, value, options, onChange }: SelectFieldProps) {
  return (
    <FieldChrome label={label} tooltip={tooltip}>
      <select className="input-control" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </FieldChrome>
  );
}

type RangeFieldProps = {
  label: string;
  tooltip: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
};

function RangeField({ label, tooltip, value, min, max, step, onChange }: RangeFieldProps) {
  return (
    <FieldChrome label={label} tooltip={tooltip} valueText={value.toFixed(1)}>
      <input
        className="slider-control"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </FieldChrome>
  );
}

type ToggleControlProps = {
  label: string;
  tooltip: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
};

function ToggleControl({ label, tooltip, checked, disabled, onChange }: ToggleControlProps) {
  return (
    <div className="flex items-center gap-3 rounded-full border border-[color:var(--line-strong)] bg-white/70 px-4 py-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-[color:var(--ink)]">{label}</span>
        <Tooltip content={tooltip} />
      </div>
      <button
        aria-pressed={checked}
        className={`toggle-ring ${checked ? "toggle-ring-on" : ""}`}
        disabled={disabled}
        type="button"
        onClick={() => onChange(!checked)}
      >
        <span className={`toggle-knob ${checked ? "translate-x-6" : ""}`} />
      </button>
    </div>
  );
}

type StatTileProps = {
  label: string;
  value: string;
};

function StatTile({ label, value }: StatTileProps) {
  return (
    <div className="rounded-2xl bg-white/8 px-3 py-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-white/45">{label}</p>
      <p className="mt-2 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

export default App;
