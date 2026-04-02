"use client";

import { User, Bot, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import ToolCall from "./ToolCall";

export interface ToolCallData {
  name: string;
  params: Record<string, unknown>;
  result?: string;
  status: "pending" | "running" | "done" | "error";
  duration?: string;
}

export interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  toolCalls?: ToolCallData[];
}

export default function ChatMessage({
  role,
  content,
  timestamp,
  toolCalls,
}: ChatMessageProps) {
  const [showTools, setShowTools] = useState(true);
  const isUser = role === "user";

  return (
    <div
      className={`flex gap-3 animate-fade-in ${
        isUser ? "flex-row-reverse" : ""
      }`}
    >
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isUser
            ? "bg-primary/20 text-primary"
            : "bg-emerald-500/20 text-emerald-400"
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[75%] space-y-2`}>
        <div
          className={`rounded-lg px-4 py-3 ${
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-card border border-border text-foreground"
          }`}
        >
          {/* Render content with basic markdown-like formatting */}
          <div className="text-sm leading-relaxed whitespace-pre-wrap">
            {content.split("```").map((block, i) => {
              if (i % 2 === 1) {
                // Code block
                return (
                  <pre
                    key={i}
                    className="my-2 overflow-x-auto rounded-md bg-black/30 px-3 py-2 font-mono text-xs"
                  >
                    <code>{block.replace(/^\w+\n/, "")}</code>
                  </pre>
                );
              }
              // Regular text with inline code
              return (
                <span key={i}>
                  {block.split("`").map((segment, j) => {
                    if (j % 2 === 1) {
                      return (
                        <code
                          key={j}
                          className="rounded bg-black/20 px-1.5 py-0.5 font-mono text-xs"
                        >
                          {segment}
                        </code>
                      );
                    }
                    // Bold text
                    return segment.split("**").map((part, k) => {
                      if (k % 2 === 1) {
                        return (
                          <strong key={`${j}-${k}`} className="font-semibold">
                            {part}
                          </strong>
                        );
                      }
                      return <span key={`${j}-${k}`}>{part}</span>;
                    });
                  })}
                </span>
              );
            })}
          </div>
        </div>

        {/* Tool Calls */}
        {toolCalls && toolCalls.length > 0 && (
          <div className="w-full space-y-2">
            <button
              onClick={() => setShowTools(!showTools)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {showTools ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              {toolCalls.length} tool call{toolCalls.length > 1 ? "s" : ""}
            </button>
            {showTools && (
              <div className="space-y-2">
                {toolCalls.map((tool, idx) => (
                  <ToolCall
                    key={idx}
                    name={tool.name}
                    params={tool.params}
                    result={tool.result}
                    status={tool.status}
                    duration={tool.duration}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        <span className="text-[10px] text-muted-foreground">{timestamp}</span>
      </div>
    </div>
  );
}
