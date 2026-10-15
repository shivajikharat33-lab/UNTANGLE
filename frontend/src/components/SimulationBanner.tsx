export function SimulationBanner({ on }: { on: boolean }) {
  if (!on) {
    return null;
  }
  return (
    <p className="rounded-card border border-line bg-paper-raised px-3 py-2 text-sm font-semibold">
      SIMULATION - not real plant data
    </p>
  );
}
