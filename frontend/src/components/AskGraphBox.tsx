export function AskGraphBox({
  question,
  answer,
  onQuestion,
  onAsk,
}: {
  question: string;
  answer: string;
  onQuestion: (value: string) => void;
  onAsk: () => void;
}) {
  return (
    <section className="rounded-card border border-line p-4 text-sm">
      <h2 className="font-semibold">Ask the graph</h2>
      <p className="mt-1 text-ink-soft">Answers use the extracted graph only. A question outside that list is refused.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <input aria-label="Question for the graph" className="min-w-0 flex-1 rounded-control border border-line px-3 py-2" value={question} onChange={(event) => onQuestion(event.target.value)} />
        <button type="button" className="rounded-full border border-ink px-3 py-1 font-semibold" onClick={onAsk}>Ask</button>
      </div>
      {answer ? <p className="mt-3">{answer}</p> : <p className="mt-3 text-ink-soft">No question sent yet.</p>}
    </section>
  );
}
