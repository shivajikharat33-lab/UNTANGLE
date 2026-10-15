import { describe, expect, it } from "vitest";
import { gateNeeded, uploadsHidden } from "./access";

describe("demo gate helpers", () => {
  it("opens local development when the server does not require a code", () => {
    expect(gateNeeded({ access_required: false })).toBe(false);
    expect(gateNeeded(null)).toBe(false);
  });

  it("asks for the code only when the server says so", () => {
    expect(gateNeeded({ access_required: true })).toBe(true);
  });

  it("hides uploads in the public demo", () => {
    expect(uploadsHidden({ public_demo_mode: true })).toBe(true);
    expect(uploadsHidden({ public_demo_mode: false })).toBe(false);
  });
});
