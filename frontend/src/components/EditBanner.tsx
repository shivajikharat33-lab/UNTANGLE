export function EditBanner({
  modifyEnabled,
  accepted,
  onKeep,
  onModify,
}: {
  modifyEnabled: boolean;
  accepted: boolean;
  onKeep: () => void;
  onModify: () => void;
}) {
  return (
    <section className="rounded-card border border-line p-4 text-sm">
      <p className="font-semibold">Version 0 is the tool result. It is not changed by either choice.</p>
      {accepted ? <p>Version 0 is accepted. Exports stay available.</p> : <p>Choose keep as is, or modify a separate working copy.</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="rounded-full border border-line px-3 py-1 font-semibold" onClick={onKeep}>
          Keep as is
        </button>
        {modifyEnabled ? (
          <button type="button" className="rounded-full border border-ink px-3 py-1 font-semibold" onClick={onModify}>
            Modify
          </button>
        ) : (
          <p>Modify is turned off for this demo.</p>
        )}
      </div>
    </section>
  );
}
