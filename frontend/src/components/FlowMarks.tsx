export function FlowMarks({ enabled, onToggle }: { enabled: boolean; onToggle: (value: boolean) => void }) {
  if (!enabled && onToggle.length === 0) {
    return null;
  }
  return (
    <div className="text-sm">
      <button type="button" className="rounded-full border border-line px-3 py-1" onClick={() => onToggle(!enabled)}>
        {enabled ? "Pause flow marks" : "Play flow marks"}
      </button>
      {enabled ? <span className="flow-mark ml-2 inline-block h-2 w-2 rounded-full bg-teal" /> : null}
      <style>{`@media (prefers-reduced-motion: reduce) { .flow-mark { animation: none; } }`}</style>
    </div>
  );
}
