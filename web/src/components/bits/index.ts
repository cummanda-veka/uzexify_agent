import type { ComponentType } from "react";
import GradientASCIIRaw from "./GradientASCII";
import HalftoneMarkRaw from "./HalftoneMark";
import PromptBarRaw from "./PromptBar";
import RubberSegmentRaw from "./RubberSegment";
import ThoughtLineRaw from "./ThoughtLine";

// Vendored React Bits components are plain JS; give them explicit prop types here.
type Props = Record<string, unknown>;

export const GradientASCII =
  GradientASCIIRaw as unknown as ComponentType<Props>;
export const HalftoneMark = HalftoneMarkRaw as unknown as ComponentType<Props>;
export const ThoughtLine = ThoughtLineRaw as unknown as ComponentType<Props>;
export const RubberSegment = RubberSegmentRaw as unknown as ComponentType<{
  items: { value: string; label: string }[];
  value?: string;
  onChange?: (value: string, index: number) => void;
  trackColor?: string;
  thumbColor?: string;
  textColor?: string;
  activeTextColor?: string;
  size?: "sm" | "md" | "lg";
  radius?: number;
  inset?: number;
  className?: string;
  "aria-label"?: string;
}>;
export const PromptBar = PromptBarRaw as unknown as ComponentType<{
  placeholder?: string;
  busy?: boolean;
  onSend?: (text: string) => void;
  onStop?: () => void;
  labels?: { prompt: string; send: string; stop: string };
  background?: string;
  color?: string;
  sparkColor?: string;
  width?: number;
  radius?: number;
  maxRows?: number;
  className?: string;
}>;
