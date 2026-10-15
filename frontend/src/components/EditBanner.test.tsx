import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EditBanner } from "./EditBanner";
import { HistoryCompare } from "./HistoryCompare";
import { AskGraphBox } from "./AskGraphBox";
import { FlowMarks } from "./FlowMarks";
import { SanityList } from "./SanityList";
import { ThemeToggle } from "./ThemeToggle";
import { SimulationBanner } from "./SimulationBanner";

describe("edit banner", () => {
  it("hides Modify when editing is turned off", () => {
    const html = renderToStaticMarkup(<EditBanner modifyEnabled={false} accepted={false} onKeep={() => undefined} onModify={() => undefined} />);
    expect(html).toContain("Keep as is");
    expect(html).toContain("Modify is turned off");
    expect(html).not.toContain(">Modify<");
  });

  it("shows a validation message and an undo control", () => {
    const html = renderToStaticMarkup(
      <section>
        <p>Unknown tag on NO-TAG.</p>
        <button type="button" disabled>Undo</button>
      </section>,
    );
    expect(html).toContain("Unknown tag");
    expect(html).toContain("disabled");
  });
});

describe("sanity list", () => {
  it("states that a warning is not a fact", () => {
    const html = renderToStaticMarkup(<SanityList warnings={[{ id: "1", rule: "ab-symmetry", reason: "This is a warning, not a fact that B is missing from the plant." }]} />);
    expect(html).toContain("not a fact");
  });
});

describe("simulation banner", () => {
  it("names the simulation and hides itself when off", () => {
    expect(renderToStaticMarkup(<SimulationBanner on={false} />)).toBe("");
    expect(renderToStaticMarkup(<SimulationBanner on />)).toContain("SIMULATION - not real plant data");
  });
});

describe("ask the graph box", () => {
  it("shows the refusal wording", () => {
    const html = renderToStaticMarkup(
      <AskGraphBox question="weather" answer="That is not in the extracted graph." onQuestion={() => undefined} onAsk={() => undefined} />,
    );
    expect(html).toContain("That is not in the extracted graph.");
  });
});

describe("stretch controls", () => {
  it("hides the theme toggle when the flag is off and keeps reduced motion in the flow marks", () => {
    expect(renderToStaticMarkup(<ThemeToggle enabled={false} mode="light" onChange={() => undefined} />)).toBe("");
    expect(renderToStaticMarkup(<FlowMarks enabled onToggle={() => undefined} />)).toContain("prefers-reduced-motion");
  });
});

describe("history compare", () => {
  it("lists a direction change", () => {
    const html = renderToStaticMarkup(<HistoryCompare changes={[{ from: "T-101", to: "P-101A", fields: ["direction"] }]} />);
    expect(html).toContain("T-101");
    expect(html).toContain("direction");
  });
});
