import { useEffect, useMemo, useRef, useState } from "react";

import type { PreviewResponse } from "../lib/api";
import type { AppConfig, AttractorKey } from "../lib/defaults";

type StimulusPreviewProps = {
  config: AppConfig;
  preview: PreviewResponse | null;
  designMode: boolean;
  ghostAgentsEnabled: boolean;
  playbackEnabled: boolean;
  selectedAttractor: AttractorKey;
  onPlaceAttractor: (point: { x: number; y: number }) => void;
};

const ATTRACTOR_STYLES: Record<AttractorKey, { label: string; fill: string; stroke: string }> = {
  center: { label: "Aggregation", fill: "rgba(19, 132, 122, 0.16)", stroke: "#13847A" },
  left: { label: "Left branch", fill: "rgba(26, 118, 255, 0.16)", stroke: "#1A76FF" },
  right: { label: "Right branch", fill: "rgba(219, 110, 63, 0.18)", stroke: "#DB6E3F" },
};

function StimulusPreview({
  config,
  preview,
  designMode,
  ghostAgentsEnabled,
  playbackEnabled,
  selectedAttractor,
  onPlaceAttractor,
}: StimulusPreviewProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);

  useEffect(() => {
    setFrameIndex(0);
  }, [preview]);

  useEffect(() => {
    if (!preview || designMode || !playbackEnabled || preview.frames.length <= 1) {
      return;
    }

    const intervalMs = Math.max(40, Math.round(1000 / Math.max(preview.preview_fps, 1)));
    const handle = window.setInterval(() => {
      setFrameIndex((current) => (current + 1) % preview.frames.length);
    }, intervalMs);

    return () => window.clearInterval(handle);
  }, [designMode, playbackEnabled, preview]);

  const activeFrame = useMemo(() => {
    if (!preview || preview.frames.length === 0) {
      return null;
    }
    if (designMode || !playbackEnabled) {
      return preview.frames[preview.frames.length - 1];
    }
    return preview.frames[Math.min(frameIndex, preview.frames.length - 1)];
  }, [designMode, frameIndex, playbackEnabled, preview]);

  const attractors = useMemo(
    () => ({
      center: {
        x: preview?.attractors.center?.x ?? config.center_attractor_x,
        y: preview?.attractors.center?.y ?? config.center_attractor_y,
      },
      left: {
        x: preview?.attractors.left?.x ?? config.left_attractor_x,
        y: preview?.attractors.left?.y ?? config.left_attractor_y,
      },
      right: {
        x: preview?.attractors.right?.x ?? config.right_attractor_x,
        y: preview?.attractors.right?.y ?? config.right_attractor_y,
      },
    }),
    [config, preview],
  );

  const handlePointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!designMode || !svgRef.current) {
      return;
    }
    const rect = svgRef.current.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * config.output_width;
    const y = ((event.clientY - rect.top) / rect.height) * config.output_height;
    onPlaceAttractor({ x, y });
  };

  return (
    <div className="preview-shell relative overflow-hidden rounded-[34px] border border-[color:var(--line-strong)] bg-[color:var(--panel-strong)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(19,132,122,0.16),transparent_42%),radial-gradient(circle_at_bottom_right,rgba(219,110,63,0.18),transparent_38%)]" />
      <svg
        ref={svgRef}
        className={`relative z-10 aspect-[16/10] w-full ${designMode ? "cursor-crosshair" : ""}`}
        viewBox={`0 0 ${config.output_width} ${config.output_height}`}
        onPointerDown={handlePointerDown}
      >
        <defs>
          <pattern id="preview-grid" width="64" height="64" patternUnits="userSpaceOnUse">
            <path d="M 64 0 L 0 0 0 64" fill="none" stroke="rgba(24,50,68,0.08)" strokeWidth="1" />
          </pattern>
        </defs>

        <rect fill={config.background_color} height={config.output_height} width={config.output_width} />
        <rect fill="url(#preview-grid)" height={config.output_height} width={config.output_width} />

        {(Object.entries(attractors) as Array<[AttractorKey, { x: number; y: number }]>).map(([key, point]) => {
          const style = ATTRACTOR_STYLES[key];
          const selected = designMode && selectedAttractor === key;
          return (
            <g key={key}>
              <circle
                cx={point.x}
                cy={point.y}
                fill={style.fill}
                r={config.target_cluster_radius}
                stroke={selected ? style.stroke : "transparent"}
                strokeDasharray={selected ? "10 10" : undefined}
                strokeWidth={selected ? 2.5 : 0}
              />
              <circle
                cx={point.x}
                cy={point.y}
                fill={selected ? style.stroke : style.fill}
                r={selected ? 11 : 9}
                stroke="#ffffff"
                strokeWidth={2}
              />
              <text
                fill={style.stroke}
                fontFamily="var(--font-ui)"
                fontSize="14"
                fontWeight="700"
                letterSpacing="1.2"
                textAnchor="middle"
                x={point.x}
                y={point.y - config.target_cluster_radius - 14}
              >
                {style.label}
              </text>
            </g>
          );
        })}

        {ghostAgentsEnabled &&
          activeFrame?.agents.map((agent, index) => (
            <g
              key={`${agent.group}-${index}`}
              className={!designMode ? "preview-agent" : undefined}
              transform={`translate(${agent.x} ${agent.y}) rotate(${(agent.heading * 180) / Math.PI})`}
            >
              {config.shape === "circle" ? (
                <circle
                  fill={groupColor(agent.group, preview?.phase ?? "center")}
                  opacity={0.92}
                  r={Math.max(4, config.size * 0.88)}
                  stroke="rgba(255,255,255,0.72)"
                  strokeWidth={0.8}
                />
              ) : (
                <path
                  d={shapePath(config.shape, config.size * 0.92)}
                  fill={groupColor(agent.group, preview?.phase ?? "center")}
                  opacity={0.92}
                  stroke="rgba(255,255,255,0.72)"
                  strokeWidth={0.8}
                />
              )}
            </g>
          ))}
      </svg>

      <div className="pointer-events-none absolute left-4 top-4 rounded-full border border-[color:var(--line-strong)] bg-white/88 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-[color:var(--ink-muted)] shadow-[0_12px_30px_rgba(15,33,46,0.12)] backdrop-blur">
        {designMode ? "Preview paused for layout editing" : playbackEnabled ? "Looping preview clip" : "Preview held"}
      </div>

      {activeFrame && (
        <div className="pointer-events-none absolute right-4 top-4 rounded-full border border-[color:var(--line-strong)] bg-white/88 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-[color:var(--ink-muted)] shadow-[0_12px_30px_rgba(15,33,46,0.12)] backdrop-blur">
          {activeFrame.time_seconds.toFixed(1)}s
        </div>
      )}

      {designMode && (
        <div className="pointer-events-none absolute bottom-4 left-4 rounded-full border border-[color:var(--line-strong)] bg-white/88 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-[color:var(--ink-muted)] shadow-[0_12px_30px_rgba(15,33,46,0.12)] backdrop-blur">
          Click to place the {ATTRACTOR_STYLES[selectedAttractor].label.toLowerCase()} target
        </div>
      )}
    </div>
  );
}

function groupColor(group: string, phase: string) {
  if (phase !== "split") {
    return "#4B6275";
  }
  if (group === "left") {
    return "#1A76FF";
  }
  if (group === "right") {
    return "#DB6E3F";
  }
  return "#4B6275";
}

function shapePath(shape: string, size: number) {
  if (shape === "square") {
    return `M ${size} ${size} L ${size} ${-size} L ${-size} ${-size} L ${-size} ${size} Z`;
  }
  if (shape === "arrow") {
    return [
      `M ${size * 1.4} 0`,
      `L ${size * 0.18} ${-size * 0.8}`,
      `L ${size * 0.06} ${-size * 0.32}`,
      `L ${-size} ${-size * 0.32}`,
      `L ${-size} ${size * 0.32}`,
      `L ${size * 0.06} ${size * 0.32}`,
      `L ${size * 0.18} ${size * 0.8}`,
      "Z",
    ].join(" ");
  }
  return [
    `M ${size * 1.42} 0`,
    `L ${-size * 0.94} ${-size * 0.74}`,
    `L ${-size * 0.34} 0`,
    `L ${-size * 0.94} ${size * 0.74}`,
    "Z",
  ].join(" ");
}

export default StimulusPreview;
