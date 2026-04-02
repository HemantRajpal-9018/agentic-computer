"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Brain,
  Code,
  FileText,
  MessageSquare,
  Lightbulb,
  Database,
} from "lucide-react";

export interface MemoryEntry {
  id: string;
  type: "episodic" | "semantic" | "procedural" | "conversation" | "fact" | "preference";
  title: string;
  content: string;
  timestamp: string;
  tags?: string[];
  relevance?: number;
}

interface MemoryTimelineProps {
  entries: MemoryEntry[];
}

const typeConfig: Record<
  MemoryEntry["type"],
  { icon: typeof Brain; color: string; bg: string; label: string }
> = {
  episodic: {
    icon: MessageSquare,
    color: "text-blue-400",
    bg: "bg-blue-400/10",
    label: "Episodic",
  },
  semantic: {
    icon: Brain,
    color: "text-purple-400",
    bg: "bg-purple-400/10",
    label: "Semantic",
  },
  procedural: {
    icon: Code,
    color: "text-emerald-400",
    bg: "bg-emerald-400/10",
    label: "Procedural",
  },
  conversation: {
    icon: MessageSquare,
    color: "text-cyan-400",
    bg: "bg-cyan-400/10",
    label: "Conversation",
  },
  fact: {
    icon: Database,
    color: "text-amber-400",
    bg: "bg-amber-400/10",
    label: "Fact",
  },
  preference: {
    icon: Lightbulb,
    color: "text-pink-400",
    bg: "bg-pink-400/10",
    label: "Preference",
  },
};

function MemoryTimelineEntry({ entry }: { entry: MemoryEntry }) {
  const [expanded, setExpanded] = useState(false);
  const config = typeConfig[entry.type];
  const Icon = config.icon;

  return (
    <div className="relative flex gap-4 pb-8 last:pb-0">
      {/* Timeline line */}
      <div className="absolute left-[15px] top-8 bottom-0 w-px bg-border last:hidden" />

      {/* Timeline dot */}
      <div
        className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${config.bg} ring-4 ring-background`}
      >
        <Icon className={`h-4 w-4 ${config.color}`} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-start gap-2 text-left group"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${config.bg} ${config.color}`}
              >
                {config.label}
              </span>
              {entry.relevance !== undefined && (
                <span className="text-[10px] text-muted-foreground">
                  {Math.round(entry.relevance * 100)}% relevance
                </span>
              )}
            </div>
            <p className="mt-1 text-sm font-medium text-foreground">
              {entry.title}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {entry.timestamp}
            </p>
          </div>
          <div className="mt-1 shrink-0">
            {expanded ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
            )}
          </div>
        </button>

        {/* Expanded content */}
        {expanded && (
          <div className="mt-3 animate-fade-in">
            <div className="rounded-lg border border-border bg-card p-4">
              <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                {entry.content}
              </p>
              {entry.tags && entry.tags.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {entry.tags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                    >
                      #{tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function MemoryTimeline({ entries }: MemoryTimelineProps) {
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <Brain className="h-12 w-12 text-border" />
        <p className="mt-4 text-sm">No memory entries found</p>
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {entries.map((entry) => (
        <MemoryTimelineEntry key={entry.id} entry={entry} />
      ))}
    </div>
  );
}
