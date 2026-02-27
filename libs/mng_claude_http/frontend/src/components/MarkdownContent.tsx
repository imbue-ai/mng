import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import hljs from "highlight.js/lib/core";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import python from "highlight.js/lib/languages/python";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import css from "highlight.js/lib/languages/css";
import xml from "highlight.js/lib/languages/xml";
import "highlight.js/styles/github-dark.css";

// Register languages
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("js", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("ts", typescript);
hljs.registerLanguage("tsx", typescript);
hljs.registerLanguage("jsx", javascript);
hljs.registerLanguage("python", python);
hljs.registerLanguage("py", python);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("sh", bash);
hljs.registerLanguage("shell", bash);
hljs.registerLanguage("json", json);
hljs.registerLanguage("css", css);
hljs.registerLanguage("html", xml);
hljs.registerLanguage("xml", xml);

interface MarkdownContentProps {
  text: string;
}

export const MarkdownContent = ({ text }: MarkdownContentProps) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.querySelectorAll("pre code:not(.hljs)").forEach((el) => {
        hljs.highlightElement(el as HTMLElement);
      });
    }
  }, [text]);

  return (
    <div ref={containerRef} style={{ fontSize: "14px", lineHeight: "1.6" }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const isInline = !match && !className;

            if (isInline) {
              return (
                <code
                  style={{
                    backgroundColor: "var(--code-bg)",
                    padding: "2px 6px",
                    borderRadius: "3px",
                    fontSize: "0.9em",
                  }}
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children }) {
            return (
              <pre
                style={{
                  overflow: "auto",
                  padding: "12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--code-bg)",
                  fontSize: "13px",
                  lineHeight: "1.5",
                  margin: "8px 0",
                }}
              >
                {children}
              </pre>
            );
          },
          table({ children }) {
            return (
              <div style={{ overflowX: "auto", margin: "8px 0" }}>
                <table
                  style={{
                    borderCollapse: "collapse",
                    width: "100%",
                    fontSize: "13px",
                  }}
                >
                  {children}
                </table>
              </div>
            );
          },
          th({ children }) {
            return (
              <th
                style={{
                  border: "1px solid var(--border)",
                  padding: "6px 12px",
                  backgroundColor: "var(--bg-tertiary)",
                  textAlign: "left",
                }}
              >
                {children}
              </th>
            );
          },
          td({ children }) {
            return (
              <td
                style={{
                  border: "1px solid var(--border)",
                  padding: "6px 12px",
                }}
              >
                {children}
              </td>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
};
