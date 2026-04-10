export type PreviewPhase = "center" | "stabilize" | "split";
export type AttractorKey = "center" | "left" | "right";
export type ParameterGroupId =
  | "group-behavior"
  | "movement-noise"
  | "splitting-control"
  | "environment"
  | "rendering";

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

export type BehaviorPreset = {
  id: string;
  name: string;
  description: string;
  recommended?: boolean;
  patch: Partial<AppConfig>;
};

export type ControlSection = {
  id: ParameterGroupId;
  title: string;
  description: string;
};

export type NumericConfigKey = {
  [Key in keyof AppConfig]: AppConfig[Key] extends number ? Key : never;
}[keyof AppConfig];

export type ParameterSpec = {
  key: NumericConfigKey;
  group: ParameterGroupId;
  label: string;
  tooltip: string;
  min: number;
  max: number;
  step: number;
  recommended: [number, number];
  warning: string;
  advanced?: boolean;
  unit?: "agents" | "seconds" | "pixels" | "fps" | "seed";
  precision?: number;
};

export const CONTROL_SECTIONS: ControlSection[] = [
  {
    id: "group-behavior",
    title: "Group Behavior",
    description: "Set how strongly the fish hold together and move as a coherent shoal.",
  },
  {
    id: "movement-noise",
    title: "Movement Noise",
    description: "Control how much randomness and turning variation is visible in the motion.",
  },
  {
    id: "splitting-control",
    title: "Splitting Control",
    description: "Define exact branch membership, timing, and post-split compactness.",
  },
  {
    id: "environment",
    title: "Environment",
    description: "Place attractors in the arena and tune how far local interactions can reach.",
  },
  {
    id: "rendering",
    title: "Rendering",
    description: "Lock the exported stimulus duration, resolution, and display styling.",
  },
];

export const MODEL_OPTIONS = [
  "Research Boids",
  "Vicsek Consensus",
  "Potential Field",
  "Hybrid Consensus",
];

export const SHAPE_OPTIONS = ["circle", "triangle", "square", "arrow"];

export const PREVIEW_PHASE_OPTIONS: Array<{ id: PreviewPhase; label: string; description: string }> = [
  { id: "center", label: "Aggregation", description: "Shows convergence toward the shared center." },
  { id: "stabilize", label: "Stabilization", description: "Shows the clustered shoal holding position with low drift." },
  { id: "split", label: "Splitting", description: "Shows the left and right branches separating into stable groups." },
];

export const ATTRACTOR_OPTIONS: Array<{ id: AttractorKey; label: string }> = [
  { id: "center", label: "Center target" },
  { id: "left", label: "Left branch" },
  { id: "right", label: "Right branch" },
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

export const BEHAVIOR_PRESETS: BehaviorPreset[] = [
  {
    id: "clean-split",
    name: "Clean Split",
    description: "Recommended baseline for tight clustering, low drift, and crisp left/right separation.",
    recommended: true,
    patch: {
      noise: 0.1,
      speed: 132,
      cohesion: 1.78,
      alignment: 1.42,
      separation: 1.02,
      neighbor_radius: 78,
      separation_radius: 24,
      target_cluster_radius: 108,
      attractor_strength: 236,
      rotation_strength: 6,
      time_in_center: 2.8,
      time_to_split: 5,
      size: 14,
      shape: "circle",
    },
  },
  {
    id: "tight-shoal",
    name: "Tight Shoal",
    description: "Pushes the school into a compact, low-noise group with restrained micro-movement.",
    patch: {
      noise: 0.07,
      cohesion: 1.96,
      alignment: 1.55,
      separation: 0.94,
      neighbor_radius: 72,
      separation_radius: 26,
      target_cluster_radius: 96,
      attractor_strength: 248,
      rotation_strength: 4,
      size: 15,
      shape: "circle",
    },
  },
  {
    id: "loose-group",
    name: "Loose Group",
    description: "Keeps the school interpretable while allowing broader spacing and softer alignment.",
    patch: {
      noise: 0.18,
      cohesion: 1.16,
      alignment: 1.02,
      separation: 0.78,
      neighbor_radius: 102,
      separation_radius: 28,
      target_cluster_radius: 126,
      attractor_strength: 182,
      rotation_strength: 14,
      size: 14,
      shape: "circle",
    },
  },
  {
    id: "high-noise",
    name: "High Noise",
    description: "Intentionally disorderly motion for contrast conditions, but still within hard bounds.",
    patch: {
      noise: 0.28,
      cohesion: 1.22,
      alignment: 0.98,
      separation: 0.86,
      target_cluster_radius: 132,
      separation_radius: 28,
      attractor_strength: 192,
      rotation_strength: 18,
      size: 14,
      shape: "circle",
    },
  },
];

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
  target_cluster_radius: 104,
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
  shape: "circle",
  size: 14,
  background_color: "#F4FBFF",
  output_path: "",
};

export const PARAMETER_SPECS: ParameterSpec[] = [
  {
    key: "number_of_agents",
    group: "group-behavior",
    label: "Shoal Size",
    tooltip: "Controls how many fish are visible in the arena. Larger groups can feel denser, but too many agents can reduce interpretability.",
    min: 2,
    max: 160,
    step: 1,
    recommended: [16, 96],
    warning: "This shoal size may reduce biological interpretability or slow down preview feedback.",
    unit: "agents",
  },
  {
    key: "speed",
    group: "group-behavior",
    label: "Cruising Speed",
    tooltip: "Controls the baseline travel speed of the shoal away from attractors. Higher values make movement more urgent and directional.",
    min: 20,
    max: 220,
    step: 1,
    recommended: [80, 160],
    warning: "This speed may make the fish look unusually sluggish or overly ballistic.",
    unit: "pixels",
  },
  {
    key: "cohesion",
    group: "group-behavior",
    label: "Cohesion Strength",
    tooltip: "Controls how strongly agents are pulled toward nearby neighbors. Higher values produce tighter clusters.",
    min: 0,
    max: 4,
    step: 0.01,
    recommended: [1.1, 2.2],
    warning: "This cohesion level may produce either diffuse clouds or unnaturally compressed shoals.",
    precision: 2,
  },
  {
    key: "alignment",
    group: "group-behavior",
    label: "Alignment Strength",
    tooltip: "Controls how strongly agents align their heading with nearby neighbors. Higher values make the group move as a coordinated unit.",
    min: 0,
    max: 4,
    step: 0.01,
    recommended: [0.95, 1.8],
    warning: "This alignment level may weaken coordinated travel or make the shoal feel excessively rigid.",
    precision: 2,
  },
  {
    key: "separation",
    group: "group-behavior",
    label: "Spacing Protection",
    tooltip: "Controls short-range repulsion between neighbors. Higher values prevent overlap, but can broaden the shoal if pushed too far.",
    min: 0,
    max: 4,
    step: 0.01,
    recommended: [0.55, 1.5],
    warning: "This spacing protection may allow overlap or create an overly spread-out group.",
    precision: 2,
  },
  {
    key: "noise",
    group: "movement-noise",
    label: "Noise Level",
    tooltip: "Controls randomness in movement. Higher values increase disorder and reduce cluster stability.",
    min: 0,
    max: 0.8,
    step: 0.01,
    recommended: [0.04, 0.24],
    warning: "This noise level may produce non-biological jitter or unusually rigid motion.",
    precision: 2,
  },
  {
    key: "rotation_strength",
    group: "movement-noise",
    label: "Turning Bias",
    tooltip: "Controls tangential steering around attractors. Keep this low to preserve gentle arcs without reintroducing orbiting.",
    min: 0,
    max: 32,
    step: 0.5,
    recommended: [0, 22],
    warning: "This turning bias may reintroduce visible circling around attractors.",
    advanced: true,
  },
  {
    key: "time_in_center",
    group: "splitting-control",
    label: "Aggregation Time",
    tooltip: "Controls how long the fish spend converging toward the center before the stabilization period begins.",
    min: 0.5,
    max: 8,
    step: 0.1,
    recommended: [1.5, 4],
    warning: "This aggregation time may feel too rushed or unnecessarily prolonged.",
    unit: "seconds",
    precision: 1,
  },
  {
    key: "time_to_split",
    group: "splitting-control",
    label: "Split Start Time",
    tooltip: "Controls when the deterministic split begins. Later values leave more time for stabilization before the branches diverge.",
    min: 1,
    max: 12,
    step: 0.1,
    recommended: [3.2, 6.5],
    warning: "This split timing may leave too little time for stabilization or too little time to observe the final shoals.",
    unit: "seconds",
    precision: 1,
  },
  {
    key: "target_cluster_radius",
    group: "splitting-control",
    label: "Split Tightness",
    tooltip: "Controls the desired radius around each attractor after convergence. Lower values create tighter, more stable shoals.",
    min: 42,
    max: 180,
    step: 1,
    recommended: [86, 128],
    warning: "This split tightness may crowd larger dots together or create clusters that look unnecessarily broad.",
    unit: "pixels",
  },
  {
    key: "attractor_strength",
    group: "splitting-control",
    label: "Target Pull",
    tooltip: "Controls how strongly the active attractor pulls on each fish. Higher values speed convergence and sharpen branch commitment.",
    min: 0,
    max: 420,
    step: 1,
    recommended: [160, 280],
    warning: "This target pull may create weak convergence or overly mechanical steering.",
    unit: "pixels",
  },
  {
    key: "neighbor_radius",
    group: "environment",
    label: "Interaction Radius",
    tooltip: "Controls how far each fish senses nearby neighbors. Lower values emphasize local shoaling and help prevent overextended clusters.",
    min: 10,
    max: 180,
    step: 1,
    recommended: [48, 112],
    warning: "This interaction radius may make the shoal too fragmented or too diffuse.",
    advanced: true,
    unit: "pixels",
  },
  {
    key: "separation_radius",
    group: "environment",
    label: "Personal Space Radius",
    tooltip: "Controls the distance at which repulsive steering activates. Smaller values allow tighter packing before fish push apart.",
    min: 6,
    max: 56,
    step: 1,
    recommended: [18, 34],
    warning: "This personal space radius may allow overlap or widen the shoal more than intended.",
    advanced: true,
    unit: "pixels",
  },
  {
    key: "video_duration",
    group: "rendering",
    label: "Stimulus Duration",
    tooltip: "Controls the final MP4 duration. Longer videos allow more post-split settling, but increase compute time.",
    min: 3,
    max: 24,
    step: 0.1,
    recommended: [6, 16],
    warning: "This duration may be too short for interpretation or longer than needed for stimulus presentation.",
    unit: "seconds",
    precision: 1,
  },
  {
    key: "fps",
    group: "rendering",
    label: "Frame Rate",
    tooltip: "Controls temporal smoothness for both simulation stepping and MP4 export. Higher values look smoother but cost more compute time.",
    min: 12,
    max: 120,
    step: 1,
    recommended: [24, 60],
    warning: "This frame rate may reduce motion smoothness or create unnecessary compute cost.",
    unit: "fps",
  },
  {
    key: "output_width",
    group: "rendering",
    label: "Arena Width",
    tooltip: "Controls the output width in pixels. Attractor positions are scaled automatically when the arena size changes.",
    min: 640,
    max: 2560,
    step: 10,
    recommended: [960, 1920],
    warning: "This arena width may be too small for clean visibility or larger than most experiments need.",
    unit: "pixels",
  },
  {
    key: "output_height",
    group: "rendering",
    label: "Arena Height",
    tooltip: "Controls the output height in pixels. Attractor positions are scaled automatically when the arena size changes.",
    min: 360,
    max: 1440,
    step: 10,
    recommended: [540, 1080],
    warning: "This arena height may be too small for clean visibility or larger than most experiments need.",
    unit: "pixels",
  },
  {
    key: "size",
    group: "rendering",
    label: "Dot Size",
    tooltip: "Controls the rendered size of each fish marker. Larger values improve visibility, and the simulation also increases collision spacing to keep dots from overlapping.",
    min: 4,
    max: 32,
    step: 0.5,
    recommended: [12, 18],
    warning: "This dot size may make the shoal hard to read or visually overcrowded.",
    unit: "pixels",
    precision: 1,
  },
  {
    key: "random_seed",
    group: "rendering",
    label: "Random Seed",
    tooltip: "Controls the deterministic pseudo-random initialization used for motion noise and exact split assignment.",
    min: 0,
    max: 999999,
    step: 1,
    recommended: [0, 999999],
    warning: "Any seed is reproducible; change this only when you want a different but repeatable stimulus instance.",
    advanced: true,
    unit: "seed",
  },
];

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

export function applyBehaviorPreset(config: AppConfig, presetId: string): AppConfig {
  const preset = BEHAVIOR_PRESETS.find((entry) => entry.id === presetId);
  if (!preset) {
    return config;
  }
  return { ...config, ...preset.patch };
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

export function getParameterWarning(spec: ParameterSpec, value: number): string | null {
  if (value < spec.recommended[0] || value > spec.recommended[1]) {
    return spec.warning;
  }
  return null;
}

export function formatParameterValue(spec: ParameterSpec, value: number): string {
  const precision = spec.precision ?? (spec.step >= 1 ? 0 : 2);
  const formatted = value.toFixed(precision);

  if (spec.unit === "seconds") {
    return `${formatted}s`;
  }
  if (spec.unit === "fps") {
    return `${formatted} fps`;
  }
  if (spec.unit === "agents") {
    return `${Math.round(value)} fish`;
  }
  if (spec.unit === "seed") {
    return `${Math.round(value)}`;
  }
  if (spec.unit === "pixels") {
    return `${formatted}px`;
  }
  return formatted;
}
