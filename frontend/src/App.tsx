import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

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
  type ParameterSpec,
  type PreviewPhase,
} from "./lib/defaults";
import { getRuntimeInfo, waitForBackend, type RuntimeInfo } from "./lib/runtime";

const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "stopping", "cancelling"]);
const TERMINAL_VIDEO_STATUSES = new Set(["completed", "stopped"]);
const MIN_STABILIZATION_WINDOW_SECONDS = 5;
const MIN_SPLIT_OBSERVATION_SECONDS = 10;

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

  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
      { label: "Schedule", value: `${formatClock(config.time_in_center)} / ${formatClock(config.time_to_split)} / ${formatClock(config.video_duration)}` },
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

    if (config.time_to_split - config.time_in_center < Math.max(MIN_STABILIZATION_WINDOW_SECONDS, config.video_duration * 0.08)) {
      warnings.push("Stabilization time is very short, so the shoal may split before it looks settled.");
    }

    if (config.video_duration - config.time_to_split < Math.max(MIN_SPLIT_OBSERVATION_SECONDS, config.video_duration * 0.12)) {
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
      const maxAggregationEnd = Math.max(
        5,
        current.video_duration - (MIN_STABILIZATION_WINDOW_SECONDS + MIN_SPLIT_OBSERVATION_SECONDS),
      );
      const timeInCenter = Math.min(maxAggregationEnd, Math.max(5, nextValue));
      const minimumSplitTime = timeInCenter + MIN_STABILIZATION_WINDOW_SECONDS;
      return {
        ...current,
        time_in_center: timeInCenter,
        time_to_split: Math.max(current.time_to_split, minimumSplitTime),
      };
    });
  };

  const handleTimeToSplitChange = (nextValue: number) => {
    setBehaviorPresetId("custom");
    setConfig((current) => {
      const minimumSplitTime = current.time_in_center + MIN_STABILIZATION_WINDOW_SECONDS;
      const maximumSplitTime = Math.max(minimumSplitTime, current.video_duration - MIN_SPLIT_OBSERVATION_SECONDS);
      return {
        ...current,
        time_to_split: Math.min(maximumSplitTime, Math.max(minimumSplitTime, nextValue)),
      };
    });
  };

  const handleVideoDurationChange = (nextValue: number) => {
    setConfig((current) => {
      const videoDuration = Math.max(60, Math.min(180, nextValue));
      const maxAggregationEnd = Math.max(
        5,
        videoDuration - (MIN_STABILIZATION_WINDOW_SECONDS + MIN_SPLIT_OBSERVATION_SECONDS),
      );
      const timeInCenter = Math.min(current.time_in_center, maxAggregationEnd);
      const minimumSplitTime = timeInCenter + MIN_STABILIZATION_WINDOW_SECONDS;
      const maximumSplitTime = Math.max(minimumSplitTime, videoDuration - MIN_SPLIT_OBSERVATION_SECONDS);
      return {
        ...current,
        video_duration: videoDuration,
        time_in_center: timeInCenter,
        time_to_split: Math.min(maximumSplitTime, Math.max(minimumSplitTime, current.time_to_split)),
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

  const handleExportConfig = () => {
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "fish-stimulus-config.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setInfoMessage("Saved the current configuration to fish-stimulus-config.json.");
  };

  const handleImportConfigFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-importing the same file name
    if (!file) {
      return;
    }
    try {
      const parsed = JSON.parse(await file.text());
      const source =
        parsed && typeof parsed === "object" && parsed.config && typeof parsed.config === "object"
          ? (parsed.config as Record<string, unknown>)
          : (parsed as Record<string, unknown>);

      setConfig((current) => {
        const next = { ...current };
        for (const key of Object.keys(DEFAULT_CONFIG) as Array<keyof AppConfig>) {
          const incoming = source[key as string];
          if (incoming === undefined || incoming === null) {
            continue;
          }
          if (typeof DEFAULT_CONFIG[key] === "number") {
            const numeric = Number(incoming);
            if (Number.isFinite(numeric)) {
              (next as Record<string, unknown>)[key] = numeric;
            }
          } else {
            (next as Record<string, unknown>)[key] = incoming;
          }
        }

        // Re-derive interdependent fields so an imported file can never land in
        // an invalid state (split counts, then the phase schedule windows).
        const balanced = rebalanceSplit(next.number_of_agents, next.left_count);
        const videoDuration = Math.max(60, Math.min(180, next.video_duration));
        const timeInCenter = Math.max(
          5,
          Math.min(next.time_in_center, videoDuration - (MIN_STABILIZATION_WINDOW_SECONDS + MIN_SPLIT_OBSERVATION_SECONDS)),
        );
        const timeToSplit = Math.max(
          timeInCenter + MIN_STABILIZATION_WINDOW_SECONDS,
          Math.min(next.time_to_split, videoDuration - MIN_SPLIT_OBSERVATION_SECONDS),
        );
        return {
          ...next,
          ...balanced,
          video_duration: videoDuration,
          time_in_center: timeInCenter,
          time_to_split: timeToSplit,
        };
      });

      setBehaviorPresetId("custom");
      setLayoutPresetId("custom");
      setErrorMessage(null);
      setInfoMessage(`Loaded configuration from ${file.name}.`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? `Could not load configuration: ${error.message}` : "Could not load the configuration file.",
      );
    }
  };

  const handleResetDefaults = () => {
    setConfig((current) => applyBehaviorPreset({ ...DEFAULT_CONFIG, output_path: current.output_path }, "clean-split"));
    setBehaviorPresetId("clean-split");
    setLayoutPresetId(DEFAULT_LAYOUT_PRESET_ID);
    setErrorMessage(null);
    setInfoMessage("Restored the recommended default configuration.");
  };

  const renderParameterField = (spec: ParameterSpec) => {
    if (spec.advanced && !advancedSettings) {
      return null;
    }

    let resolvedSpec = spec;
    if (spec.key === "time_in_center") {
      resolvedSpec = {
        ...spec,
        max: Math.max(5, Math.floor(config.video_duration - (MIN_STABILIZATION_WINDOW_SECONDS + MIN_SPLIT_OBSERVATION_SECONDS))),
      };
    } else if (spec.key === "time_to_split") {
      resolvedSpec = {
        ...spec,
        min: Math.ceil(config.time_in_center + MIN_STABILIZATION_WINDOW_SECONDS),
        max: Math.max(
          Math.ceil(config.time_in_center + MIN_STABILIZATION_WINDOW_SECONDS),
          Math.floor(config.video_duration - MIN_SPLIT_OBSERVATION_SECONDS),
        ),
      };
    }

    const value = Number(config[resolvedSpec.key]);
    const onChange = (nextValue: number) => {
      if (resolvedSpec.key === "number_of_agents") {
        handleAgentCountChange(nextValue);
        return;
      }
      if (resolvedSpec.key === "time_in_center") {
        handleTimeInCenterChange(nextValue);
        return;
      }
      if (resolvedSpec.key === "time_to_split") {
        handleTimeToSplitChange(nextValue);
        return;
      }
      if (resolvedSpec.key === "video_duration") {
        handleVideoDurationChange(nextValue);
        return;
      }
      if (resolvedSpec.key === "output_width") {
        handleResolutionChange("width", nextValue);
        return;
      }
      if (resolvedSpec.key === "output_height") {
        handleResolutionChange("height", nextValue);
        return;
      }
      updateConfigValue(resolvedSpec.key, nextValue as AppConfig[typeof resolvedSpec.key], {
        markBehaviorCustom: resolvedSpec.group !== "rendering" && resolvedSpec.group !== "environment",
      });
    };

    return (
      <ParameterSlider
        key={resolvedSpec.key}
        disabled={resolvedSpec.group === "environment" ? environmentLocked : controlsLocked}
        spec={resolvedSpec}
        value={value}
        onChange={onChange}
      />
    );
  };

  const presetOptions = behaviorPresetId === "custom"
    ? [{ id: "custom", name: "Custom tuning", description: "Manual adjustments are active.", patch: {} }, ...BEHAVIOR_PRESETS]
    : BEHAVIOR_PRESETS;

  const backendStatusLabel = errorMessage ? "Error" : backendReady ? "Ready" : "Starting";

  return (
    <div className="min-h-screen pb-12 text-[color:var(--ink)]">
      <input
        ref={fileInputRef}
        accept="application/json,.json"
        className="hidden"
        type="file"
        onChange={handleImportConfigFile}
      />

      <header className="top-bar">
        <div className="mx-auto flex max-w-[1640px] flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3 md:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[color:var(--accent)] font-display text-sm font-bold text-white">
              F
            </div>
            <div className="leading-tight">
              <h1 className="font-display text-[0.98rem] text-[color:var(--ink)]">Fish Stimulus Generator</h1>
              <p className="text-[11px] text-[color:var(--ink-faint)]">Deterministic shoaling stimulus console</p>
            </div>
          </div>

          <span className={`status-pill ${statusTone(errorMessage, backendReady)}`}>
            <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-current" />
            {backendStatusLabel}
          </span>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <label className="mr-1 flex items-center gap-2 text-sm text-[color:var(--ink-muted)]">
              <span>Advanced</span>
              <button
                aria-pressed={advancedSettings}
                className={`toggle-ring ${advancedSettings ? "toggle-ring-on" : ""}`}
                disabled={!backendReady || busy}
                type="button"
                onClick={() => setAdvancedSettings((current) => !current)}
              >
                <span className="toggle-knob" />
              </button>
            </label>
            <button className="action-button action-button-secondary action-button-sm" disabled={!backendReady || busy} onClick={handleAutoOptimize}>
              Optimize
            </button>
            <button className="action-button action-button-secondary action-button-sm" disabled={busy} onClick={handleExportConfig}>
              Save
            </button>
            <button className="action-button action-button-secondary action-button-sm" disabled={busy} onClick={() => fileInputRef.current?.click()}>
              Load
            </button>
            <button className="action-button action-button-secondary action-button-sm" disabled={!backendReady || busy} onClick={handleResetDefaults}>
              Reset
            </button>
            <button className="action-button" disabled={!backendReady || busy || designMode} onClick={handleGenerate}>
              Generate MP4
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto mt-5 grid max-w-[1640px] gap-5 px-4 md:px-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="flex min-w-0 flex-col gap-5">
          <div className="panel-surface p-4 md:p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="eyebrow">Real-time preview</p>
                <h2 className="mt-1 font-display text-lg text-[color:var(--ink)]">Inspect every change before you render</h2>
              </div>
              <div className="flex flex-wrap gap-2">
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
                <button className="action-button action-button-secondary action-button-sm" disabled={!backendReady} onClick={handleSeePreview}>
                  {previewLoading ? "Refreshing…" : "Refresh"}
                </button>
              </div>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
              <StimulusPreview
                config={config}
                designMode={designMode}
                ghostAgentsEnabled={ghostAgentsEnabled}
                playbackEnabled={previewLoopEnabled}
                preview={preview}
                selectedAttractor={selectedAttractor}
                onPlaceAttractor={handleAttractorPlacement}
              />

              <div className="flex flex-col gap-3">
                <div className="panel-soft">
                  <p className="text-sm leading-6 text-[color:var(--ink-muted)]">
                    {PREVIEW_PHASE_OPTIONS.find((option) => option.id === previewPhase)?.description}
                  </p>
                </div>

                <div className="panel-soft">
                  <LabelRow label="Preview aids" tooltip="Lightweight visual helpers while you inspect the arena." />
                  <div className="mt-3 flex flex-col gap-2.5">
                    <ToggleControl
                      checked={designMode}
                      disabled={!backendReady || busy}
                      label="Design mode"
                      tooltip="Pauses playback and leaves only layout editing active so you can click to place attractors."
                      onChange={handleDesignModeToggle}
                    />
                    <ToggleControl
                      checked={ghostAgentsEnabled}
                      disabled={!backendReady}
                      label="Ghost fish"
                      tooltip="Shows preview fish positions so you can judge spread, cluster tightness, and branch separation."
                      onChange={setGhostAgentsEnabled}
                    />
                  </div>
                </div>

                <div className="panel-soft">
                  <LabelRow label="Layout preset" tooltip="Applies a reproducible attractor arrangement. Changes geometry only — not the seed or split counts." />
                  <select
                    className="input-control mt-2.5"
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
                </div>

                <div className="panel-soft">
                  <LabelRow label="Placement target" tooltip="Which attractor the next canvas click updates while design mode is active." />
                  <div className="mt-2.5 flex flex-wrap gap-2">
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
                  <p className="text-xs leading-5 text-[color:var(--ink-muted)]">{previewMessage}</p>
                  {previewError && <div className="warning-box mt-2">{previewError}</div>}
                </div>
              </div>
            </div>

            <div className="mt-4 grid gap-2.5 sm:grid-cols-3 xl:grid-cols-6">
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
              <div className="mt-3 grid gap-3">
                {PARAMETER_SPECS.filter((spec) => spec.group === "group-behavior").map(renderParameterField)}
              </div>
            </SectionPanel>

            <SectionPanel
              description={CONTROL_SECTIONS.find((section) => section.id === "movement-noise")?.description ?? ""}
              disabled={controlsLocked}
              title="Movement Noise"
            >
              <div className="grid gap-3">
                {PARAMETER_SPECS.filter((spec) => spec.group === "movement-noise").map(renderParameterField)}
              </div>
            </SectionPanel>

            <SectionPanel
              description={CONTROL_SECTIONS.find((section) => section.id === "splitting-control")?.description ?? ""}
              disabled={controlsLocked}
              title="Splitting Control"
            >
              <PhaseScheduleCard
                aggregationEnd={config.time_in_center}
                disabled={controlsLocked}
                splitStart={config.time_to_split}
                videoEnd={config.video_duration}
                onAggregationEndChange={handleTimeInCenterChange}
                onSplitStartChange={handleTimeToSplitChange}
                onVideoEndChange={handleVideoDurationChange}
              />
              <div className="mt-3">
                <SplitBalanceField
                  disabled={controlsLocked}
                  leftCount={config.left_count}
                  rightCount={config.right_count}
                  totalAgents={config.number_of_agents}
                  onChange={handleLeftCountChange}
                />
              </div>
              <div className="mt-3 grid gap-3">
                {PARAMETER_SPECS
                  .filter((spec) => spec.group === "splitting-control" && !["time_in_center", "time_to_split"].includes(spec.key))
                  .map(renderParameterField)}
              </div>
            </SectionPanel>

            <SectionPanel
              description={CONTROL_SECTIONS.find((section) => section.id === "environment")?.description ?? ""}
              disabled={environmentLocked}
              title="Environment"
            >
              <div className="grid gap-3">
                {PARAMETER_SPECS.filter((spec) => spec.group === "environment").map(renderParameterField)}
                <CoordinateGrid
                  config={config}
                  disabled={environmentLocked}
                  onChange={(key, value) => updateConfigValue(key, value, { markLayoutCustom: true })}
                />
              </div>
            </SectionPanel>

            <SectionPanel
              className="lg:col-span-2"
              description={CONTROL_SECTIONS.find((section) => section.id === "rendering")?.description ?? ""}
              disabled={controlsLocked}
              title="Rendering"
            >
              <div className="grid gap-3 md:grid-cols-2">
                {PARAMETER_SPECS
                  .filter((spec) => spec.group === "rendering" && spec.key !== "video_duration")
                  .map(renderParameterField)}
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
                  className="md:col-span-2"
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

        <aside className="flex min-w-0 flex-col gap-5">
          <div className="panel-surface p-4 md:p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="eyebrow">Run control</p>
                <h2 className="mt-1 font-display text-lg text-[color:var(--ink)]">{busy ? "Rendering stimulus" : "Ready to export"}</h2>
              </div>
              <span className={`status-pill ${jobTone(status?.status)}`}>{humanizeJobStatus(status?.status ?? (backendReady ? "idle" : "booting"))}</span>
            </div>

            {errorMessage && <div className="warning-box mt-3">{errorMessage}</div>}

            <div className="status-panel-dark mt-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-white">Render progress</span>
                <span className="mono text-sm text-white/70">{progressValue}%</span>
              </div>
              <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-[color:var(--accent)] transition-all duration-300" style={{ width: `${progressValue}%` }} />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2.5 text-sm">
                <StatTile label="Job" value={jobId ? jobId.slice(0, 8) : "--"} />
                <StatTile label="Phase" value={humanizePhase(status?.phase)} />
                <StatTile label="ETA" value={formatEta(status?.eta_seconds)} />
                <StatTile label="State" value={humanizeJobStatus(status?.status ?? (backendReady ? "idle" : "booting"))} />
              </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <button className="action-button" disabled={!backendReady || busy || designMode} onClick={handleGenerate}>
                Generate MP4
              </button>
              <button className="action-button action-button-secondary" disabled={!canStop} onClick={handleStop}>
                Stop
              </button>
              <button className="action-button action-button-danger" disabled={!canCancel} onClick={handleCancel}>
                Cancel
              </button>
            </div>
            <p className="mt-3 text-xs leading-5 text-[color:var(--ink-muted)]">{infoMessage}</p>
          </div>

          <div className="panel-surface p-4 md:p-5">
            <p className="eyebrow">Quick presets</p>
            <h2 className="mt-1 font-display text-lg text-[color:var(--ink)]">Start from a safe profile</h2>
            <div className="mt-3 grid gap-2.5">
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

          <div className="panel-surface p-4 md:p-5">
            <p className="eyebrow">Biological plausibility</p>
            <div className="mt-3 flex flex-col gap-2.5">
              {warnings.length > 0 ? (
                warnings.map((warning) => (
                  <div key={warning} className="warning-card">
                    {warning}
                  </div>
                ))
              ) : (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800">
                  Current settings stay within the recommended operating ranges.
                </div>
              )}
            </div>
          </div>

          <div className="panel-surface p-4 md:p-5">
            <p className="eyebrow">Study summary</p>
            <div className="mt-3 space-y-2">
              {summaryRows.map((row) => (
                <div key={row.label} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-[color:var(--ink-muted)]">{row.label}</span>
                  <span className="mono text-right font-semibold text-[color:var(--ink)]">{row.value}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="panel-surface p-4 md:p-5">
            <p className="eyebrow">Video output</p>
            {previewUrl && status?.status && TERMINAL_VIDEO_STATUSES.has(status.status) ? (
              <video
                key={previewUrl}
                className="mt-3 aspect-video w-full rounded-lg border border-[color:var(--line-strong)] bg-slate-950 object-cover"
                controls
                preload="metadata"
                src={previewUrl}
              />
            ) : (
              <div className="mt-3 flex aspect-video items-center justify-center rounded-lg border border-dashed border-[color:var(--line-strong)] bg-[#fbfcfe] px-4 text-center text-sm text-[color:var(--ink-muted)]">
                Generate or gracefully stop a stimulus to inspect the resulting MP4 here.
              </div>
            )}
            <div className="mt-3 flex justify-between gap-3 text-sm">
              <span className="text-[color:var(--ink-muted)]">Output path</span>
              <span className="mono max-w-[200px] truncate text-right font-semibold text-[color:var(--ink)]">
                {(status?.output_path ?? config.output_path) || "--"}
              </span>
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
}

type SectionPanelProps = {
  title: string;
  description: string;
  disabled: boolean;
  className?: string;
  children: ReactNode;
};

function SectionPanel({ title, description, disabled, className, children }: SectionPanelProps) {
  return (
    <fieldset className={`panel-surface p-4 md:p-5 ${disabled ? "opacity-60" : ""} ${className ?? ""}`} disabled={disabled}>
      <p className="eyebrow">{title}</p>
      <p className="mt-1.5 text-sm leading-6 text-[color:var(--ink-muted)]">{description}</p>
      <div className="mt-4">{children}</div>
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
      {value && <span className="mono text-sm font-semibold text-[color:var(--ink-muted)]">{value}</span>}
    </div>
  );
}

type FieldShellProps = {
  label: string;
  tooltip: string;
  valueText?: string;
  warning?: string | null;
  className?: string;
  children: ReactNode;
};

function FieldShell({ label, tooltip, valueText, warning, className, children }: FieldShellProps) {
  return (
    <div className={`panel-soft ${className ?? ""}`}>
      <LabelRow label={label} tooltip={tooltip} value={valueText} />
      <div className="mt-2.5">{children}</div>
      {warning && <p className="mt-2.5 text-xs leading-5 text-amber-700">{warning}</p>}
    </div>
  );
}

const UNIT_SUFFIX: Record<NonNullable<ParameterSpec["unit"]>, string> = {
  agents: "fish",
  seconds: "s",
  pixels: "px",
  fps: "fps",
  seed: "",
};

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
  const precision = spec.precision ?? (spec.step >= 1 ? 0 : 2);
  const unitSuffix = spec.unit ? UNIT_SUFFIX[spec.unit] : "";

  const commit = (raw: number) => {
    if (!Number.isFinite(raw)) {
      return;
    }
    onChange(Math.min(spec.max, Math.max(spec.min, raw)));
  };

  return (
    <FieldShell label={spec.label} tooltip={spec.tooltip} warning={warning}>
      <div className="flex items-center gap-3">
        <div className="range-shell min-w-0 flex-1">
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
        <div className="flex items-center gap-1.5">
          <input
            className="value-input"
            disabled={disabled}
            max={spec.max}
            min={spec.min}
            step={spec.step}
            type="number"
            value={Number(value.toFixed(precision))}
            onChange={(event) => commit(Number(event.target.value))}
          />
          {unitSuffix && <span className="w-7 text-xs text-[color:var(--ink-faint)]">{unitSuffix}</span>}
        </div>
      </div>
      <div className="mono mt-2.5 flex items-center justify-between gap-3 text-[11px] text-[color:var(--ink-faint)]">
        <span>{formatParameterValue(spec, spec.min)}</span>
        <span>
          Rec. {formatParameterValue(spec, spec.recommended[0])}–{formatParameterValue(spec, spec.recommended[1])}
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
  className?: string;
  onChange: (value: string) => void;
};

function SelectField({ label, tooltip, value, options, disabled, className, onChange }: SelectFieldProps) {
  return (
    <FieldShell className={className} label={label} tooltip={tooltip}>
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
  className?: string;
  onChange: (value: string) => void;
};

function TextField({ label, tooltip, value, disabled, className, onChange }: TextFieldProps) {
  return (
    <FieldShell className={className} label={label} tooltip={tooltip}>
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
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[color:var(--line)] bg-white px-3 py-2.5">
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
        <span className="toggle-knob" />
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
      <div className="flex items-center gap-3">
        <div className="range-shell min-w-0 flex-1">
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
        <input
          className="value-input"
          disabled={disabled}
          max={totalAgents}
          min={0}
          step={1}
          type="number"
          value={leftCount}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2.5">
        <PreviewMetric label="Left branch" value={`${leftCount} fish`} />
        <PreviewMetric label="Right branch" value={`${rightCount} fish`} />
      </div>
    </FieldShell>
  );
}

type PhaseScheduleCardProps = {
  aggregationEnd: number;
  splitStart: number;
  videoEnd: number;
  disabled: boolean;
  onAggregationEndChange: (value: number) => void;
  onSplitStartChange: (value: number) => void;
  onVideoEndChange: (value: number) => void;
};

function PhaseScheduleCard({
  aggregationEnd,
  splitStart,
  videoEnd,
  disabled,
  onAggregationEndChange,
  onSplitStartChange,
  onVideoEndChange,
}: PhaseScheduleCardProps) {
  const stabilizationWindow = Math.max(0, splitStart - aggregationEnd);
  const splitWindow = Math.max(0, videoEnd - splitStart);
  const aggregationWidth = `${(aggregationEnd / Math.max(videoEnd, 1)) * 100}%`;
  const stabilizationWidth = `${(stabilizationWindow / Math.max(videoEnd, 1)) * 100}%`;
  const splitWidth = `${(splitWindow / Math.max(videoEnd, 1)) * 100}%`;

  return (
    <div className="panel-soft">
      <LabelRow
        label="Phase Schedule"
        tooltip="Choose the exact timestamps for when aggregation ends, when splitting begins, and when the video ends."
      />
      <div className="schedule-track mt-3">
        <div className="schedule-segment schedule-aggregation" style={{ width: aggregationWidth }}>
          Aggregation
        </div>
        <div className="schedule-segment schedule-stabilization" style={{ width: stabilizationWidth }}>
          Stabilize
        </div>
        <div className="schedule-segment schedule-split" style={{ width: splitWidth }}>
          Split
        </div>
      </div>
      <div className="mt-3 grid gap-2.5 md:grid-cols-3">
        <ScheduleInput
          disabled={disabled}
          label="Aggregation Ends"
          max={Math.max(5, Math.floor(videoEnd - (MIN_STABILIZATION_WINDOW_SECONDS + MIN_SPLIT_OBSERVATION_SECONDS)))}
          min={5}
          value={aggregationEnd}
          onChange={onAggregationEndChange}
        />
        <ScheduleInput
          disabled={disabled}
          label="Split Starts"
          max={Math.max(
            Math.ceil(aggregationEnd + MIN_STABILIZATION_WINDOW_SECONDS),
            Math.floor(videoEnd - MIN_SPLIT_OBSERVATION_SECONDS),
          )}
          min={Math.ceil(aggregationEnd + MIN_STABILIZATION_WINDOW_SECONDS)}
          value={splitStart}
          onChange={onSplitStartChange}
        />
        <ScheduleInput disabled={disabled} label="Video Ends" max={180} min={60} value={videoEnd} onChange={onVideoEndChange} />
      </div>
      <div className="mt-3 grid gap-2.5 md:grid-cols-3">
        <PreviewMetric label="Aggregation" value={formatClock(aggregationEnd)} />
        <PreviewMetric label="Stabilization" value={formatClock(stabilizationWindow)} />
        <PreviewMetric label="Split Observation" value={formatClock(splitWindow)} />
      </div>
    </div>
  );
}

type ScheduleInputProps = {
  label: string;
  value: number;
  min: number;
  max: number;
  disabled: boolean;
  onChange: (value: number) => void;
};

function ScheduleInput({ label, value, min, max, disabled, onChange }: ScheduleInputProps) {
  return (
    <div className="rounded-lg border border-[color:var(--line)] bg-white px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ink-faint)]">{label}</p>
      <div className="mt-2 flex items-center gap-2">
        <input
          className="input-control mono"
          disabled={disabled}
          max={max}
          min={min}
          step={1}
          type="number"
          value={Math.round(value)}
          onChange={(event) => {
            const nextValue = Number(event.target.value);
            if (Number.isFinite(nextValue)) {
              onChange(nextValue);
            }
          }}
        />
        <span className="text-sm font-semibold text-[color:var(--ink-muted)]">sec</span>
      </div>
    </div>
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
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {fields.map((field) => (
        <FieldShell key={field.key} label={field.label} tooltip={field.tooltip} valueText={`${Math.round(Number(config[field.key]))}px`}>
          <input
            className="input-control mono"
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
      <p className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ink-faint)]">{label}</p>
      <p className="mono mt-1.5 text-base font-semibold text-[color:var(--ink)]">{value}</p>
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
    <button className={`preset-card ${active ? "preset-card-active" : ""}`} disabled={disabled} onClick={onClick}>
      <p className="text-left text-sm font-semibold text-[color:var(--ink)]">{label}</p>
      <p className="mt-1 text-left text-xs leading-5 text-[color:var(--ink-muted)]">{description}</p>
    </button>
  );
}

type StatTileProps = {
  label: string;
  value: string;
};

function StatTile({ label, value }: StatTileProps) {
  return (
    <div className="rounded-lg bg-white/[0.06] px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-[0.16em] text-white/45">{label}</p>
      <p className="mono mt-1.5 text-sm font-semibold text-white">{value}</p>
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

function formatClock(seconds: number): string {
  const clamped = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(clamped / 60);
  const remainder = clamped % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
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
