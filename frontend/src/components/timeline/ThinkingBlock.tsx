export function ThinkingBlock({ text, expanded, onExpandedChange }: {
  text: string | null;
  expanded?: boolean;
  onExpandedChange?: (open: boolean) => void;
}) {
  return (
    <details open={expanded} onToggle={(event) => onExpandedChange?.(event.currentTarget.open)} className="rounded-lg border border-dashed border-line bg-surface/60">
      <summary className="cursor-pointer px-3 py-2 text-sm text-muted">Thinking</summary>
      <div className="whitespace-pre-wrap border-t border-line px-3 py-3 text-sm text-muted">
        {text || "Thinking was recorded without a readable summary."}
      </div>
    </details>
  );
}
