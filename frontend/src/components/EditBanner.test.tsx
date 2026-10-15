import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EditBanner } from "./EditBanner";
import { HistoryCompare } from "./HistoryCompare";

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

describe("history compare", () => {
  it("lists a direction change", () => {
    const html = renderToStaticMarkup(<HistoryCompare changes={[{ from: "T-101", to: "P-101A", fields: ["direction"] }]} />);
    expect(html).toContain("T-101");
    expect(html).toContain("direction");
  });
});
