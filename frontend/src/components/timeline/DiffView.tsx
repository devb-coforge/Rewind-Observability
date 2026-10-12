import { diffLines } from "../../lib/diff";

const tone = {
  same: "text-muted",
  add: "bg-ok/15 text-ok",
  del: "bg-danger/15 text-danger",
};

export function DiffView({ before, after }: { before: string; after: string }) {
  const lines = diffLines(before, after);
  return (
    <pre className="overflow-auto rounded-md bg-[#10120c] p-3 font-mono text-xs leading-5">
      {lines.map((line, index) => (
        <div key={`${line.kind}-${index}`} className={tone[line.kind]}>
          {line.kind === "add" ? "+ " : line.kind === "del" ? "- " : "  "}
          {line.text || " "}
        </div>
      ))}
    </pre>
  );
}

export function PatchView({ patch }: { patch: string }) {
  return (
    <pre className="overflow-auto rounded-md bg-[#10120c] p-3 font-mono text-xs leading-5">
      {patch.split("\n").map((line, index) => {
        const className = line.startsWith("+") && !line.startsWith("+++")
          ? "text-ok"
          : line.startsWith("-") && !line.startsWith("---")
            ? "text-danger"
            : "text-muted";
        return (
          <div key={index} className={className}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}
