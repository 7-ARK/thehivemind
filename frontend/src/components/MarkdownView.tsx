import React from "react";

interface MarkdownViewProps {
  content: string;
}

export default function MarkdownView({ content }: MarkdownViewProps) {
  if (!content) return null;

  // Split content by lines and perform clean visual conversions on common markdown tags
  const lines = content.split("\n");

  return (
    <div className="space-y-3.5 text-[#e9ecef] font-sans text-sm leading-relaxed">
      {lines.map((line, idx) => {
        const trimmed = line.trim();

        // 1. Level 3 Headers (e.g. ### Title)
        if (trimmed.startsWith("###")) {
          return (
            <h3 key={idx} className="text-sm font-bold tracking-tight text-[#20c997] uppercase pt-3.5 border-b border-[#2c2e33] pb-1.5 font-mono">
              {trimmed.replace(/^###\s+/, "")}
            </h3>
          );
        }

        // 2. Level 4 Headers (e.g. #### Title)
        if (trimmed.startsWith("####")) {
          return (
            <h4 key={idx} className="text-xs font-semibold tracking-wide text-[#e9ecef] uppercase pt-2">
              {trimmed.replace(/^####\s+/, "")}
            </h4>
          );
        }

        // 3. Bullet points (e.g. * Item or - Item)
        if (trimmed.startsWith("*") || trimmed.startsWith("-")) {
          const text = trimmed.replace(/^[\*\-]\s+/, "");
          return (
            <div key={idx} className="flex items-start gap-2.5 pl-3">
              <span className="w-1.5 h-1.5 bg-[#20c997] rounded mt-2 shrink-0 animate-pulse" />
              <p className="flex-1 text-[#e1e2e6]">
                {parseInlineFormatting(text)}
              </p>
            </div>
          );
        }

        // 4. Horizontal Rule
        if (trimmed === "---") {
          return <div key={idx} className="border-t border-[#2c2e33] my-4" />;
        }

        // 5. Normal line (empty line skipped to prevent huge spacing gaps)
        if (!trimmed) {
          return <div key={idx} className="h-1" />;
        }

        return (
          <p key={idx} className="text-[#e1e2e6] text-xs sm:text-sm">
            {parseInlineFormatting(line)}
          </p>
        );
      })}
    </div>
  );
}

// Simple parser for **bold text** and `inline code blocks`
function parseInlineFormatting(text: string) {
  const parts: React.ReactNode[] = [];
  let currentIndex = 0;

  // Pattern scanner
  const regex = /(\*\*.*?\*\*|`.*?`)/g;
  let match;

  while ((match = regex.exec(text)) !== null) {
    const matchIndex = match.index;
    const matchStr = match[0];

    // Append preceding raw text segment
    if (matchIndex > currentIndex) {
      parts.push(text.substring(currentIndex, matchIndex));
    }

    if (matchStr.startsWith("**") && matchStr.endsWith("**")) {
      // Bold
      const cleanVal = matchStr.substring(2, matchStr.length - 2);
      parts.push(<strong key={matchIndex} className="font-bold text-[#e1e2e6]">{cleanVal}</strong>);
    } else if (matchStr.startsWith("`") && matchStr.endsWith("`")) {
      // Inline Code
      const cleanVal = matchStr.substring(1, matchStr.length - 1);
      parts.push(
        <code key={matchIndex} className="bg-[#141517] text-[#fab005] px-1.5 py-0.5 rounded font-mono text-xs border border-[#2c2e33]">
          {cleanVal}
        </code>
      );
    }

    currentIndex = matchIndex + matchStr.length;
  }

  // Append remaining text
  if (currentIndex < text.length) {
    parts.push(text.substring(currentIndex));
  }

  return parts.length > 0 ? parts : text;
}
