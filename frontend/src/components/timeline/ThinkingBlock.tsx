import { ChevronRight, Sparkles } from "lucide-react";

export function ThinkingBlock({ text, expanded, onExpandedChange }: {
  text: string | null;
  expanded?: boolean;
  onExpandedChange?: (open: boolean) => void;
}) {
  return (
    <details
      open={expanded}
      onToggle={(event) => onExpandedChange?.(event.currentTarget.open)}
      className="thinking rounded-lg border border-dashed border-line-strong/70 bg-surface/40"
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs text-muted hover:text-ink">
        <ChevronRight aria-hidden="true" className="disclosure size-3.5 text-subtle transition-transform" />
        <Sparkles aria-hidden="true" className="size-3.5 text-subtle" />
        <span className="font-medium">Thinking</span>
      </summary>
      <div className="whitespace-pre-wrap border-t border-dashed border-line-strong/70 px-4 py-3 text-[13px] italic leading-relaxed text-muted">
        {text || "Thinking was recorded without a readable summary."}
      </div>
    </details>
  );
}
