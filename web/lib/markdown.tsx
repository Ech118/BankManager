import type { ReactNode } from "react";
import { TYPE_LABEL, VALUE_TYPES, type ValueType } from "./format";

/**
 * A deliberately small markdown renderer for report bodies.
 *
 * Report text originates from filings and models, so it is UNTRUSTED. This builds React
 * nodes and never uses dangerouslySetInnerHTML: markup in the text is displayed as text.
 * It understands exactly what orchestrator/report/generator.py emits: headings, bullet
 * lists, blockquotes, paragraphs, rules, **bold**, _italic_, `code`, and three tokens the
 * UI turns into badges:
 *   (40.0% · fact)      a number with its type, coloured by type
 *   **[UNVERIFIED]**    a claim that failed verification, marked and never hidden
 *   _[unchecked]_       a claim the verifier has not seen
 */

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "quote"; lines: string[] }
  | { kind: "rule" }
  | { kind: "paragraph"; text: string };

export function parseBlocks(md: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  };
  for (const raw of md.split("\n")) {
    const line = raw.trimEnd();
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (!line.trim()) flush();
    else if (heading) {
      flush();
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
    } else if (/^---+$/.test(line.trim())) {
      flush();
      blocks.push({ kind: "rule" });
    } else if (line.startsWith("- ")) {
      flush();
      const last = blocks[blocks.length - 1];
      if (last?.kind === "list") last.items.push(line.slice(2));
      else blocks.push({ kind: "list", items: [line.slice(2)] });
    } else if (line.startsWith(">")) {
      flush();
      const text = line.replace(/^>\s?/, "");
      const last = blocks[blocks.length - 1];
      if (last?.kind === "quote") last.lines.push(text);
      else blocks.push({ kind: "quote", lines: [text] });
    } else paragraph.push(line);
  }
  flush();
  return blocks;
}

const INLINE = new RegExp(
  [
    String.raw`(?<unverified>\*\*\[UNVERIFIED\]\*\*)`,
    String.raw`(?<unchecked>_\[unchecked\]_)`,
    String.raw`(?<num>\((?<numtext>[^()]*?) · (?<numtype>fact|estimate|assumption)\))`,
    String.raw`(?<bold>\*\*(?<boldtext>.+?)\*\*)`,
    String.raw`(?<facts>_\[(?<factlist>[^\]]*)\]_)`,
    String.raw`(?<italic>_(?<italictext>[^_]+)_)`,
    String.raw`(?<code>` + "`" + String.raw`(?<codetext>[^` + "`" + String.raw`]+)` + "`" + String.raw`)`,
  ].join("|"),
  "g",
);

export function NumberToken({ text, type }: { text: string; type: ValueType }) {
  return (
    <span className={`num num-${type}`} title={TYPE_LABEL[type]} data-value-type={type}>
      {text}
      <span className="num-type">{type === "fact" ? "" : type === "estimate" ? "est." : "assum."}</span>
    </span>
  );
}

export function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const m of text.matchAll(INLINE)) {
    const g = m.groups ?? {};
    if (m.index > last) out.push(text.slice(last, m.index));
    if (g.unverified) {
      out.push(
        <span key={key++} className="chip chip-unverified" title="This claim failed verification. It is shown, not hidden.">
          Unverified
        </span>,
      );
    } else if (g.unchecked) {
      out.push(
        <span key={key++} className="chip chip-unchecked" title="The verifier has not checked this claim.">
          Unchecked
        </span>,
      );
    } else if (g.num) {
      const type = g.numtype as ValueType;
      out.push(VALUE_TYPES.includes(type) ? <NumberToken key={key++} text={g.numtext} type={type} /> : g.num);
    } else if (g.bold) out.push(<strong key={key++}>{g.boldtext}</strong>);
    else if (g.facts) {
      out.push(
        <span key={key++} className="fact-ids" title="Facts this claim rests on">
          {g.factlist}
        </span>,
      );
    } else if (g.italic) out.push(<em key={key++}>{g.italictext}</em>);
    else if (g.code) out.push(<code key={key++}>{g.codetext}</code>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ source }: { source: string }) {
  return (
    <div className="md">
      {parseBlocks(source).map((b, i) => {
        switch (b.kind) {
          case "heading": {
            const level = Math.min(Math.max(b.level + 1, 3), 6); // section titles live in <summary>; keep the outline sane
            const Tag = `h${level}` as "h3" | "h4" | "h5" | "h6";
            return <Tag key={i}>{renderInline(b.text)}</Tag>;
          }
          case "list":
            return (
              <ul key={i}>
                {b.items.map((it, j) => (
                  <li key={j}>{renderInline(it)}</li>
                ))}
              </ul>
            );
          case "quote":
            return (
              <blockquote key={i}>
                {b.lines.map((l, j) => (
                  <div key={j}>{renderInline(l)}</div>
                ))}
              </blockquote>
            );
          case "rule":
            return <hr key={i} />;
          default:
            return <p key={i}>{renderInline(b.text)}</p>;
        }
      })}
    </div>
  );
}
