export type AppConfig = {
  random_seed: number;
  model_type: string;
  number_of_agents: number;
  noise: number;
  cohesion: number;
  alignment: number;
  separation: number;
  split_ratio: number;
  time_in_center: number;
  time_to_split: number;
  rotation_strength: number;
  video_duration: number;
  fps: number;
  output_width: number;
  output_height: number;
  shape: string;
  size: number;
  attractor_strength: number;
  background_color: string;
  output_path: string;
};

export const MODEL_OPTIONS = [
  "Research Boids",
  "Vicsek Consensus",
  "Potential Field",
  "Hybrid Consensus",
];

export const SHAPE_OPTIONS = ["circle", "triangle", "square", "arrow"];

export const DEFAULT_CONFIG: AppConfig = {
  random_seed: 2024,
  model_type: "Hybrid Consensus",
  number_of_agents: 48,
  noise: 0.18,
  cohesion: 1.3,
  alignment: 1.05,
  separation: 1.65,
  split_ratio: 0.7,
  time_in_center: 2.8,
  time_to_split: 5,
  rotation_strength: 72,
  video_duration: 10,
  fps: 60,
  output_width: 1280,
  output_height: 720,
  shape: "triangle",
  size: 12,
  attractor_strength: 180,
  background_color: "#F4FBFF",
  output_path: "",
};
