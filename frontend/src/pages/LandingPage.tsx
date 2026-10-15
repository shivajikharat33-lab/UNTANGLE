import { Link } from "react-router";
import { buttonClass } from "../lib/buttonClass";

const workflow = [
  { name: "Read", text: "Open the customer P&ID and the instrument IO list." },
  { name: "Keep", text: "Hold onto every symbol. Hide one only with a reason." },
  { name: "Trace", text: "Follow the lines and record the flow direction." },
  { name: "Redraw", text: "Lay a simpler sketch out from left to right." },
  { name: "Verify", text: "Run the checks. Flag anything that is still uncertain." },
];

const outputs = [
  { name: "Sketch", detail: "SVG, PDF, and PNG of the simplified drawing." },
  { name: "Tag Check Report", detail: "Each IO tag marked found, fuzzy, missing, or extra." },
  { name: "Connection Report", detail: "Each line, its direction, and the evidence behind it." },
  { name: "JSON", detail: "The graph, for a later tool or an HMI handoff." },
  { name: "Connection List", detail: "An Excel workbook of the connections." },
  { name: "Print-ready PDF", detail: "A page laid out for a review packet." },
];

const people = [
  { name: "Engineers", text: "Spend the time on the lines that need a decision, not on redrawing the ones that are clear." },
  { name: "Operators", text: "Read a left-to-right sketch instead of hunting across a crowded customer drawing." },
  { name: "Integrators", text: "Start from the IO list and see which tags landed on the sketch." },
  { name: "Review teams", text: "See what passed a check, and what is still marked for a person." },
];

function PipeSketch() {
  return (
    <svg viewBox="0 0 360 220" className="h-auto w-full max-w-md" role="img" aria-label="Simple illustration of a tank, a pump, and a pipe. This is not a project result.">
      <rect x="24" y="36" width="70" height="120" rx="6" fill="none" stroke="#102030" strokeWidth="3" />
      <path d="M40 56h38M40 72h38" stroke="#8c4a12" strokeWidth="3" />
      <text x="59" y="148" textAnchor="middle" fill="#3f4e5e" fontSize="12" fontFamily="IBM Plex Mono, monospace">
        TANK
      </text>
      <path d="M94 96h70" stroke="#102030" strokeWidth="4" />
      <circle cx="196" cy="96" r="28" fill="#f4efe6" stroke="#102030" strokeWidth="3" />
      <path d="M184 96h24M196 84v24" stroke="#0e5f68" strokeWidth="3" />
      <text x="196" y="146" textAnchor="middle" fill="#3f4e5e" fontSize="12" fontFamily="IBM Plex Mono, monospace">
        PUMP
      </text>
      <path d="M224 96h90" stroke="#102030" strokeWidth="4" />
      <path d="M300 84l16 12-16 12" fill="none" stroke="#8c4a12" strokeWidth="3" />
    </svg>
  );
}

export function LandingPage() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="border-b border-line bg-paper/95">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 md:px-8">
          <div>
            <p className="font-display text-2xl leading-none">UNTANGLE</p>
            <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-soft">P&amp;ID simplification</p>
          </div>
          <Link to="/app" className={buttonClass("primary")}>
            Open app
          </Link>
        </div>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-12 md:px-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:py-20">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-copper-deep">For control-room sketches</p>
            <h1 className="mt-3 font-display text-display text-ink">
              Give us the customer P&amp;ID and IO list, get back a verified, simplified control-room sketch.
            </h1>
            <p className="mt-4 max-w-xl text-lg leading-8 text-ink-soft">
              UNTANGLE is being built to read those two files and redraw the control story from left to right. Uncertain items are flagged for review. They are not dropped.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/app/new" className={buttonClass("primary")}>
                Start a project
              </Link>
              <a href="#workflow" className={buttonClass("secondary")}>
                See how it works
              </a>
            </div>
          </div>
          <div className="rounded-card border border-line bg-paper-raised p-6 shadow-card">
            <PipeSketch />
            <p className="mt-3 text-xs text-ink-soft">Illustration only. This is not a drawing from a project.</p>
          </div>
        </section>

        <section className="border-y border-line bg-paper-raised">
          <div className="mx-auto max-w-6xl px-4 py-12 md:px-8">
            <h2 className="font-display text-title">The redraw still happens by hand</h2>
            <p className="mt-3 max-w-3xl text-base leading-7 text-ink-soft">
              An engineer opens the customer P&amp;ID, finds each instrument on the IO list, traces the line, and draws a cleaner sketch for the control room. That work is slow. It is the same kind of tracing on every project. A missed tag or a reversed arrow is easy to introduce and hard to see later.
            </p>
            <p className="mt-3 max-w-3xl text-base leading-7 text-ink-soft">
              The aim is hours of manual redrawing reduced to minutes of review (to be measured). The person still decides what is accepted.
            </p>
          </div>
        </section>

        <section id="workflow" className="mx-auto max-w-6xl px-4 py-12 md:px-8">
          <h2 className="font-display text-title">How a drawing moves through</h2>
          <ol className="mt-6 grid gap-3 md:grid-cols-5">
            {workflow.map((step, index) => (
              <li key={step.name} className="rounded-card border border-line bg-paper-raised p-4">
                <p className="font-mono text-xs text-copper-deep">{index + 1}</p>
                <h3 className="mt-2 font-display text-xl">{step.name}</h3>
                <p className="mt-2 text-sm leading-6 text-ink-soft">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-y border-line">
          <div className="mx-auto max-w-6xl px-4 py-12 md:px-8">
            <h2 className="font-display text-title">Exact first, rules decide, AI assists</h2>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <article className="rounded-card border border-line bg-paper-raised p-5">
                <h3 className="font-display text-xl">What the checks mean</h3>
                <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-ink-soft">
                  <li>Text and lines that are actually in the file are used before any guess.</li>
                  <li>Named rules accept a connection, send it back for another trace, or flag it.</li>
                  <li>An AI suggestion, when one exists later, keeps a confidence score and a reason.</li>
                  <li>A low score or a failed check becomes a Needs Review flag. The item stays in the data.</li>
                </ul>
              </article>
              <article className="rounded-card border border-line bg-paper-raised p-5">
                <h3 className="font-display text-xl">What a pass is not</h3>
                <p className="mt-3 text-sm leading-6 text-ink-soft">
                  Passing the automated checks is not an engineering approval and it is not a safety certification. A Verified mark, when it exists, will only mean every defined check passed. A person still reviews the sketch before it is used.
                </p>
              </article>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-12 md:px-8">
          <h2 className="font-display text-title">What you will be able to take away</h2>
          <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {outputs.map((item) => (
              <li key={item.name} className="rounded-card border border-line bg-paper-raised p-4">
                <h3 className="font-semibold">{item.name}</h3>
                <p className="mt-1 text-sm leading-6 text-ink-soft">{item.detail}</p>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-ink-soft">After a project is processed, the Export page can download JSON, SVG, PNG, PDF, and Excel. A draft file is labeled draft and is not Verified.</p>
        </section>

        <section className="border-t border-line bg-paper-raised">
          <div className="mx-auto max-w-6xl px-4 py-12 md:px-8">
            <h2 className="font-display text-title">Who this is for</h2>
            <ul className="mt-6 grid gap-4 md:grid-cols-2">
              {people.map((person) => (
                <li key={person.name}>
                  <h3 className="font-display text-xl">{person.name}</h3>
                  <p className="mt-1 text-sm leading-6 text-ink-soft">{person.text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="status" className="mx-auto max-w-6xl px-4 py-12 md:px-8">
          <div className="rounded-card border border-copper/40 bg-paper-raised p-6 shadow-card">
            <h2 className="font-display text-title">Current status</h2>
            <div className="mt-4 grid gap-6 md:grid-cols-2">
              <div>
                <h3 className="font-semibold text-teal">Works today</h3>
                <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-ink-soft">
                  <li>Upload a P&amp;ID PDF and an IO workbook, then run extraction.</li>
                  <li>Read pages, detect symbols, and match tags to the IO list.</li>
                  <li>Build the graph, simplified sketch, reports, and downloads.</li>
                  <li>Edit the connection list. Version 0 stays the original.</li>
                  <li>Compare versions and restore an older one as a new version.</li>
                </ul>
              </div>
              <div>
                <h3 className="font-semibold text-copper-deep">Limits</h3>
                <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-ink-soft">
                  <li>There is no login. Edits are recorded as the local user.</li>
                  <li>Verified means the defined automated checks passed. It is not an engineering or safety certification.</li>
                  <li>The optional model, few-shot symbols, dark theme, and flow animation stay off.</li>
                  <li>Detection counts on the sample drawing are not a product accuracy percentage.</li>
                </ul>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm text-ink-soft md:flex-row md:items-center md:justify-between md:px-8">
          <p>UNTANGLE. Uncertain items are flagged for review.</p>
          <Link to="/app" className="font-semibold text-teal underline">
            Open app
          </Link>
        </div>
      </footer>
    </div>
  );
}
