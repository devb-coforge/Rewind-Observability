import { diffLines } from "../../lib/diff";

const tone = {
  same: "text-muted",
  add: "bg-ok/10 text-ok",
  del: "bg-danger/10 text-danger",
};

export const codeBlock = "overflow-auto rounded-md border border-line bg-code px-3 py-2.5 font-mono text-xs leading-5";

export function DiffView({ before, after }: { before: string; after: string }) {
  const lines = diffLines(before, after);
  return (
    <pre className={codeBlock}>
      {lines.map((line, index) => (
        <div key={`${line.kind}-${index}`} className={`-mx-3 px-3 ${tone[line.kind]}`}>
          {line.kind === "add" ? "+ " : line.kind === "del" ? "- " : "  "}
          {line.text || " "}
        </div>
      ))}
    </pre>
  );
}

export function PatchView({ patch }: { patch: string }) {
  return (
    <pre className={codeBlock}>
      {patch.split("\n").map((line, index) => {
        const className = line.startsWith("+") && !line.startsWith("+++")
          ? tone.add
          : line.startsWith("-") && !line.startsWith("---")
            ? tone.del
            : line.startsWith("@@") || line.startsWith("***")
              ? "text-accent/80"
              : tone.same;
        return (
          <div key={index} className={`-mx-3 px-3 ${className}`}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}
