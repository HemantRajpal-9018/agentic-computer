"use client";

import {
  Activity,
  Brain,
  Wrench,
  GitBranch,
  ArrowRight,
  Zap,
  MessageSquare,
  Clock,
  CheckCircle2,
  AlertCircle,
  Play,
} from "lucide-react";

const stats = [
  {
    label: "Active Tasks",
    value: "3",
    change: "+2 today",
    icon: Activity,
    color: "text-blue-400",
    bgColor: "bg-blue-400/10",
    glowClass: "glow-primary",
  },
  {
    label: "Memory Entries",
    value: "1,247",
    change: "+18 today",
    icon: Brain,
    color: "text-purple-400",
    bgColor: "bg-purple-400/10",
    glowClass: "glow-primary",
  },
  {
    label: "Tools Available",
    value: "24",
    change: "All active",
    icon: Wrench,
    color: "text-emerald-400",
    bgColor: "bg-emerald-400/10",
    glowClass: "glow-success",
  },
  {
    label: "Workflows",
    value: "7",
    change: "2 running",
    icon: GitBranch,
    color: "text-amber-400",
    bgColor: "bg-amber-400/10",
    glowClass: "glow-warning",
  },
];

const recentActivity = [
  {
    id: 1,
    type: "task",
    title: "Code review completed",
    description: "Reviewed PR #142 - Authentication middleware refactor",
    time: "2 minutes ago",
    status: "completed",
    icon: CheckCircle2,
  },
  {
    id: 2,
    type: "memory",
    title: "New memory stored",
    description: "Project architecture decision: switched to event-driven pattern",
    time: "8 minutes ago",
    status: "completed",
    icon: Brain,
  },
  {
    id: 3,
    type: "workflow",
    title: "Deploy pipeline running",
    description: "Staging deployment for feature/auth-v2 branch",
    time: "15 minutes ago",
    status: "running",
    icon: Play,
  },
  {
    id: 4,
    type: "error",
    title: "Tool execution failed",
    description: "database_query timed out after 30s - retrying with cache",
    time: "22 minutes ago",
    status: "error",
    icon: AlertCircle,
  },
  {
    id: 5,
    type: "task",
    title: "Test suite passed",
    description: "All 847 tests passing across 12 test suites",
    time: "35 minutes ago",
    status: "completed",
    icon: CheckCircle2,
  },
];

const quickActions = [
  { label: "New Chat", icon: MessageSquare, description: "Start a conversation with the agent" },
  { label: "Run Workflow", icon: Play, description: "Execute a predefined workflow" },
  { label: "Search Memory", icon: Brain, description: "Query the agent's memory store" },
  { label: "View Tools", icon: Wrench, description: "Browse available tools and APIs" },
];

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: "bg-emerald-500",
    running: "bg-blue-500 animate-pulse-dot",
    error: "bg-red-500",
    pending: "bg-amber-500",
  };
  return <div className={`h-2 w-2 rounded-full ${colors[status] || colors.pending}`} />;
}

export default function DashboardPage() {
  return (
    <div className="p-6 lg:p-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Monitor your agentic system at a glance
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.label}
              className={`rounded-lg border border-border bg-card p-5 transition-shadow hover:${stat.glowClass}`}
            >
              <div className="flex items-center justify-between">
                <div className={`rounded-md p-2 ${stat.bgColor}`}>
                  <Icon className={`h-5 w-5 ${stat.color}`} />
                </div>
                <span className="text-xs text-muted-foreground">
                  {stat.change}
                </span>
              </div>
              <div className="mt-3">
                <p className="text-2xl font-bold text-foreground">
                  {stat.value}
                </p>
                <p className="text-sm text-muted-foreground">{stat.label}</p>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent Activity */}
        <div className="lg:col-span-2 rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <h2 className="font-semibold text-foreground">
                Recent Activity
              </h2>
            </div>
            <button className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors">
              View all
              <ArrowRight className="h-3 w-3" />
            </button>
          </div>
          <div className="divide-y divide-border">
            {recentActivity.map((activity) => {
              const Icon = activity.icon;
              return (
                <div
                  key={activity.id}
                  className="flex items-start gap-4 px-5 py-4 hover:bg-accent/50 transition-colors"
                >
                  <div className="mt-0.5 rounded-md bg-muted p-2">
                    <Icon
                      className={`h-4 w-4 ${
                        activity.status === "error"
                          ? "text-red-400"
                          : activity.status === "running"
                          ? "text-blue-400"
                          : "text-emerald-400"
                      }`}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground">
                        {activity.title}
                      </p>
                      <StatusDot status={activity.status} />
                    </div>
                    <p className="mt-0.5 text-sm text-muted-foreground truncate">
                      {activity.description}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {activity.time}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="rounded-lg border border-border bg-card">
          <div className="flex items-center gap-2 border-b border-border px-5 py-4">
            <Zap className="h-4 w-4 text-muted-foreground" />
            <h2 className="font-semibold text-foreground">Quick Actions</h2>
          </div>
          <div className="space-y-2 p-4">
            {quickActions.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.label}
                  className="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left transition-colors hover:bg-accent group"
                >
                  <div className="rounded-md bg-primary/10 p-2 group-hover:bg-primary/20 transition-colors">
                    <Icon className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {action.label}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {action.description}
                    </p>
                  </div>
                  <ArrowRight className="ml-auto h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* System Status Bar */}
      <div className="rounded-lg border border-border bg-card px-5 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-emerald-500" />
              <span className="text-xs text-muted-foreground">
                System: Healthy
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-emerald-500" />
              <span className="text-xs text-muted-foreground">
                API: Connected
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse-dot" />
              <span className="text-xs text-muted-foreground">
                Agent: Processing
              </span>
            </div>
          </div>
          <span className="text-xs text-muted-foreground">
            Last sync: just now
          </span>
        </div>
      </div>
    </div>
  );
}
