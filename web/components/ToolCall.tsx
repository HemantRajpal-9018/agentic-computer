"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
} from "lucide-react";

export interface ToolCallProps {
  name: string;
  params: Record<string, unknown>;
  result?: string;
  status: "pending" | "running" | "done" | "error";
  duration?: string;
}

const statusConfig = {
  pending: {
    icon: Circle,
    color: "text-amber-400",
    dotColor: "bg-amber-400",
    label: "Pending",
  },
  running: {
    icon: Loader2,
    color: "text-blue-400",
    dotColor: "bg-blue-400 animate-pulse-dot",
    label: "Running",
  },
  done: {
    icon: CheckCircle2,
    color: "text-emerald-400",
    dotColor: "bg-emerald-400",
    label: "Done",
  },
  error: {
    icon: XCircle,
    color: "text-red-400",
    dotColor: "bg-red-400",
    label: "Error",
  },
};

export default function ToolCall({
  name,
  params,
  result,
  status,
  duration,
}: ToolCallProps) {
  const [expanded, setExpanded] = useState(false);
  const config = statusConfig[status];
  const StatusIcon = config.icon;

  return (
    <div className="rounded-md border border-border bg-secondary/50 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-accent/50 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
        )}

        {/* Status dot */}
        <div className={`h-2 w-2 rounded-full shrink-0 ${config.dotColor}`} />

        {/* Tool name */}
        <code className="text-xs font-mono font-medium text-foreground">
          {name}
        </code>

        {/* Status and duration */}
        <div className="ml-auto flex items-center gap-2">
          {duration && (
            <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <Clock className="h-3 w-3" />
              {duration}
            </span>
          )}
          <span className={`flex items-center gap-1 text-[10px] ${config.color}`}>
            <StatusIcon
              className={`h-3 w-3 ${status === "running" ? "animate-spin" : ""}`}
            />
            {config.label}
          </span>
        </div>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-border">
          {/* Parameters */}
          <div className="px-3 py-2">
            <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Parameters
            </p>
            <pre className="overflow-x-auto rounded bg-black/30 px-3 py-2 font-mono text-xs text-muted-foreground">
              {JSON.stringify(params, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {result && (
            <div className="border-t border-border px-3 py-2">
              <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Result
              </p>
              <pre
                className={`overflow-x-auto rounded px-3 py-2 font-mono text-xs ${
                  status === "error"
                    ? "bg-red-500/10 text-red-300"
                    : "bg-black/30 text-emerald-300"
                }`}
              >
                {result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
