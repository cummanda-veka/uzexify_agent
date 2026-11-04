import type { ComponentType, ReactNode } from "react";
import AnimatedListRaw from "./AnimatedList";
import CallChipRaw from "./CallChip";
import DecryptedTextRaw from "./DecryptedText";
import GradientASCIIRaw from "./GradientASCII";
import GradualBlurRaw from "./GradualBlur";
import HalftoneMarkRaw from "./HalftoneMark";
import LatticeLoaderRaw from "./LatticeLoader";
import PromptBarRaw from "./PromptBar";
import RubberSegmentRaw from "./RubberSegment";
import ThoughtLineRaw from "./ThoughtLine";

// Vendored React Bits components are plain JS; give them explicit prop types here.
type Props = Record<string, unknown>;
const typed = <P>(component: unknown) => component as ComponentType<P>;

export const GradientASCII = typed<Props>(GradientASCIIRaw);
export const HalftoneMark = typed<Props>(HalftoneMarkRaw);
export const GradualBlur = typed<Props>(GradualBlurRaw);
export const LatticeLoader = typed<{
  status?: "working" | "done" | "error";
  label?: string;
  doneLabel?: string;
  errorLabel?: string;
  pattern?: string;
  grid?: 3 | 4;
  shape?: "round" | "square";
  color?: string;
  doneColor?: string;
  errorColor?: string;
  cellSize?: number;
  gap?: number;
  fontSize?: number;
  step?: number;
  idleOpacity?: number;
  glow?: boolean;
  glowColor?: string;
  showTimer?: boolean;
  elapsed?: number;
  className?: string;
}>(LatticeLoaderRaw);
export const DecryptedText = typed<Props & { text: string }>(DecryptedTextRaw);
export const ThoughtLine = typed<Props & { steps?: ReactNode[] }>(
  ThoughtLineRaw,
);
export const CallChip = typed<{
  icon?: "terminal" | "file" | "search" | "edit";
  name: string;
  argument?: string;
  status: "running" | "done" | "error" | "idle";
  size?: number;
  surfaceColor?: string;
  color?: string;
  doneColor?: string;
  errorColor?: string;
  showTimer?: boolean;
}>(CallChipRaw);
export type ListItem = {
  icon?: ReactNode;
  title: string;
  description?: string;
  meta?: string;
};
export const AnimatedList = typed<
  Props & {
    items: ListItem[];
    onItemSelect?: (item: ListItem, index: number) => void;
  }
>(AnimatedListRaw);
export const RubberSegment = typed<{
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
}>(RubberSegmentRaw);
export const PromptBar = typed<{
  placeholder?: string;
  placeholders?: string[];
  placeholderPrefix?: string;
  busyPlaceholder?: string;
  rotateMs?: number;
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
}>(PromptBarRaw);
