export function HistoryCompare({ changes }: { changes: Array<{ from: string; to: string; fields: string[] }> }) {
  if (changes.length === 0) {
    return <p className="text-sm">No field changes between these versions.</p>;
  }
  return (
    <ul className="text-sm">
      {changes.map((change) => (
        <li key={`${change.from}-${change.to}`}>{change.from} to {change.to}: {change.fields.join(", ")}</li>
      ))}
    </ul>
  );
}
