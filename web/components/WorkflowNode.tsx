"use client";

import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  ArrowRight,
  Zap,
  GitBranch,
  FileCode,
  Database,
  Send,
} from "lucide-react";

export interface WorkflowNodeProps {
  name: string;
  status: "pending" | "running" | "completed" | "error";
  type: "trigger" | "action" | "condition" | "output";
  connections?: string[];
  description?: string;
}

const typeConfig = {
  trigger: {
    icon: Zap,
    borderColor: "border-amber-500/50",
    bgColor: "bg-amber-500/10",
    iconColor: "text-amber-400",
  },
  action: {
    icon: FileCode,
    borderColor: "border-blue-500/50",
    bgColor: "bg-blue-500/10",
    iconColor: "text-blue-400",
  },
  condition: {
    icon: GitBranch,
    borderColor: "border-purple-500/50",
    bgColor: "bg-purple-500/10",
    iconColor: "text-purple-400",
  },
  output: {
    icon: Send,
    borderColor: "border-emerald-500/50",
    bgColor: "bg-emerald-500/10",
    iconColor: "text-emerald-400",
  },
};

const statusConfig = {
  pending: {
    icon: Circle,
    color: "text-muted-foreground",
    label: "Pending",
  },
  running: {
    icon: Loader2,
    color: "text-blue-400",
    label: "Running",
  },
  completed: {
    icon: CheckCircle2,
    color: "text-emerald-400",
    label: "Completed",
  },
  error: {
    icon: XCircle,
    color: "text-red-400",
    label: "Error",
  },
};

export default function WorkflowNode({
  name,
  status,
  type,
  description,
}: WorkflowNodeProps) {
  const tConfig = typeConfig[type];
  const sConfig = statusConfig[status];
  const TypeIcon = tConfig.icon;
  const StatusIcon = sConfig.icon;

  return (
    <div className="flex items-center gap-3">
      <div
        className={`relative rounded-lg border ${tConfig.borderColor} bg-card p-4 min-w-[200px] transition-shadow hover:shadow-md`}
      >
        {/* Connection point left */}
        <div className="absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 h-3 w-3 rounded-full border-2 border-border bg-card" />
        {/* Connection point right */}
        <div className="absolute right-0 top-1/2 translate-x-1/2 -translate-y-1/2 h-3 w-3 rounded-full border-2 border-border bg-card" />

        <div className="flex items-start gap-3">
          <div className={`rounded-md p-1.5 ${tConfig.bgColor}`}>
            <TypeIcon className={`h-4 w-4 ${tConfig.iconColor}`} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground">{name}</p>
            {description && (
              <p className="mt-0.5 text-xs text-muted-foreground truncate">
                {description}
              </p>
            )}
          </div>
          <StatusIcon
            className={`h-4 w-4 shrink-0 ${sConfig.color} ${
              status === "running" ? "animate-spin" : ""
            }`}
          />
        </div>

        {/* Type badge */}
        <div className="mt-2">
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${tConfig.bgColor} ${tConfig.iconColor}`}
          >
            {type}
          </span>
        </div>
      </div>

      {/* Connector arrow */}
      <ArrowRight className="h-4 w-4 shrink-0 text-border" />
    </div>
  );
}
