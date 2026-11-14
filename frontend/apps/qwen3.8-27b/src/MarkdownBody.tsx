import React from "react";
import { Button, CopyOutlined, useStudioFeedback } from "@colab/shared";

interface Segment {
  kind: "text" | "code";
  lang?: string;
  value: string;
}

function splitCodeFences(raw: string): Segment[] {
  const segments: Segment[] = [];
  const fenceRegex = /```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null = null;

  while ((match = fenceRegex.exec(raw)) !== null) {
    if (match.index > lastIdx) {
      segments.push({ kind: "text", value: raw.slice(lastIdx, match.index) });
    }
    segments.push({
      kind: "code",
      lang: (match[1] || "code").trim(),
      value: match[2].replace(/\n$/, ""),
    });
    lastIdx = match.index + match[0].length;
  }

  const tail = raw.slice(lastIdx);
  if (tail) {
    const unclosed = tail.match(/```([a-zA-Z0-9_+-]*)\n([\s\S]*)$/);
    if (unclosed && unclosed.index != null) {
      if (unclosed.index > 0) {
        segments.push({ kind: "text", value: tail.slice(0, unclosed.index) });
      }
      segments.push({
        kind: "code",
        lang: (unclosed[1] || "code").trim(),
        value: unclosed[2],
      });
    } else {
      segments.push({ kind: "text", value: tail });
    }
  }

  return segments;
}

function renderInlineNodes(text: string): React.ReactNode[] {
  const tokens = text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g);
  return tokens.map((tok, idx) => {
    if (tok.startsWith("`") && tok.endsWith("`") && tok.length >= 2) {
      return (
        <code key={idx} className="studio-md-inline-code">
          {tok.slice(1, -1)}
        </code>
      );
    }
    if (tok.startsWith("**") && tok.endsWith("**") && tok.length >= 4) {
      return <strong key={idx}>{tok.slice(2, -2)}</strong>;
    }
    return <React.Fragment key={idx}>{tok}</React.Fragment>;
  });
}

function renderProseBlock(block: string, keyPrefix: string): React.ReactNode {
  const paragraphs = block
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);

  return paragraphs.map((para, pIdx) => {
    const key = `${keyPrefix}-${pIdx}`;
    const lines = para.split("\n");
    if (lines.every((l) => l.trim().startsWith(">"))) {
      const clean = lines.map((l) => l.replace(/^\s*>\s?/, "")).join("\n");
      return <blockquote key={key}>{renderInlineNodes(clean)}</blockquote>;
    }
    if (lines.length === 1 && /^#{1,4}\s+/.test(lines[0])) {
      const m = lines[0].match(/^(#{1,4})\s+(.*)$/);
      const level = m ? m[1].length : 3;
      const headingText = m ? m[2] : lines[0];
      const fontSize = level === 1 ? "1.08rem" : level === 2 ? "1.0rem" : "0.95rem";
      return (
        <div key={key} style={{ fontWeight: 700, fontSize, marginBlockStart: 2 }}>
          {renderInlineNodes(headingText)}
        </div>
      );
    }
    return <p key={key}>{renderInlineNodes(para)}</p>;
  });
}

export function MarkdownBody({ text }: { text: string }) {
  const { message } = useStudioFeedback();
  const segments = splitCodeFences(text);

  const handleCopyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      message.success("代码已复制");
    } catch {
      message.warning("复制失败，请手动选中复制");
    }
  };

  return (
    <div className="studio-md-content">
      {segments.map((seg, idx) => {
        if (seg.kind === "code") {
          return (
            <div key={idx} className="studio-md-codeblock">
              <div className="studio-md-codeheader">
                <span>{seg.lang || "code"}</span>
                <Button
                  htmlType="button"
                  size="small"
                  type="text"
                  icon={<CopyOutlined />}
                  style={{ blockSize: 22, paddingInline: 6, fontSize: 11.5 }}
                  onClick={() => void handleCopyCode(seg.value)}
                >
                  复制
                </Button>
              </div>
              <pre className="studio-md-codepre">{seg.value}</pre>
            </div>
          );
        }
        return <React.Fragment key={idx}>{renderProseBlock(seg.value, `prose-${idx}`)}</React.Fragment>;
      })}
    </div>
  );
}
