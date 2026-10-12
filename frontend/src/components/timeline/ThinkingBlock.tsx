export function ThinkingBlock({ text }: { text: string | null }) {
  return (
    <details className="rounded-lg border border-dashed border-line bg-surface/60">
      <summary className="cursor-pointer px-3 py-2 text-sm text-muted">Thinking</summary>
      <div className="whitespace-pre-wrap border-t border-line px-3 py-3 text-sm text-muted">
        {text || "Thinking was recorded without a readable summary."}
      </div>
    </details>
  );
}
