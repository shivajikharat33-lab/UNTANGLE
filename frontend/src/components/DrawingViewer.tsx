import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, WheelEvent } from "react";
import { Button } from "./Button";
import { clampZoom, zoomBy, zoomPercent } from "../lib/viewTransform";

type DrawingViewerProps = {
  label: string;
  zoom: number;
  onZoom: (zoom: number) => void;
  children: React.ReactNode;
};

export function DrawingViewer({ label, zoom, onZoom, children }: DrawingViewerProps) {
  const frame = useRef<HTMLDivElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const pinch = useRef<number | null>(null);

  useEffect(() => {
    const node = frame.current;
    if (!node) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (document.activeElement !== node) {
        return;
      }
      if (event.key === "+" || event.key === "=") {
        onZoom(zoomBy(zoom, 1.25));
      } else if (event.key === "-" || event.key === "_") {
        onZoom(zoomBy(zoom, 0.8));
      } else if (event.key === "0") {
        onZoom(1);
        setPan({ x: 0, y: 0 });
      } else       if (event.key === "f" || event.key === "F") {
        onZoom(1);
        setPan({ x: 0, y: 0 });
      }
    }
    node.addEventListener("keydown", onKey);
    return () => node.removeEventListener("keydown", onKey);
  }, [onZoom, zoom]);

  function fit() {
    onZoom(1);
    setPan({ x: 0, y: 0 });
  }

  function onWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    onZoom(zoomBy(zoom, event.deltaY > 0 ? 0.9 : 1.1));
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === "touch" && event.isPrimary === false) {
      return;
    }
    drag.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const touches = event.nativeEvent;
    if (touches instanceof TouchEvent) {
      return;
    }
    if (!drag.current) {
      return;
    }
    setPan({
      x: drag.current.panX + event.clientX - drag.current.x,
      y: drag.current.panY + event.clientY - drag.current.y,
    });
  }

  function onPointerUp() {
    drag.current = null;
  }

  function onTouchMove(event: React.TouchEvent<HTMLDivElement>) {
    if (event.touches.length === 2) {
      const distance = Math.hypot(
        event.touches[0].clientX - event.touches[1].clientX,
        event.touches[0].clientY - event.touches[1].clientY,
      );
      if (pinch.current !== null) {
        onZoom(zoomBy(zoom, distance / pinch.current));
      }
      pinch.current = distance;
      return;
    }
    pinch.current = null;
  }

  return (
    <section className="space-y-2" aria-label={label}>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" aria-label={`Zoom in ${label}`} onClick={() => onZoom(zoomBy(zoom, 1.25))}>Zoom in</Button>
        <Button variant="secondary" aria-label={`Zoom out ${label}`} onClick={() => onZoom(zoomBy(zoom, 0.8))}>Zoom out</Button>
        <Button variant="secondary" aria-label={`Fit ${label} to width`} onClick={fit}>Fit to width</Button>
        <Button variant="secondary" aria-label={`Reset ${label}`} onClick={() => { onZoom(1); setPan({ x: 0, y: 0 }); }}>Reset</Button>
        <p className="text-sm font-semibold" aria-live="polite">{zoomPercent(zoom)}</p>
      </div>
      <div
        ref={frame}
        tabIndex={0}
        role="application"
        aria-label={`${label} viewer. Plus and minus change zoom. F fits to width. Zero resets.`}
        className="h-80 overflow-hidden rounded-card border border-line bg-paper"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onTouchMove={onTouchMove}
        onTouchEnd={() => { pinch.current = null; }}
      >
        <div style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${clampZoom(zoom)})`, transformOrigin: "0 0" }}>
          {children}
        </div>
      </div>
    </section>
  );
}
