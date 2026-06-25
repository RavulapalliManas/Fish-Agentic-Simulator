import { useCallback, useEffect, useRef } from "react";

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
  center: { label: "Aggregation", fill: "rgba(37, 99, 235, 0.12)", stroke: "#1d4ed8" },
  left: { label: "Left branch", fill: "rgba(37, 99, 235, 0.12)", stroke: "#2563eb" },
  right: { label: "Right branch", fill: "rgba(210, 105, 63, 0.14)", stroke: "#d2693f" },
};

/**
 * Canvas-based arena preview. Rendering is driven by requestAnimationFrame and
 * reads the latest props from a ref, so playback advances without triggering a
 * React re-render per frame. This keeps the preview smooth on weak hardware.
 */
function StimulusPreview({
  config,
  preview,
  designMode,
  ghostAgentsEnabled,
  playbackEnabled,
  selectedAttractor,
  onPlaceAttractor,
}: StimulusPreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const timeBadgeRef = useRef<HTMLSpanElement | null>(null);

  // Latest props, read by the animation loop without re-subscribing each frame.
  const stateRef = useRef({ config, preview, designMode, ghostAgentsEnabled, playbackEnabled, selectedAttractor });
  stateRef.current = { config, preview, designMode, ghostAgentsEnabled, playbackEnabled, selectedAttractor };

  const frameRef = useRef(0);

  const paint = useCallback((frameIndex: number) => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    const { config: cfg, preview: pv, designMode: design, ghostAgentsEnabled: ghosts, selectedAttractor: selected } =
      stateRef.current;

    const arenaW = Math.max(1, cfg.output_width);
    const arenaH = Math.max(1, cfg.output_height);
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight;
    if (cssW === 0 || cssH === 0) {
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    const pixelW = Math.round(cssW * dpr);
    const pixelH = Math.round(cssH * dpr);
    if (canvas.width !== pixelW || canvas.height !== pixelH) {
      canvas.width = pixelW;
      canvas.height = pixelH;
    }

    // Map arena coordinates straight to displayed pixels (container matches arena
    // aspect ratio, so scaling is uniform and click mapping stays exact).
    ctx.setTransform((dpr * cssW) / arenaW, 0, 0, (dpr * cssH) / arenaH, 0, 0);
    const unit = arenaW / cssW; // ~1 displayed pixel in arena units, for hairlines

    // Background + grid.
    ctx.fillStyle = cfg.background_color || "#ffffff";
    ctx.fillRect(0, 0, arenaW, arenaH);

    ctx.lineWidth = unit;
    ctx.strokeStyle = "rgba(24, 50, 68, 0.06)";
    ctx.beginPath();
    for (let x = 0; x <= arenaW; x += 64) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, arenaH);
    }
    for (let y = 0; y <= arenaH; y += 64) {
      ctx.moveTo(0, y);
      ctx.lineTo(arenaW, y);
    }
    ctx.stroke();

    const attractors: Record<AttractorKey, { x: number; y: number }> = {
      center: {
        x: pv?.attractors.center?.x ?? cfg.center_attractor_x,
        y: pv?.attractors.center?.y ?? cfg.center_attractor_y,
      },
      left: {
        x: pv?.attractors.left?.x ?? cfg.left_attractor_x,
        y: pv?.attractors.left?.y ?? cfg.left_attractor_y,
      },
      right: {
        x: pv?.attractors.right?.x ?? cfg.right_attractor_x,
        y: pv?.attractors.right?.y ?? cfg.right_attractor_y,
      },
    };

    (Object.keys(attractors) as AttractorKey[]).forEach((key) => {
      const point = attractors[key];
      const style = ATTRACTOR_STYLES[key];
      const isSelected = design && selected === key;

      ctx.beginPath();
      ctx.arc(point.x, point.y, cfg.target_cluster_radius, 0, Math.PI * 2);
      ctx.fillStyle = style.fill;
      ctx.fill();
      if (isSelected) {
        ctx.lineWidth = 2.5 * unit;
        ctx.strokeStyle = style.stroke;
        ctx.setLineDash([10, 10]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      ctx.beginPath();
      ctx.arc(point.x, point.y, isSelected ? 11 : 9, 0, Math.PI * 2);
      ctx.fillStyle = isSelected ? style.stroke : style.fill;
      ctx.fill();
      ctx.lineWidth = 2 * unit;
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();

      ctx.fillStyle = style.stroke;
      ctx.font = `700 14px ${'"Inter Variable", system-ui, sans-serif'}`;
      ctx.textAlign = "center";
      ctx.fillText(style.label, point.x, point.y - cfg.target_cluster_radius - 12);
    });

    // Agents.
    const frames = pv?.frames ?? [];
    const frame = frames.length > 0 ? frames[Math.min(frameIndex, frames.length - 1)] : null;
    if (ghosts && frame) {
      const radius = Math.max(4, cfg.size * 0.88);
      ctx.lineWidth = 0.8 * unit;
      ctx.strokeStyle = "rgba(255, 255, 255, 0.72)";
      for (const agent of frame.agents) {
        ctx.save();
        ctx.translate(agent.x, agent.y);
        ctx.rotate(agent.heading);
        ctx.fillStyle = groupColor(agent.group, pv?.phase ?? "center");
        ctx.beginPath();
        if (cfg.shape === "circle") {
          ctx.arc(0, 0, radius, 0, Math.PI * 2);
        } else {
          tracePath(ctx, cfg.shape, cfg.size * 0.92);
        }
        ctx.fill();
        ctx.stroke();
        ctx.restore();
      }
    }

    if (timeBadgeRef.current) {
      timeBadgeRef.current.textContent = frame ? `${frame.time_seconds.toFixed(1)}s` : "--";
    }
  }, []);

  // Draw on any prop change; run a rAF loop only while actively playing.
  useEffect(() => {
    const frames = preview?.frames ?? [];
    const animating = Boolean(preview) && !designMode && playbackEnabled && frames.length > 1;

    if (!animating) {
      frameRef.current = Math.max(0, frames.length - 1);
      paint(frameRef.current);
      return;
    }

    const fps = Math.max(1, preview?.preview_fps ?? 24);
    let raf = 0;
    let start = 0;

    const tick = (timestamp: number) => {
      if (start === 0) {
        start = timestamp;
      }
      const elapsed = (timestamp - start) / 1000;
      frameRef.current = Math.floor(elapsed * fps) % frames.length;
      paint(frameRef.current);
      raf = window.requestAnimationFrame(tick);
    };

    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [config, preview, designMode, ghostAgentsEnabled, playbackEnabled, selectedAttractor, paint]);

  // Redraw on container resize.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => paint(frameRef.current));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [paint]);

  const handlePointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!designMode || !canvasRef.current) {
      return;
    }
    const rect = canvasRef.current.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * config.output_width;
    const y = ((event.clientY - rect.top) / rect.height) * config.output_height;
    onPlaceAttractor({ x, y });
  };

  return (
    <div className="preview-shell relative">
      <canvas
        ref={canvasRef}
        className={`block w-full ${designMode ? "cursor-crosshair" : ""}`}
        style={{ aspectRatio: `${config.output_width} / ${config.output_height}` }}
        onPointerDown={handlePointerDown}
      />

      <div className="pointer-events-none absolute left-3 top-3">
        <span className="preview-badge">
          {!designMode && playbackEnabled && <span className="pulse-dot" />}
          {designMode ? "Layout editing, paused" : playbackEnabled ? "Looping preview" : "Preview held"}
        </span>
      </div>

      <div className="pointer-events-none absolute right-3 top-3">
        <span ref={timeBadgeRef} className="preview-badge mono">
          --
        </span>
      </div>

      {designMode && (
        <div className="pointer-events-none absolute bottom-3 left-3">
          <span className="preview-badge">
            Click to place the {ATTRACTOR_STYLES[selectedAttractor].label.toLowerCase()} target
          </span>
        </div>
      )}
    </div>
  );
}

function groupColor(group: string, phase: string) {
  if (phase !== "split") {
    return "#4b6275";
  }
  if (group === "left") {
    return "#2563eb";
  }
  if (group === "right") {
    return "#d2693f";
  }
  return "#4b6275";
}

function tracePath(ctx: CanvasRenderingContext2D, shape: string, size: number) {
  if (shape === "square") {
    ctx.moveTo(size, size);
    ctx.lineTo(size, -size);
    ctx.lineTo(-size, -size);
    ctx.lineTo(-size, size);
    ctx.closePath();
    return;
  }
  if (shape === "arrow") {
    ctx.moveTo(size * 1.4, 0);
    ctx.lineTo(size * 0.18, -size * 0.8);
    ctx.lineTo(size * 0.06, -size * 0.32);
    ctx.lineTo(-size, -size * 0.32);
    ctx.lineTo(-size, size * 0.32);
    ctx.lineTo(size * 0.06, size * 0.32);
    ctx.lineTo(size * 0.18, size * 0.8);
    ctx.closePath();
    return;
  }
  // triangle (default)
  ctx.moveTo(size * 1.42, 0);
  ctx.lineTo(-size * 0.94, -size * 0.74);
  ctx.lineTo(-size * 0.34, 0);
  ctx.lineTo(-size * 0.94, size * 0.74);
  ctx.closePath();
}

export default StimulusPreview;
