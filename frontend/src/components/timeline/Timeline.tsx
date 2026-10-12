import { useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { ObsEvent } from "../../api/types";
import { EventRow } from "./EventRow";
import { itemKey, itemMatches, timelineItems } from "./pair";
import { ToolCallCard } from "./ToolCallCard";

export function Timeline({
  events,
  showThinking,
  focusId,
  onRaw,
}: {
  events: ObsEvent[];
  showThinking: boolean;
  focusId?: string | null;
  onRaw: (id: string) => void;
}) {
  const items = timelineItems(events, showThinking);
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

  if (items.length === 0) {
    return <p className="p-6 text-sm text-muted">No events in this session.</p>;
  }

  return (
    <div ref={parentRef} className="h-full overflow-auto px-4 py-4">
      <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((virtual) => {
          const item = items[virtual.index];
          const focused = focusId ? itemMatches(item, focusId) : false;
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
                  <ToolCallCard call={item.call} result={item.result} />
                </div>
              ) : (
                <EventRow event={item.event} focused={focused} onRaw={onRaw} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
