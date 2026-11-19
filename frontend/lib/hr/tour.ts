import type {
  HrTourCompletionState,
  HrTourPlacement,
  HrTourStep,
} from "@/types/hr";

export const HR_TOUR_STORAGE_KEY = "rag-hr-product-tour:v1";

export interface HrStorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface TourRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export interface TourViewport {
  width: number;
  height: number;
}

export interface TourSize {
  width: number;
  height: number;
}

export interface SpotlightFrame {
  top: number;
  left: number;
  width: number;
  height: number;
}

export interface PopoverCoordinates {
  top: number;
  left: number;
  placement: HrTourPlacement;
}

export function readTourCompletionState(
  storage: Pick<HrStorageLike, "getItem"> | null | undefined,
): HrTourCompletionState | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(HR_TOUR_STORAGE_KEY);
    if (raw === "completed" || raw === "dismissed") return raw;
    return null;
  } catch {
    return null;
  }
}

export function writeTourCompletionState(
  storage: Pick<HrStorageLike, "setItem"> | null | undefined,
  state: HrTourCompletionState,
): void {
  if (!storage) return;
  try {
    storage.setItem(HR_TOUR_STORAGE_KEY, state);
  } catch {
    // Bỏ qua lỗi quota hoặc private browsing
  }
}

export function shouldAutoPromptHrTour(
  pathname: string,
  persistedState: HrTourCompletionState | null,
): boolean {
  return pathname === "/hr" && persistedState === null;
}

export function getTourProgressLabel(
  stepIndex: number,
  steps: readonly HrTourStep[],
): string {
  const total = steps.length;
  if (total === 0) return "0 / 0";
  const clamped = Math.min(Math.max(stepIndex + 1, 1), total);
  return `Bước ${clamped} / ${total}`;
}

export function getNextTourStepIndex(currentIndex: number, total: number): number | null {
  if (total <= 0) return null;
  return currentIndex + 1 < total ? currentIndex + 1 : null;
}

export function getPrevTourStepIndex(currentIndex: number): number | null {
  return currentIndex > 0 ? currentIndex - 1 : null;
}

export function computeSpotlightFrame(
  targetRect: TourRect | null,
  viewport: TourViewport,
  padding = 8,
): SpotlightFrame | null {
  if (!targetRect || targetRect.width <= 0 || targetRect.height <= 0) return null;

  const top = Math.max(8, targetRect.top - padding);
  const left = Math.max(8, targetRect.left - padding);
  const maxWidth = Math.max(40, viewport.width - left - 8);
  const maxHeight = Math.max(40, viewport.height - top - 8);
  const width = Math.min(targetRect.width + padding * 2, maxWidth);
  const height = Math.min(targetRect.height + padding * 2, maxHeight);

  return { top, left, width, height };
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}

function fitsPlacement(
  placement: Exclude<HrTourPlacement, "center">,
  rect: TourRect,
  viewport: TourViewport,
  popover: TourSize,
  gap: number,
  margin: number,
): boolean {
  switch (placement) {
    case "bottom":
      return rect.top + rect.height + gap + popover.height + margin <= viewport.height;
    case "top":
      return rect.top - gap - popover.height >= margin;
    case "right":
      return rect.left + rect.width + gap + popover.width + margin <= viewport.width;
    case "left":
      return rect.left - gap - popover.width >= margin;
  }
}

export function computePopoverPosition(
  targetRect: TourRect | null,
  viewport: TourViewport,
  popover: TourSize,
  preferred: HrTourPlacement,
  gap = 16,
  margin = 16,
): PopoverCoordinates {
  const safeWidth = Math.min(popover.width, Math.max(240, viewport.width - margin * 2));
  const safeHeight = Math.min(popover.height, Math.max(180, viewport.height - margin * 2));

  if (!targetRect || preferred === "center" || viewport.width < 640) {
    const centeredTop =
      viewport.width < 640
        ? Math.max(margin, viewport.height - safeHeight - margin)
        : Math.max(margin, (viewport.height - safeHeight) / 2);
    return {
      top: clamp(centeredTop, margin, viewport.height - safeHeight - margin),
      left: clamp((viewport.width - safeWidth) / 2, margin, viewport.width - safeWidth - margin),
      placement: "center",
    };
  }

  const fallbacks: Record<Exclude<HrTourPlacement, "center">, readonly Exclude<HrTourPlacement, "center">[]> = {
    bottom: ["bottom", "top", "right", "left"],
    top: ["top", "bottom", "right", "left"],
    left: ["left", "right", "bottom", "top"],
    right: ["right", "left", "bottom", "top"],
  };

  const chosen =
    fallbacks[preferred].find((candidate) =>
      fitsPlacement(candidate, targetRect, viewport, { width: safeWidth, height: safeHeight }, gap, margin),
    ) ?? preferred;

  let top = margin;
  let left = margin;

  switch (chosen) {
    case "bottom":
      top = targetRect.top + targetRect.height + gap;
      left = targetRect.left + targetRect.width / 2 - safeWidth / 2;
      break;
    case "top":
      top = targetRect.top - gap - safeHeight;
      left = targetRect.left + targetRect.width / 2 - safeWidth / 2;
      break;
    case "right":
      top = targetRect.top + targetRect.height / 2 - safeHeight / 2;
      left = targetRect.left + targetRect.width + gap;
      break;
    case "left":
      top = targetRect.top + targetRect.height / 2 - safeHeight / 2;
      left = targetRect.left - gap - safeWidth;
      break;
  }

  return {
    top: clamp(top, margin, viewport.height - safeHeight - margin),
    left: clamp(left, margin, viewport.width - safeWidth - margin),
    placement: chosen,
  };
}
