export function SanityList({ warnings }: { warnings: Array<{ id: string; rule: string; reason: string }> }) {
  if (warnings.length === 0) {
    return <p className="text-sm">No sanity warnings. These checks are silent when nothing looks uneven.</p>;
  }
  return (
    <ul className="space-y-2 text-sm">
      {warnings.map((item) => (
        <li key={item.id}><span className="font-semibold">{item.rule}.</span> {item.reason}</li>
      ))}
    </ul>
  );
}
