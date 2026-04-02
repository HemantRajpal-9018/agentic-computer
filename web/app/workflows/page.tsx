"use client";

import { useState } from "react";
import {
  Play,
  Plus,
  GitBranch,
  Clock,
  CheckCircle2,
  FileCode,
  Database,
  Mail,
  Shield,
  Zap,
} from "lucide-react";
import WorkflowNode, { WorkflowNodeProps } from "@/components/WorkflowNode";

interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  icon: typeof Play;
  steps: number;
  lastRun?: string;
  status: "idle" | "running" | "completed" | "error";
  nodes: WorkflowNodeProps[];
}

const workflowTemplates: WorkflowTemplate[] = [
  {
    id: "code-review",
    name: "Automated Code Review",
    description:
      "Analyze PRs for code quality, security vulnerabilities, and best practice violations",
    icon: FileCode,
    steps: 4,
    lastRun: "12 minutes ago",
    status: "completed",
    nodes: [
      {
        name: "PR Trigger",
        status: "completed",
        type: "trigger",
        description: "Watch for new PRs",
      },
      {
        name: "Analyze Code",
        status: "completed",
        type: "action",
        description: "Run static analysis",
      },
      {
        name: "Check Security",
        status: "completed",
        type: "condition",
        description: "Scan for vulnerabilities",
      },
      {
        name: "Post Review",
        status: "completed",
        type: "output",
        description: "Comment on PR",
      },
    ],
  },
  {
    id: "data-pipeline",
    name: "Data Pipeline Sync",
    description:
      "Extract, transform, and load data between databases with validation checks",
    icon: Database,
    steps: 5,
    lastRun: "1 hour ago",
    status: "running",
    nodes: [
      {
        name: "Schedule",
        status: "completed",
        type: "trigger",
        description: "Cron: */30 * * * *",
      },
      {
        name: "Extract Data",
        status: "completed",
        type: "action",
        description: "Query source DB",
      },
      {
        name: "Validate",
        status: "running",
        type: "condition",
        description: "Schema validation",
      },
      {
        name: "Transform",
        status: "pending",
        type: "action",
        description: "Apply mappings",
      },
      {
        name: "Load",
        status: "pending",
        type: "output",
        description: "Insert to target",
      },
    ],
  },
  {
    id: "incident-response",
    name: "Incident Response",
    description:
      "Automated incident detection, notification, and initial triage workflow",
    icon: Shield,
    steps: 4,
    status: "idle",
    nodes: [
      {
        name: "Alert Monitor",
        status: "pending",
        type: "trigger",
        description: "Watch alerts",
      },
      {
        name: "Triage",
        status: "pending",
        type: "condition",
        description: "Severity check",
      },
      {
        name: "Investigate",
        status: "pending",
        type: "action",
        description: "Gather context",
      },
      {
        name: "Notify Team",
        status: "pending",
        type: "output",
        description: "Send alerts",
      },
    ],
  },
  {
    id: "deploy-notify",
    name: "Deploy & Notify",
    description:
      "Build, test, deploy to staging, and notify the team via Slack with deployment details",
    icon: Mail,
    steps: 4,
    lastRun: "3 hours ago",
    status: "completed",
    nodes: [
      {
        name: "Git Push",
        status: "completed",
        type: "trigger",
        description: "On merge to main",
      },
      {
        name: "Build & Test",
        status: "completed",
        type: "action",
        description: "CI pipeline",
      },
      {
        name: "Deploy Staging",
        status: "completed",
        type: "action",
        description: "K8s rollout",
      },
      {
        name: "Send Notification",
        status: "completed",
        type: "output",
        description: "Slack message",
      },
    ],
  },
];

function StatusBadge({ status }: { status: WorkflowTemplate["status"] }) {
  const config = {
    idle: { label: "Idle", bg: "bg-muted", text: "text-muted-foreground" },
    running: { label: "Running", bg: "bg-blue-500/10", text: "text-blue-400" },
    completed: {
      label: "Completed",
      bg: "bg-emerald-500/10",
      text: "text-emerald-400",
    },
    error: { label: "Error", bg: "bg-red-500/10", text: "text-red-400" },
  };
  const c = config[status];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${c.bg} ${c.text}`}
    >
      {c.label}
    </span>
  );
}

export default function WorkflowsPage() {
  const [selected, setSelected] = useState<string | null>("code-review");
  const selectedWorkflow = workflowTemplates.find((w) => w.id === selected);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Workflows</h1>
          <p className="text-xs text-muted-foreground">
            Build and run automated task pipelines
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90">
          <Plus className="h-4 w-4" />
          New Workflow
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Workflow List */}
        <div className="w-96 shrink-0 overflow-y-auto border-r border-border">
          <div className="space-y-1 p-3">
            {workflowTemplates.map((wf) => {
              const Icon = wf.icon;
              const isSelected = selected === wf.id;
              return (
                <button
                  key={wf.id}
                  onClick={() => setSelected(wf.id)}
                  className={`flex w-full items-start gap-3 rounded-lg p-3 text-left transition-colors ${
                    isSelected
                      ? "bg-primary/10 border border-primary/20"
                      : "hover:bg-accent border border-transparent"
                  }`}
                >
                  <div
                    className={`rounded-md p-2 ${
                      isSelected ? "bg-primary/20" : "bg-muted"
                    }`}
                  >
                    <Icon
                      className={`h-4 w-4 ${
                        isSelected ? "text-primary" : "text-muted-foreground"
                      }`}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-foreground truncate">
                        {wf.name}
                      </p>
                      <StatusBadge status={wf.status} />
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
                      {wf.description}
                    </p>
                    <div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <GitBranch className="h-3 w-3" />
                        {wf.steps} steps
                      </span>
                      {wf.lastRun && (
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {wf.lastRun}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Workflow Detail */}
        <div className="flex-1 overflow-y-auto p-6">
          {selectedWorkflow ? (
            <div className="space-y-6">
              {/* Workflow header */}
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-foreground">
                    {selectedWorkflow.name}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {selectedWorkflow.description}
                  </p>
                </div>
                <button
                  className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                    selectedWorkflow.status === "running"
                      ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                      : "bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                  }`}
                >
                  <Play className="h-4 w-4" />
                  {selectedWorkflow.status === "running"
                    ? "Running..."
                    : "Run Workflow"}
                </button>
              </div>

              {/* Step indicators */}
              <div className="rounded-lg border border-border bg-card p-6">
                <h3 className="mb-4 text-sm font-medium text-foreground">
                  Pipeline Steps
                </h3>

                {/* Progress bar */}
                <div className="mb-6 flex items-center gap-2">
                  {selectedWorkflow.nodes.map((node, idx) => (
                    <div key={idx} className="flex flex-1 items-center gap-2">
                      <div
                        className={`h-1.5 flex-1 rounded-full ${
                          node.status === "completed"
                            ? "bg-emerald-500"
                            : node.status === "running"
                            ? "bg-blue-500 animate-pulse-dot"
                            : node.status === "error"
                            ? "bg-red-500"
                            : "bg-border"
                        }`}
                      />
                    </div>
                  ))}
                </div>

                {/* Node cards */}
                <div className="flex flex-wrap items-center gap-2">
                  {selectedWorkflow.nodes.map((node, idx) => (
                    <WorkflowNode key={idx} {...node} />
                  ))}
                </div>
              </div>

              {/* Workflow stats */}
              <div className="grid grid-cols-3 gap-4">
                <div className="rounded-lg border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground">Total Runs</p>
                  <p className="mt-1 text-2xl font-bold text-foreground">
                    47
                  </p>
                </div>
                <div className="rounded-lg border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground">Success Rate</p>
                  <p className="mt-1 text-2xl font-bold text-emerald-400">
                    94%
                  </p>
                </div>
                <div className="rounded-lg border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground">Avg Duration</p>
                  <p className="mt-1 text-2xl font-bold text-foreground">
                    2.3m
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <div className="text-center">
                <Zap className="mx-auto h-12 w-12 text-border" />
                <p className="mt-4 text-sm">
                  Select a workflow to view details
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
