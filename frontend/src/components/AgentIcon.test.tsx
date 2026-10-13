import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentIcon, hasAgentIcon } from "./AgentIcon";

describe("AgentIcon", () => {
  it("renders brand marks for known agents", () => {
    for (const agent of ["cursor", "claude_code", "codex"]) {
      expect(hasAgentIcon(agent)).toBe(true);
      const { container } = render(<AgentIcon agent={agent} />);
      expect(container.querySelector("svg path")).toBeTruthy();
    }
  });

  it("falls back to a dot for unknown agents", () => {
    expect(hasAgentIcon("other")).toBe(false);
    const { container } = render(<AgentIcon agent="other" />);
    expect(container.querySelector("svg")).toBeNull();
    expect(container.querySelector("span.rounded-full")).toBeTruthy();
  });
});
