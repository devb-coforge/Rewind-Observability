import { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { ObsEvent } from "../../api/types";
import { EventRow } from "./EventRow";
import { filterTimeline, itemKey, itemMatches, matchesView, pairEvents, type TimelineView } from "./pair";
import { ToolCallCard } from "./ToolCallCard";

export function Timeline({
  events,
  showThinking,
  onShowThinkingChange,
  focusId,
  onRaw,
}: {
  events: ObsEvent[];
  showThinking: boolean;
  onShowThinkingChange: (show: boolean) => void;
  focusId?: string | null;
  onRaw: (id: string) => void;
}) {
  const [view, setView] = useState<TimelineView>("all");
  // Keep disclosure state here so virtualized rows retain it when they leave the viewport.
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const allItems = useMemo(() => pairEvents(events), [events]);
  const items = useMemo(
    () => filterTimeline(allItems, view, showThinking, focusId),
    [allItems, view, showThinking, focusId],
  );
  const focusedOutsideView = allItems.some((item) =>
    focusId && itemMatches(item, focusId) &&
    (!matchesView(item, view) || (!showThinking && item.type === "single" && item.event.kind === "thinking")),
  );
  const thinkingCount = events.filter((event) => event.kind === "thinking").length;
  const views: { value: TimelineView; label: string }[] = [
    { value: "all", label: "All events" },
    { value: "conversation", label: "Conversation" },
    { value: "tools", label: "Tools" },
    { value: "errors", label: "Errors" },
  ];
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 96,
    overscan: 8,
    getItemKey: (index) => itemKey(items[index]),
  });

  useEffect(() => {
    if (!focusId) return;
    const index = items.findIndex((item) => itemMatches(item, focusId));
    if (index >= 0) virtualizer.scrollToIndex(index, { align: "center" });
  }, [focusId, items, virtualizer]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line bg-bg px-4 py-2">
        <div role="group" aria-label="Filter timeline" className="flex flex-wrap gap-1">
          {views.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={view === value}
              className={`rounded-md px-2.5 py-1.5 text-xs ${view === value ? "bg-surface2 text-accent" : "text-muted hover:bg-surface hover:text-ink"}`}
              onClick={() => {
                setView(value);
                parentRef.current?.scrollTo({ top: 0 });
              }}
            >
              {label} <span className="ml-1 tabular-nums opacity-70">{allItems.filter((item) => matchesView(item, value)).length}</span>
            </button>
          ))}
        </div>
        {thinkingCount > 0 && (view === "all" || view === "errors") ? (
          <label className="ml-auto flex items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={showThinking} onChange={(event) => onShowThinkingChange(event.target.checked)} />
            Show thinking ({thinkingCount})
          </label>
        ) : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 px-4 pt-3 text-xs text-muted">
        <span aria-live="polite">{items.length} of {allItems.length} steps{focusedOutsideView ? " · includes linked event" : ""}</span>
        <button
          type="button"
          className="hover:text-ink"
          onClick={() => setExpanded(Object.fromEntries(allItems.map((item) => [itemKey(item), false])))}
        >
          Collapse details
        </button>
      </div>
      <div ref={parentRef} className="min-h-0 flex-1 overflow-auto px-4 py-4">
        {items.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line p-8 text-center">
            <p className="text-sm text-muted">
              {allItems.length === 0 ? "No events in this session." : view === "errors" ? "No errors recorded in this session." : "No events match this view."}
            </p>
            {view !== "all" ? (
              <button type="button" className="mt-3 text-sm text-accent" onClick={() => setView("all")}>Show all events</button>
            ) : null}
          </div>
        ) : null}
        <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((virtual) => {
            const item = items[virtual.index];
            const focused = focusId ? itemMatches(item, focusId) : false;
            const key = itemKey(item);
            const open = expanded[key] ?? focused;
            const onExpandedChange = (value: boolean) => setExpanded((current) =>
              current[key] === value ? current : { ...current, [key]: value },
            );
            return (
              <div
                key={virtual.key}
                data-index={virtual.index}
                ref={virtualizer.measureElement}
                className="absolute left-0 top-0 w-full pb-3"
                style={{ transform: `translateY(${virtual.start}px)` }}
              >
                {item.type === "tool" ? (
                  <div className={focused ? "rounded-lg ring-1 ring-accent" : ""}>
                    <ToolCallCard call={item.call} result={item.result} expanded={open} onExpandedChange={onExpandedChange} onRaw={onRaw} />
                  </div>
                ) : (
                  <EventRow event={item.event} focused={focused} onRaw={onRaw} expanded={open} onExpandedChange={onExpandedChange} />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
