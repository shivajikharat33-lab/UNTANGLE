import { useRef, useState } from "react";
import { Button } from "./Button";
import { formatBytes } from "../lib/format";

type FileDropZoneProps = {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  message: string | null;
  disabled?: boolean;
  onSelect: (file: File) => void;
  onClear: () => void;
};

export function FileDropZone({ label, hint, accept, file, message, disabled = false, onSelect, onClear }: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function take(list: FileList | null) {
    const next = list?.item(0);
    if (next) {
      onSelect(next);
    }
  }

  return (
    <div
      className={`rounded-card border bg-paper px-4 py-4 ${dragging ? "border-teal" : "border-line"} ${disabled ? "opacity-60" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) {
          setDragging(true);
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (!disabled) {
          take(event.dataTransfer.files);
        }
      }}
    >
      <p className="font-semibold text-ink">{label}</p>
      <p className="mt-1 text-sm text-ink-soft">{hint}</p>
      {file ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink">
            {file.name}
            <span className="ml-2 font-mono text-xs text-ink-soft">{formatBytes(file.size)}</span>
          </p>
          <Button variant="ghost" onClick={onClear} disabled={disabled}>
            Remove
          </Button>
        </div>
      ) : (
        <label className="mt-3 flex cursor-pointer flex-col items-start gap-2">
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            className="sr-only"
            disabled={disabled}
            onChange={(event) => {
              take(event.target.files);
              event.target.value = "";
            }}
          />
          <span className="rounded-control border border-line bg-paper-raised px-3 py-2 text-sm font-semibold">
            Browse
          </span>
          <span className="text-sm text-ink-soft">Or drop the file here.</span>
        </label>
      )}
      {message ? (
        <p role="alert" className="mt-3 text-sm text-alert-error-fg">
          {message}
        </p>
      ) : null}
    </div>
  );
}
