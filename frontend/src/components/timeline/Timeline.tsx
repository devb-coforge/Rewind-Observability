import { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronsDownUp } from "lucide-react";
import type { ObsEvent } from "../../api/types";
import { cn } from "../../lib/cn";
import { Button, Checkbox, EmptyState } from "../ui";
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
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line px-5 py-2.5">
        <div role="group" aria-label="Filter timeline" className="inline-flex rounded-md border border-line bg-surface p-0.5">
          {views.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={view === value}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition-colors",
                view === value ? "bg-surface3 text-ink shadow-card" : "text-muted hover:text-ink",
              )}
              onClick={() => {
                setView(value);
                parentRef.current?.scrollTo({ top: 0 });
              }}
            >
              {label}
              <span className={cn("tabular-nums", view === value ? "text-muted" : "text-subtle")}>
                {allItems.filter((item) => matchesView(item, value)).length}
              </span>
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-4">
          {thinkingCount > 0 && (view === "all" || view === "errors") ? (
            <Checkbox
              className="text-xs"
              label={`Show thinking (${thinkingCount})`}
              checked={showThinking}
              onChange={(event) => onShowThinkingChange(event.target.checked)}
            />
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setExpanded(Object.fromEntries(allItems.map((item) => [itemKey(item), false])))}
          >
            <ChevronsDownUp aria-hidden="true" className="size-3.5" />
            Collapse details
          </Button>
        </div>
      </div>
      <div className="shrink-0 px-5 pt-3 text-2xs text-subtle">
        <span aria-live="polite">
          <span className="tabular-nums">{items.length}</span> of <span className="tabular-nums">{allItems.length}</span> steps
          {focusedOutsideView ? " · includes linked event" : ""}
        </span>
      </div>
      <div ref={parentRef} className="min-h-0 flex-1 overflow-auto px-5 py-3">
        {items.length === 0 ? (
          <EmptyState
            title={allItems.length === 0 ? "No events in this session." : view === "errors" ? "No errors recorded in this session." : "No events match this view."}
            action={view !== "all" ? <Button size="sm" onClick={() => setView("all")}>Show all events</Button> : undefined}
          />
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
                className="absolute left-0 top-0 w-full pb-2.5"
                style={{ transform: `translateY(${virtual.start}px)` }}
              >
                {item.type === "tool" ? (
                  <div className={focused ? "rounded-lg ring-1 ring-accent/70 ring-offset-2 ring-offset-bg" : ""}>
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
