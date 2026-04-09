export type TabId = "dynamics" | "split" | "layout" | "rendering" | "appearance" | "output";
export type PreviewPhase = "center" | "stabilize" | "split";
export type AttractorKey = "center" | "left" | "right";

export type AppConfig = {
  random_seed: number;
  model_type: string;
  number_of_agents: number;
  left_count: number;
  right_count: number;
  noise: number;
  speed: number;
  cohesion: number;
  alignment: number;
  separation: number;
  neighbor_radius: number;
  separation_radius: number;
  target_cluster_radius: number;
  time_in_center: number;
  time_to_split: number;
  rotation_strength: number;
  attractor_strength: number;
  center_attractor_x: number;
  center_attractor_y: number;
  left_attractor_x: number;
  left_attractor_y: number;
  right_attractor_x: number;
  right_attractor_y: number;
  video_duration: number;
  fps: number;
  output_width: number;
  output_height: number;
  shape: string;
  size: number;
  background_color: string;
  output_path: string;
};

export type LayoutPreset = {
  id: string;
  name: string;
  description: string;
  positions: Record<AttractorKey, [number, number]>;
};

export const TAB_COPY: Array<{ id: TabId; title: string; description: string }> = [
  { id: "dynamics", title: "Dynamics", description: "Seeded motion model, crowd size, and shoal forces." },
  { id: "split", title: "Split Logic", description: "Exact branch counts, timing, and cluster discipline." },
  { id: "layout", title: "Layout Lab", description: "Interactive attractor placement and live preview sampling." },
  { id: "rendering", title: "Rendering", description: "Fixed stimulus duration, FPS, and arena resolution." },
  { id: "appearance", title: "Appearance", description: "Agent geometry and export surface styling." },
  { id: "output", title: "Output", description: "Destination path, progress tracking, and finished video review." },
];

export const MODEL_OPTIONS = [
  "Research Boids",
  "Vicsek Consensus",
  "Potential Field",
  "Hybrid Consensus",
];

export const SHAPE_OPTIONS = ["circle", "triangle", "square", "arrow"];

export const PREVIEW_PHASE_OPTIONS: Array<{ id: PreviewPhase; label: string }> = [
  { id: "center", label: "Aggregation" },
  { id: "stabilize", label: "Stabilization" },
  { id: "split", label: "Split" },
];

export const ATTRACTOR_OPTIONS: Array<{ id: AttractorKey; label: string }> = [
  { id: "center", label: "Center" },
  { id: "left", label: "Left" },
  { id: "right", label: "Right" },
];

export const LAYOUT_PRESETS: LayoutPreset[] = [
  {
    id: "symmetric-fork",
    name: "Symmetric Fork",
    description: "Balanced branches with a clean, interpretable upward split.",
    positions: {
      center: [0.5, 0.66],
      left: [0.31, 0.31],
      right: [0.69, 0.31],
    },
  },
  {
    id: "wide-fork",
    name: "Wide Fork",
    description: "Larger lateral separation for unmistakable branch identity.",
    positions: {
      center: [0.5, 0.68],
      left: [0.24, 0.29],
      right: [0.76, 0.29],
    },
  },
  {
    id: "tight-rise",
    name: "Tight Rise",
    description: "Compact post-split targets that emphasize shoal cohesion.",
    positions: {
      center: [0.5, 0.63],
      left: [0.37, 0.27],
      right: [0.63, 0.27],
    },
  },
  {
    id: "deep-climb",
    name: "Deep Climb",
    description: "Higher branch targets for a longer, more directional ascent.",
    positions: {
      center: [0.5, 0.71],
      left: [0.3, 0.2],
      right: [0.7, 0.2],
    },
  },
];

export const DEFAULT_LAYOUT_PRESET_ID = LAYOUT_PRESETS[0].id;

export const DEFAULT_CONFIG: AppConfig = {
  random_seed: 2024,
  model_type: "Hybrid Consensus",
  number_of_agents: 48,
  left_count: 24,
  right_count: 24,
  noise: 0.14,
  speed: 132,
  cohesion: 1.55,
  alignment: 1.28,
  separation: 1.18,
  neighbor_radius: 88,
  separation_radius: 24,
  target_cluster_radius: 78,
  time_in_center: 2.8,
  time_to_split: 5,
  rotation_strength: 18,
  attractor_strength: 210,
  center_attractor_x: 640,
  center_attractor_y: 475.2,
  left_attractor_x: 396.8,
  left_attractor_y: 223.2,
  right_attractor_x: 883.2,
  right_attractor_y: 223.2,
  video_duration: 10,
  fps: 60,
  output_width: 1280,
  output_height: 720,
  shape: "triangle",
  size: 12,
  background_color: "#F4FBFF",
  output_path: "",
};

export function clampCount(value: number, total: number): number {
  return Math.max(0, Math.min(total, Math.round(value)));
}

export function rebalanceSplit(totalAgents: number, desiredLeft: number): Pick<AppConfig, "number_of_agents" | "left_count" | "right_count"> {
  const total = Math.max(2, Math.round(totalAgents));
  const left = clampCount(desiredLeft, total);
  return {
    number_of_agents: total,
    left_count: left,
    right_count: total - left,
  };
}

export function applyLayoutPreset(config: AppConfig, presetId: string): AppConfig {
  const preset = LAYOUT_PRESETS.find((entry) => entry.id === presetId) ?? LAYOUT_PRESETS[0];
  const { output_width, output_height } = config;
  return {
    ...config,
    center_attractor_x: output_width * preset.positions.center[0],
    center_attractor_y: output_height * preset.positions.center[1],
    left_attractor_x: output_width * preset.positions.left[0],
    left_attractor_y: output_height * preset.positions.left[1],
    right_attractor_x: output_width * preset.positions.right[0],
    right_attractor_y: output_height * preset.positions.right[1],
  };
}

export function scaleArenaLayout(config: AppConfig, nextWidth: number, nextHeight: number): AppConfig {
  const currentWidth = Math.max(config.output_width, 1);
  const currentHeight = Math.max(config.output_height, 1);
  const widthRatio = nextWidth / currentWidth;
  const heightRatio = nextHeight / currentHeight;

  return {
    ...config,
    output_width: nextWidth,
    output_height: nextHeight,
    center_attractor_x: config.center_attractor_x * widthRatio,
    center_attractor_y: config.center_attractor_y * heightRatio,
    left_attractor_x: config.left_attractor_x * widthRatio,
    left_attractor_y: config.left_attractor_y * heightRatio,
    right_attractor_x: config.right_attractor_x * widthRatio,
    right_attractor_y: config.right_attractor_y * heightRatio,
  };
}

export function attractorCoordinateKey(attractor: AttractorKey, axis: "x" | "y"): keyof AppConfig {
  if (attractor === "center") {
    return axis === "x" ? "center_attractor_x" : "center_attractor_y";
  }
  if (attractor === "left") {
    return axis === "x" ? "left_attractor_x" : "left_attractor_y";
  }
  return axis === "x" ? "right_attractor_x" : "right_attractor_y";
}
