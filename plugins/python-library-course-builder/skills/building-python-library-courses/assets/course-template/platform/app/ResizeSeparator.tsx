"use client";

import { useRef, type KeyboardEvent, type PointerEvent } from "react";

import { nextSeparatorValue } from "./courseLayout.mjs";

type ResizeSeparatorProps = {
  label: string;
  controls: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  className?: string;
  disabled?: boolean;
};

type PointerDrag = {
  pointerId: number;
  startX: number;
  startValue: number;
};

export function ResizeSeparator({
  label,
  controls,
  value,
  min,
  max,
  onChange,
  className = "",
  disabled = false,
}: ResizeSeparatorProps) {
  const dragRef = useRef<PointerDrag | null>(null);

  function clamp(valueToClamp: number) {
    return Math.min(max, Math.max(min, valueToClamp));
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (disabled || event.button !== 0) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startValue: value,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (disabled) return;
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    onChange(clamp(drag.startValue + event.clientX - drag.startX));
  }

  function finishPointerDrag(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    const nextValue = nextSeparatorValue(value, event.key, min, max);
    if (nextValue === null) return;
    event.preventDefault();
    onChange(nextValue);
  }

  return (
    <div
      className={`resize-separator ${className}`.trim()}
      role="separator"
      aria-label={label}
      aria-controls={controls}
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : 0}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishPointerDrag}
      onPointerCancel={finishPointerDrag}
      onKeyDown={handleKeyDown}
    >
      <span aria-hidden="true" />
    </div>
  );
}
