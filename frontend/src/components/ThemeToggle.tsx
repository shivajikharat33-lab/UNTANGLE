export function ThemeToggle({ enabled, mode, onChange }: { enabled: boolean; mode: "light" | "dark" | "system"; onChange: (mode: "light" | "dark" | "system") => void }) {
  if (!enabled) {
    return null;
  }
  return (
    <div className="flex gap-2 text-sm">
      {(["light", "dark", "system"] as const).map((value) => (
        <button key={value} type="button" className={`rounded-full border px-3 py-1 ${mode === value ? "border-ink" : "border-line"}`} onClick={() => onChange(value)}>
          {value}
        </button>
      ))}
    </div>
  );
}
