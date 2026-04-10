import { startTransition, useDeferredValue, useEffect, useMemo, useState, type ReactNode } from "react";

import StimulusPreview from "./components/StimulusPreview";
import Tooltip from "./components/Tooltip";
import {
  cancelSimulation,
  fetchOptimization,
  fetchPreview,
  fetchStatus,
  startSimulation,
  stopSimulation,
  type PreviewResponse,
  type StatusResponse,
} from "./lib/api";
import {
  applyBehaviorPreset,
  applyLayoutPreset,
  attractorCoordinateKey,
  ATTRACTOR_OPTIONS,
  BEHAVIOR_PRESETS,
  CONTROL_SECTIONS,
  DEFAULT_CONFIG,
  DEFAULT_LAYOUT_PRESET_ID,
  formatParameterValue,
  getParameterWarning,
  LAYOUT_PRESETS,
  MODEL_OPTIONS,
  PARAMETER_SPECS,
  PREVIEW_PHASE_OPTIONS,
  rebalanceSplit,
  scaleArenaLayout,
  SHAPE_OPTIONS,
  type AppConfig,
  type AttractorKey,
  type ParameterGroupId,
  type ParameterSpec,
  type PreviewPhase,
} from "./lib/defaults";
import { getRuntimeInfo, waitForBackend, type RuntimeInfo } from "./lib/runtime";

const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "stopping", "cancelling"]);
const TERMINAL_VIDEO_STATUSES = new Set(["completed", "stopped"]);

function App() {
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [backendReady, setBackendReady] = useState(false);
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  const deferredConfig = useDeferredValue(config);

  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);

  const [previewPhase, setPreviewPhase] = useState<PreviewPhase>("split");
  const [previewNonce, setPreviewNonce] = useState(0);
  const [previewLoopEnabled, setPreviewLoopEnabled] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewMessage, setPreviewMessage] = useState("Waiting for the backend so preview can begin.");

  const [designMode, setDesignMode] = useState(false);
  const [advancedSettings, setAdvancedSettings] = useState(false);
  const [selectedAttractor, setSelectedAttractor] = useState<AttractorKey>("left");
  const [layoutPresetId, setLayoutPresetId] = useState(DEFAULT_LAYOUT_PRESET_ID);
  const [behaviorPresetId, setBehaviorPresetId] = useState<string>("clean-split");
  const [ghostAgentsEnabled, setGhostAgentsEnabled] = useState(true);

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState("Starting backend…");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const busy = status ? ACTIVE_JOB_STATUSES.has(status.status) : false;
  const canStop = status?.status === "queued" || status?.status === "running";
  const canCancel = status ? ACTIVE_JOB_STATUSES.has(status.status) : false;
  const controlsLocked = !backendReady || busy || designMode;
  const environmentLocked = !backendReady || busy;
  const progressValue = Math.round(status?.progress ?? 0);
  const currentLayoutLabel =
    layoutPresetId === "custom"
      ? "Custom layout"
      : (LAYOUT_PRESETS.find((preset) => preset.id === layoutPresetId)?.name ?? "Custom layout");
  const currentBehaviorPresetLabel =
    behaviorPresetId === "custom"
      ? "Custom tuning"
      : (BEHAVIOR_PRESETS.find((preset) => preset.id === behaviorPresetId)?.name ?? "Custom tuning");

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
            ? "Browser mode connected. Use the preview stage to inspect each setting before export."
            : "Backend ready. Preview updates automatically as you tune the stimulus.",
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
        startTransition(() => {
          setStatus(nextStatus);
        });

        if (nextStatus.status === "completed") {
          window.clearInterval(handle);
          setPreviewUrl(`${runtime.baseUrl}${nextStatus.video_url}?t=${Date.now()}`);
          setInfoMessage("Video complete. Final MP4 ready for inspection.");
        } else if (nextStatus.status === "stopped") {
          window.clearInterval(handle);
          setPreviewUrl(`${runtime.baseUrl}${nextStatus.video_url}?t=${Date.now()}`);
          setInfoMessage("Render stopped cleanly after the current frame. Partial MP4 is ready.");
        } else if (nextStatus.status === "cancelled") {
          window.clearInterval(handle);
          setPreviewUrl(null);
          setInfoMessage("Render cancelled. Partial output was cleared and the console is ready again.");
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
        setPreviewLoading(true);
        setPreviewError(null);
        setPreviewMessage("Sampling preview clip from the live simulation engine…");
        const nextPreview = await fetchPreview(runtime.baseUrl, deferredConfig, previewPhase, controller.signal);
        startTransition(() => {
          setPreview(nextPreview);
        });
        setPreviewLoopEnabled(true);
        setPreviewMessage(
          designMode
            ? "Design mode is active, so the preview is held on a paused layout frame."
            : "Preview clip is looping from the live deterministic engine.",
        );
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setPreviewError(error instanceof Error ? error.message : "Unable to refresh preview.");
        setPreviewMessage("Preview unavailable.");
      } finally {
        if (!controller.signal.aborted) {
          setPreviewLoading(false);
        }
      }
    }, 180);

    return () => {
      controller.abort();
      window.clearTimeout(handle);
    };
  }, [backendReady, deferredConfig, designMode, previewNonce, previewPhase, runtime]);

  const previewMetrics = useMemo(
    () => [
      { label: "Preview phase", value: humanizePhase(preview?.phase ?? previewPhase) },
      { label: "Preview fish", value: preview ? `${preview.preview_agent_count}` : "--" },
      {
        label: "Spread",
        value: typeof preview?.metrics.spread === "number" ? preview.metrics.spread.toFixed(1) : "--",
      },
      {
        label: "Average speed",
        value: typeof preview?.metrics.avg_speed === "number" ? preview.metrics.avg_speed.toFixed(1) : "--",
      },
      {
        label: "Left branch",
        value: `${config.left_count}`,
      },
      {
        label: "Right branch",
        value: `${config.right_count}`,
      },
    ],
    [config.left_count, config.right_count, preview, previewPhase],
  );

  const summaryRows = useMemo(
    () => [
      { label: "Motion model", value: config.model_type },
      { label: "Shoal plan", value: `${config.number_of_agents} fish` },
      { label: "Split plan", value: `${config.left_count} left / ${config.right_count} right` },
      { label: "Layout", value: currentLayoutLabel },
      { label: "Preset", value: currentBehaviorPresetLabel },
      { label: "Arena", value: `${config.output_width} x ${config.output_height}` },
    ],
    [config, currentBehaviorPresetLabel, currentLayoutLabel],
  );

  const localWarnings = useMemo(() => {
    const warnings = PARAMETER_SPECS.map((spec) => getParameterWarning(spec, Number(config[spec.key]))).filter(
      (warning): warning is string => Boolean(warning),
    );

    if (config.time_to_split - config.time_in_center < 0.75) {
      warnings.push("Stabilization time is very short, so the shoal may split before it looks settled.");
    }

    if (config.video_duration - config.time_to_split < 1.5) {
      warnings.push("The post-split observation window is short; consider extending the duration or starting the split earlier.");
    }

    if (Math.abs(config.right_attractor_x - config.left_attractor_x) < config.output_width * 0.18) {
      warnings.push("The left and right attractors are close together, which can reduce visual separation between the shoals.");
    }

    return uniqueStrings(warnings);
  }, [config]);

  const warnings = useMemo(
    () => uniqueStrings([...(preview?.warnings ?? []), ...localWarnings]),
    [localWarnings, preview?.warnings],
  );

  const updateConfigValue = <K extends keyof AppConfig>(
    key: K,
    value: AppConfig[K],
    options?: { markBehaviorCustom?: boolean; markLayoutCustom?: boolean },
  ) => {
    if (options?.markBehaviorCustom) {
      setBehaviorPresetId("custom");
    }
    if (options?.markLayoutCustom) {
      setLayoutPresetId("custom");
    }
    setConfig((current) => ({ ...current, [key]: value }));
  };

  const handleAgentCountChange = (nextValue: number) => {
    setBehaviorPresetId("custom");
    setConfig((current) => {
      const preservedShare = current.left_count / Math.max(current.number_of_agents, 1);
      return {
        ...current,
        ...rebalanceSplit(nextValue, Math.round(Math.max(nextValue, 2) * preservedShare)),
      };
    });
  };

  const handleLeftCountChange = (nextValue: number) => {
    setBehaviorPresetId("custom");
    setConfig((current) => ({
      ...current,
      ...rebalanceSplit(current.number_of_agents, nextValue),
    }));
  };

  const handleResolutionChange = (dimension: "width" | "height", nextValue: number) => {
    setConfig((current) => {
      const nextWidth = dimension === "width" ? Math.max(640, Math.round(nextValue)) : current.output_width;
      const nextHeight = dimension === "height" ? Math.max(360, Math.round(nextValue)) : current.output_height;
      return scaleArenaLayout(current, nextWidth, nextHeight);
    });
  };

  const handleTimeInCenterChange = (nextValue: number) => {
    setBehaviorPresetId("custom");
    setConfig((current) => {
      const timeInCenter = Math.max(0.5, nextValue);
      const minimumSplitTime = timeInCenter + 0.6;
      return {
        ...current,
        time_in_center: timeInCenter,
        time_to_split: Math.max(current.time_to_split, minimumSplitTime),
      };
    });
  };

  const handleTimeToSplitChange = (nextValue: number) => {
    setBehaviorPresetId("custom");
    setConfig((current) => ({
      ...current,
      time_to_split: Math.max(current.time_in_center + 0.6, nextValue),
    }));
  };

  const handleVideoDurationChange = (nextValue: number) => {
    setConfig((current) => {
      const videoDuration = Math.max(3, nextValue);
      return {
        ...current,
        video_duration: videoDuration,
        time_to_split: Math.min(current.time_to_split, Math.max(current.time_in_center + 0.6, videoDuration - 0.8)),
      };
    });
  };

  const handleLayoutPresetChange = (nextPresetId: string) => {
    setLayoutPresetId(nextPresetId);
    setConfig((current) => applyLayoutPreset(current, nextPresetId));
  };

  const handleBehaviorPresetChange = (nextPresetId: string) => {
    setBehaviorPresetId(nextPresetId);
    setConfig((current) => applyBehaviorPreset(current, nextPresetId));
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
      setPreviewLoopEnabled(!nextValue);
      setInfoMessage(
        nextValue
          ? "Design mode is active. Preview playback is paused and only layout editing remains enabled."
          : "Design mode is off. Full parameter editing and preview playback have resumed.",
      );
      return nextValue;
    });
  };

  const handleSeePreview = () => {
    setPreviewLoopEnabled(true);
    setPreviewNonce((current) => current + 1);
    setPreviewMessage("Sampling a fresh preview clip…");
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
      setInfoMessage("Rendering started. You can stop gracefully or cancel immediately from the run panel.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to start simulation.");
    }
  };

  const handleStop = async () => {
    if (!runtime || !jobId) {
      return;
    }
    setErrorMessage(null);
    try {
      const nextStatus = await stopSimulation(runtime.baseUrl, jobId);
      setStatus(nextStatus);
      setInfoMessage("Stopping after the current frame. The partial MP4 will remain available.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to stop the simulation.");
    }
  };

  const handleCancel = async () => {
    if (!runtime || !jobId) {
      return;
    }
    setErrorMessage(null);
    try {
      const nextStatus = await cancelSimulation(runtime.baseUrl, jobId);
      setStatus(nextStatus);
      setPreviewUrl(null);
      setInfoMessage("Cancelling immediately and clearing partial output…");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to cancel the simulation.");
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
      setBehaviorPresetId("custom");
      setInfoMessage(
        `Optimized for ${suggestion.cpu_cores} CPU cores, ${suggestion.ram_gb.toFixed(1)} GB RAM, and ${suggestion.recommended_parallel_jobs} parallel sweep workers.`,
      );
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unable to fetch optimized settings.");
    }
  };

  const renderParameterField = (spec: ParameterSpec) => {
    if (spec.advanced && !advancedSettings) {
      return null;
    }

    const value = Number(config[spec.key]);
    const onChange = (nextValue: number) => {
      if (spec.key === "number_of_agents") {
        handleAgentCountChange(nextValue);
        return;
      }
      if (spec.key === "time_in_center") {
        handleTimeInCenterChange(nextValue);
        return;
      }
      if (spec.key === "time_to_split") {
        handleTimeToSplitChange(nextValue);
        return;
      }
      if (spec.key === "video_duration") {
        handleVideoDurationChange(nextValue);
        return;
      }
      if (spec.key === "output_width") {
        handleResolutionChange("width", nextValue);
        return;
      }
      if (spec.key === "output_height") {
        handleResolutionChange("height", nextValue);
        return;
      }
      updateConfigValue(spec.key, nextValue as AppConfig[typeof spec.key], {
        markBehaviorCustom: spec.group !== "rendering" && spec.group !== "environment",
      });
    };

    return (
      <ParameterSlider
        key={spec.key}
        disabled={spec.group === "environment" ? environmentLocked : controlsLocked}
        spec={spec}
        value={value}
        onChange={onChange}
      />
    );
  };

  const presetOptions = behaviorPresetId === "custom"
    ? [{ id: "custom", name: "Custom tuning", description: "Manual adjustments are active.", patch: {} }, ...BEHAVIOR_PRESETS]
    : BEHAVIOR_PRESETS;

  return (
    <div className="min-h-screen px-4 py-4 text-[color:var(--ink)] md:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1680px] flex-col gap-6">
        <header className="panel-surface overflow-hidden rounded-[36px] px-6 py-6 md:px-8 md:py-8">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_420px]">
            <div className="relative">
              <p className="eyebrow">Stimulus Design Console</p>
              <h1 className="mt-3 max-w-4xl font-display text-4xl leading-[0.98] tracking-[-0.04em] text-[color:var(--ink)] md:text-6xl">
                Make every setting visually interpretable before you export the experiment.
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-[color:var(--ink-muted)] md:text-base">
                This desktop console is tuned for lab users: preview-first controls, exact split counts, safe biological ranges,
                and clean stop or cancel handling for deterministic MP4 generation.
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
                <span className={`status-pill ${statusTone(errorMessage, backendReady)}`}>
                  {errorMessage ? "Error" : backendReady ? "Ready" : "Starting"}
                </span>
              </div>

              <div className="panel-soft flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-[color:var(--ink)]">Advanced Settings</span>
                    <Tooltip content="Shows expert-facing controls such as turning bias, interaction radii, and seed selection. Leave this off for a cleaner biology-first workflow." />
                  </div>
                  <p className="text-xs uppercase tracking-[0.22em] text-[color:var(--ink-faint)]">
                    {advancedSettings ? "Expert controls visible" : "Only essential controls visible"}
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <ToggleControl
                    checked={advancedSettings}
                    disabled={!backendReady || busy}
                    label="Advanced"
                    tooltip="Toggles expert-level controls that are hidden by default for non-specialist users."
                    onChange={setAdvancedSettings}
                  />
                  <button
                    className="action-button action-button-secondary"
                    disabled={!backendReady || busy}
                    onClick={handleAutoOptimize}
                  >
                    Optimize for this machine
                  </button>
                </div>
              </div>
            </div>
          </div>
        </header>

        <main className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <section className="flex flex-col gap-6">
            <div className="panel-surface rounded-[34px] p-5 md:p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="eyebrow">Real-Time Preview</p>
                  <h2 className="mt-2 font-display text-3xl tracking-[-0.04em] text-[color:var(--ink)]">
                    See what each change does before you render
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--ink-muted)]">
                    The preview stage loops a short clip from the real deterministic engine using a lighter preview configuration,
                    so model changes, split timing, and clustering controls stay visually interpretable while you work.
                  </p>
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    className="action-button action-button-secondary"
                    disabled={!backendReady}
                    onClick={handleSeePreview}
                  >
                    {previewLoading ? "Refreshing preview…" : "See Preview"}
                  </button>
                  <button
                    className="action-button"
                    disabled={!backendReady || busy || designMode}
                    onClick={handleGenerate}
                  >
                    Generate MP4
                  </button>
                </div>
              </div>

              <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
                <StimulusPreview
                  config={config}
                  designMode={designMode}
                  ghostAgentsEnabled={ghostAgentsEnabled}
                  playbackEnabled={previewLoopEnabled}
                  preview={preview}
                  selectedAttractor={selectedAttractor}
                  onPlaceAttractor={handleAttractorPlacement}
                />

                <div className="flex flex-col gap-4">
                  <div className="panel-soft">
                    <LabelRow
                      label="Preview Mode"
                      tooltip="Choose which phase of the paradigm to preview. Each mode loops a short clip focused on that part of the experiment."
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
                    <p className="mt-3 text-sm leading-6 text-[color:var(--ink-muted)]">
                      {PREVIEW_PHASE_OPTIONS.find((option) => option.id === previewPhase)?.description}
                    </p>
                  </div>

                  <div className="panel-soft">
                    <LabelRow
                      label="Preview Toggles"
                      tooltip="Turn on or off lightweight visual aids while you inspect the arena."
                    />
                    <div className="mt-3 flex flex-col gap-3">
                      <ToggleControl
                        checked={designMode}
                        disabled={!backendReady || busy}
                        label="Design Mode"
                        tooltip="Pauses preview playback and leaves only layout editing active so you can place attractors safely."
                        onChange={handleDesignModeToggle}
                      />
                      <ToggleControl
                        checked={ghostAgentsEnabled}
                        disabled={!backendReady}
                        label="Ghost Fish"
                        tooltip="Shows the preview fish positions on the arena so you can judge spread, cluster tightness, and branch separation."
                        onChange={setGhostAgentsEnabled}
                      />
                    </div>
                  </div>

                  <div className="panel-soft">
                    <LabelRow
                      label="Layout Preset"
                      tooltip="Applies a reproducible attractor arrangement. These presets change the geometry of the arena, not the seed or exact split counts."
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
                        ? "The attractors are currently hand-edited from the preview canvas."
                        : (LAYOUT_PRESETS.find((entry) => entry.id === layoutPresetId)?.description ?? "")}
                    </p>
                  </div>

                  <div className="panel-soft">
                    <LabelRow
                      label="Placement Target"
                      tooltip="Choose which attractor the next canvas click will update while design mode is active."
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
                      <div className="warning-box mt-3">
                        {previewError}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                {previewMetrics.map((metric) => (
                  <PreviewMetric key={metric.label} label={metric.label} value={metric.value} />
                ))}
              </div>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <SectionPanel
                description={CONTROL_SECTIONS.find((section) => section.id === "group-behavior")?.description ?? ""}
                disabled={controlsLocked}
                title="Group Behavior"
              >
                <SelectField
                  disabled={controlsLocked}
                  label="Motion Model"
                  tooltip="Selects the interaction model used underneath the shared integrator. The preview updates instantly so you can compare each model visually."
                  value={config.model_type}
                  options={MODEL_OPTIONS}
                  onChange={(value) => {
                    setBehaviorPresetId("custom");
                    updateConfigValue("model_type", value, { markBehaviorCustom: false });
                  }}
                />
                <div className="mt-4 grid gap-4">
                  {PARAMETER_SPECS.filter((spec) => spec.group === "group-behavior").map(renderParameterField)}
                </div>
              </SectionPanel>

              <SectionPanel
                description={CONTROL_SECTIONS.find((section) => section.id === "movement-noise")?.description ?? ""}
                disabled={controlsLocked}
                title="Movement Noise"
              >
                <div className="grid gap-4">
                  {PARAMETER_SPECS.filter((spec) => spec.group === "movement-noise").map(renderParameterField)}
                </div>
              </SectionPanel>

              <SectionPanel
                description={CONTROL_SECTIONS.find((section) => section.id === "splitting-control")?.description ?? ""}
                disabled={controlsLocked}
                title="Splitting Control"
              >
                <SplitBalanceField
                  disabled={controlsLocked}
                  leftCount={config.left_count}
                  rightCount={config.right_count}
                  totalAgents={config.number_of_agents}
                  onChange={handleLeftCountChange}
                />
                <div className="mt-4 grid gap-4">
                  {PARAMETER_SPECS.filter((spec) => spec.group === "splitting-control").map(renderParameterField)}
                </div>
              </SectionPanel>

              <SectionPanel
                description={CONTROL_SECTIONS.find((section) => section.id === "environment")?.description ?? ""}
                disabled={environmentLocked}
                title="Environment"
              >
                <div className="grid gap-4">
                  {PARAMETER_SPECS.filter((spec) => spec.group === "environment").map(renderParameterField)}
                  <CoordinateGrid
                    config={config}
                    disabled={environmentLocked}
                    onChange={(key, value) => updateConfigValue(key, value, { markLayoutCustom: true })}
                  />
                </div>
              </SectionPanel>

              <SectionPanel
                description={CONTROL_SECTIONS.find((section) => section.id === "rendering")?.description ?? ""}
                disabled={controlsLocked}
                title="Rendering"
              >
                <div className="grid gap-4">
                  {PARAMETER_SPECS.filter((spec) => spec.group === "rendering").map(renderParameterField)}
                  <SelectField
                    disabled={controlsLocked}
                    label="Marker Shape"
                    tooltip="Controls the rendered marker shape used in the preview and exported MP4."
                    value={config.shape}
                    options={SHAPE_OPTIONS}
                    onChange={(value) => updateConfigValue("shape", value, { markBehaviorCustom: false })}
                  />
                  <TextField
                    disabled={controlsLocked}
                    label="Arena Background"
                    tooltip="Sets the arena background color in both the preview panel and exported MP4."
                    value={config.background_color}
                    onChange={(value) => updateConfigValue("background_color", value, { markBehaviorCustom: false })}
                  />
                  <TextField
                    disabled={controlsLocked}
                    label="Output Path"
                    tooltip="Sets where the MP4 should be written. A metadata JSON file is written beside it when export completes."
                    value={config.output_path}
                    onChange={(value) => updateConfigValue("output_path", value, { markBehaviorCustom: false })}
                  />
                </div>
              </SectionPanel>
            </div>
          </section>

          <aside className="flex flex-col gap-5">
            <div className="panel-surface rounded-[30px] p-5">
              <p className="eyebrow">Quick Presets</p>
              <h2 className="mt-2 font-display text-3xl tracking-[-0.04em] text-[color:var(--ink)]">Start from a safe behavioral profile</h2>
              <p className="mt-2 text-sm leading-6 text-[color:var(--ink-muted)]">
                These presets give non-specialist users a strong starting point before they fine-tune the preview.
              </p>
              <div className="mt-4 grid gap-3">
                {presetOptions.map((preset) => (
                  <PresetButton
                    key={preset.id}
                    active={behaviorPresetId === preset.id}
                    description={preset.description}
                    disabled={!backendReady || busy || designMode}
                    label={preset.recommended ? `${preset.name} (Recommended)` : preset.name}
                    onClick={() => handleBehaviorPresetChange(preset.id)}
                  />
                ))}
              </div>
            </div>

            <div className="panel-surface rounded-[30px] p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="eyebrow">Run Control</p>
                  <h2 className="mt-2 font-display text-3xl tracking-[-0.04em] text-[color:var(--ink)]">
                    {busy ? "Rendering stimulus" : "Ready to export"}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--ink-muted)]">
                    Progress, phase, and interruption controls stay available throughout the export lifecycle.
                  </p>
                </div>
                <span className={`status-pill ${jobTone(status?.status)}`}>{humanizeJobStatus(status?.status ?? (backendReady ? "idle" : "booting"))}</span>
              </div>

              {errorMessage && <div className="warning-box mt-4">{errorMessage}</div>}

              <div className="status-panel-dark mt-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-white">Render progress</span>
                  <span className="text-sm text-white/70">{progressValue}%</span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-[color:var(--accent)] transition-all duration-300" style={{ width: `${progressValue}%` }} />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <StatTile label="Job" value={jobId ? jobId.slice(0, 8) : "--"} />
                  <StatTile label="Phase" value={humanizePhase(status?.phase)} />
                  <StatTile label="ETA" value={formatEta(status?.eta_seconds)} />
                  <StatTile label="State" value={humanizeJobStatus(status?.status ?? (backendReady ? "idle" : "booting"))} />
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  className="action-button"
                  disabled={!backendReady || busy || designMode}
                  onClick={handleGenerate}
                >
                  Generate MP4
                </button>
                <button
                  className="action-button action-button-secondary"
                  disabled={!canStop}
                  onClick={handleStop}
                >
                  Stop Gracefully
                </button>
                <button
                  className="action-button action-button-danger"
                  disabled={!canCancel}
                  onClick={handleCancel}
                >
                  Cancel Now
                </button>
              </div>
            </div>

            <div className="panel-surface rounded-[30px] p-5">
              <p className="eyebrow">Safety Notes</p>
              <h2 className="mt-2 font-display text-3xl tracking-[-0.04em] text-[color:var(--ink)]">Biological plausibility</h2>
              <p className="mt-2 text-sm leading-6 text-[color:var(--ink-muted)]">
                Warnings are non-blocking, but they flag settings that may make the motion harder to interpret in a real experiment.
              </p>
              <div className="mt-4 flex flex-col gap-3">
                {warnings.length > 0 ? (
                  warnings.map((warning) => (
                    <div key={warning} className="warning-card">
                      {warning}
                    </div>
                  ))
                ) : (
                  <div className="rounded-[22px] border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-800">
                    Current settings stay within the recommended operating ranges.
                  </div>
                )}
              </div>
            </div>

            <div className="panel-surface rounded-[30px] p-5">
              <p className="eyebrow">Study Summary</p>
              <div className="mt-4 space-y-3">
                {summaryRows.map((row) => (
                  <div key={row.label} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-[color:var(--ink-muted)]">{row.label}</span>
                    <span className="text-right font-semibold text-[color:var(--ink)]">{row.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel-surface rounded-[30px] p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="eyebrow">Video Preview</p>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--ink-muted)]">
                    Completed or gracefully stopped exports appear here without leaving the desktop app.
                  </p>
                </div>
              </div>

              {previewUrl && status?.status && TERMINAL_VIDEO_STATUSES.has(status.status) ? (
                <video
                  key={previewUrl}
                  className="mt-4 aspect-video w-full rounded-[24px] border border-[color:var(--line-strong)] bg-slate-950 object-cover shadow-[0_18px_40px_rgba(15,33,46,0.14)]"
                  controls
                  preload="metadata"
                  src={previewUrl}
                />
              ) : (
                <div className="mt-4 flex aspect-video items-center justify-center rounded-[24px] border border-dashed border-[color:var(--line-strong)] bg-white/60 text-sm text-[color:var(--ink-muted)]">
                  Generate or gracefully stop a stimulus to inspect the resulting MP4 here.
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

type SectionPanelProps = {
  title: string;
  description: string;
  disabled: boolean;
  children: ReactNode;
};

function SectionPanel({ title, description, disabled, children }: SectionPanelProps) {
  return (
    <fieldset className={`panel-surface rounded-[30px] p-5 md:p-6 ${disabled ? "opacity-55" : ""}`} disabled={disabled}>
      <p className="eyebrow">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[color:var(--ink-muted)]">{description}</p>
      <div className="mt-5">{children}</div>
    </fieldset>
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

type FieldShellProps = {
  label: string;
  tooltip: string;
  valueText?: string;
  warning?: string | null;
  children: ReactNode;
};

function FieldShell({ label, tooltip, valueText, warning, children }: FieldShellProps) {
  return (
    <div className="panel-soft">
      <LabelRow label={label} tooltip={tooltip} value={valueText} />
      <div className="mt-3">{children}</div>
      {warning && <p className="mt-3 text-sm leading-6 text-amber-700">{warning}</p>}
    </div>
  );
}

type ParameterSliderProps = {
  spec: ParameterSpec;
  value: number;
  disabled: boolean;
  onChange: (value: number) => void;
};

function ParameterSlider({ spec, value, disabled, onChange }: ParameterSliderProps) {
  const warning = getParameterWarning(spec, value);
  const safeStart = ((spec.recommended[0] - spec.min) / (spec.max - spec.min)) * 100;
  const safeEnd = ((spec.recommended[1] - spec.min) / (spec.max - spec.min)) * 100;

  return (
    <FieldShell label={spec.label} tooltip={spec.tooltip} valueText={formatParameterValue(spec, value)} warning={warning}>
      <div className="range-shell">
        <div className="range-track">
          <div className="range-safe-window" style={{ left: `${safeStart}%`, width: `${Math.max(0, safeEnd - safeStart)}%` }} />
        </div>
        <input
          className="slider-control"
          disabled={disabled}
          max={spec.max}
          min={spec.min}
          step={spec.step}
          type="range"
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.18em] text-[color:var(--ink-faint)]">
        <span>{formatParameterValue(spec, spec.min)}</span>
        <span>
          Recommended {formatParameterValue(spec, spec.recommended[0])} to {formatParameterValue(spec, spec.recommended[1])}
        </span>
        <span>{formatParameterValue(spec, spec.max)}</span>
      </div>
    </FieldShell>
  );
}

type SelectFieldProps = {
  label: string;
  tooltip: string;
  value: string;
  options: string[];
  disabled: boolean;
  onChange: (value: string) => void;
};

function SelectField({ label, tooltip, value, options, disabled, onChange }: SelectFieldProps) {
  return (
    <FieldShell label={label} tooltip={tooltip}>
      <select className="input-control" disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

type TextFieldProps = {
  label: string;
  tooltip: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
};

function TextField({ label, tooltip, value, disabled, onChange }: TextFieldProps) {
  return (
    <FieldShell label={label} tooltip={tooltip}>
      <input className="input-control" disabled={disabled} type="text" value={value} onChange={(event) => onChange(event.target.value)} />
    </FieldShell>
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
    <div className="flex items-center justify-between gap-3 rounded-[22px] border border-[color:var(--line-strong)] bg-white/72 px-4 py-3">
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

type SplitBalanceFieldProps = {
  totalAgents: number;
  leftCount: number;
  rightCount: number;
  disabled: boolean;
  onChange: (leftCount: number) => void;
};

function SplitBalanceField({ totalAgents, leftCount, rightCount, disabled, onChange }: SplitBalanceFieldProps) {
  return (
    <FieldShell
      label="Exact Split Size"
      tooltip="Controls the exact number of fish assigned to the left branch. The right branch updates automatically so the total always stays valid."
      valueText={`${leftCount} left / ${rightCount} right`}
    >
      <div className="range-shell">
        <div className="range-track">
          <div className="range-safe-window" style={{ left: "28%", width: "44%" }} />
        </div>
        <input
          className="slider-control"
          disabled={disabled}
          max={totalAgents}
          min={0}
          step={1}
          type="range"
          value={leftCount}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <PreviewMetric label="Left branch" value={`${leftCount} fish`} />
        <PreviewMetric label="Right branch" value={`${rightCount} fish`} />
      </div>
    </FieldShell>
  );
}

type CoordinateGridProps = {
  config: AppConfig;
  disabled: boolean;
  onChange: (key: keyof AppConfig, value: number) => void;
};

function CoordinateGrid({ config, disabled, onChange }: CoordinateGridProps) {
  const fields: Array<{ key: keyof AppConfig; label: string; tooltip: string }> = [
    { key: "center_attractor_x", label: "Center X", tooltip: "Horizontal position of the aggregation target in arena pixels." },
    { key: "center_attractor_y", label: "Center Y", tooltip: "Vertical position of the aggregation target in arena pixels." },
    { key: "left_attractor_x", label: "Left X", tooltip: "Horizontal position of the left branch target in arena pixels." },
    { key: "left_attractor_y", label: "Left Y", tooltip: "Vertical position of the left branch target in arena pixels." },
    { key: "right_attractor_x", label: "Right X", tooltip: "Horizontal position of the right branch target in arena pixels." },
    { key: "right_attractor_y", label: "Right Y", tooltip: "Vertical position of the right branch target in arena pixels." },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {fields.map((field) => (
        <FieldShell key={field.key} label={field.label} tooltip={field.tooltip} valueText={`${Math.round(Number(config[field.key]))}px`}>
          <input
            className="input-control"
            disabled={disabled}
            min={0}
            step={1}
            type="number"
            value={Number(config[field.key])}
            onChange={(event) => onChange(field.key, Number(event.target.value))}
          />
        </FieldShell>
      ))}
    </div>
  );
}

type PreviewMetricProps = {
  label: string;
  value: string;
};

function PreviewMetric({ label, value }: PreviewMetricProps) {
  return (
    <div className="metric-card">
      <p className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ink-faint)]">{label}</p>
      <p className="mt-2 text-lg font-semibold text-[color:var(--ink)]">{value}</p>
    </div>
  );
}

type PresetButtonProps = {
  label: string;
  description: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
};

function PresetButton({ label, description, active, disabled, onClick }: PresetButtonProps) {
  return (
    <button
      className={`preset-card ${active ? "preset-card-active" : ""}`}
      disabled={disabled}
      onClick={onClick}
    >
      <p className="text-left text-sm font-semibold text-[color:var(--ink)]">{label}</p>
      <p className="mt-2 text-left text-sm leading-6 text-[color:var(--ink-muted)]">{description}</p>
    </button>
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

function humanizePhase(phase?: string | null): string {
  if (!phase) {
    return "--";
  }
  if (phase === "center") {
    return "Aggregation";
  }
  if (phase === "stabilize") {
    return "Stabilization";
  }
  if (phase === "split") {
    return "Splitting";
  }
  return phase.charAt(0).toUpperCase() + phase.slice(1);
}

function humanizeJobStatus(status: string): string {
  if (status === "queued") {
    return "Queued";
  }
  if (status === "running") {
    return "Running";
  }
  if (status === "stopping") {
    return "Stopping";
  }
  if (status === "stopped") {
    return "Stopped";
  }
  if (status === "cancelling") {
    return "Cancelling";
  }
  if (status === "cancelled") {
    return "Cancelled";
  }
  if (status === "completed") {
    return "Completed";
  }
  if (status === "failed") {
    return "Failed";
  }
  if (status === "booting") {
    return "Booting";
  }
  return "Idle";
}

function formatEta(etaSeconds: number | null | undefined): string {
  if (etaSeconds == null) {
    return "--";
  }
  if (etaSeconds < 60) {
    return `${etaSeconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(etaSeconds / 60);
  const seconds = Math.round(etaSeconds % 60);
  return `${minutes}m ${seconds}s`;
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  return values.filter((value) => {
    if (seen.has(value)) {
      return false;
    }
    seen.add(value);
    return true;
  });
}

function statusTone(errorMessage: string | null, backendReady: boolean): string {
  if (errorMessage) {
    return "bg-rose-100 text-rose-700";
  }
  if (backendReady) {
    return "bg-emerald-100 text-emerald-700";
  }
  return "bg-amber-100 text-amber-700";
}

function jobTone(status?: string | null): string {
  if (status === "failed" || status === "cancelled") {
    return "bg-rose-100 text-rose-700";
  }
  if (status === "completed" || status === "stopped") {
    return "bg-emerald-100 text-emerald-700";
  }
  if (status === "running" || status === "queued" || status === "stopping" || status === "cancelling") {
    return "bg-amber-100 text-amber-700";
  }
  return "bg-slate-100 text-slate-700";
}

export default App;
