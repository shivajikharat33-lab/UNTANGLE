import { describe, expect, it } from "vitest";
import { clampZoom, zoomBy, zoomPercent } from "./viewTransform";

describe("view zoom", () => {
  it("stays inside the limits and shows a percent", () => {
    expect(clampZoom(10)).toBe(4);
    expect(clampZoom(0.01)).toBe(0.25);
    expect(zoomBy(1, 1.25)).toBe(1.25);
    expect(zoomPercent(1)).toBe("100%");
  });
});
