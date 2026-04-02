"use client";

import { useState, useMemo } from "react";
import { Search, Filter, SlidersHorizontal, Brain } from "lucide-react";
import MemoryTimeline, { MemoryEntry } from "@/components/MemoryTimeline";

const allMemories: MemoryEntry[] = [
  {
    id: "1",
    type: "semantic",
    title: "Project uses event-driven architecture with RabbitMQ",
    content:
      "The agentic-computer project follows an event-driven architecture pattern. All inter-service communication is handled through RabbitMQ message queues. Key exchanges include: task.exchange (for task routing), memory.exchange (for memory updates), and tool.exchange (for tool execution requests). Dead letter queues are configured for error handling.",
    timestamp: "Today, 10:30 AM",
    tags: ["architecture", "rabbitmq", "events"],
    relevance: 0.97,
  },
  {
    id: "2",
    type: "episodic",
    title: "Debugged authentication middleware timeout issue",
    content:
      "User reported that the auth middleware was causing 504 timeouts on high-traffic endpoints. Root cause was the JWT verification using a synchronous bcrypt comparison for token refresh checks. Fixed by switching to async verification and adding a token cache with 5-minute TTL. Response times improved from 2.3s to 45ms p99.",
    timestamp: "Today, 9:15 AM",
    tags: ["debugging", "auth", "performance"],
    relevance: 0.92,
  },
  {
    id: "3",
    type: "procedural",
    title: "Deploy to staging environment procedure",
    content:
      "1. Run full test suite: npm run test:all\n2. Build Docker images: docker compose build\n3. Push to registry: docker push registry.internal/agentic-computer:staging\n4. Apply K8s manifests: kubectl apply -f k8s/staging/\n5. Verify health checks: curl https://staging.internal/health\n6. Run smoke tests: npm run test:smoke -- --env=staging\n7. Notify team in #deploys Slack channel",
    timestamp: "Today, 8:00 AM",
    tags: ["deployment", "staging", "procedure"],
    relevance: 0.85,
  },
  {
    id: "4",
    type: "conversation",
    title: "User prefers TypeScript strict mode for all new code",
    content:
      "During code review discussion, the user expressed strong preference for TypeScript strict mode being enabled in all new projects. This includes strictNullChecks, noImplicitAny, noImplicitReturns, and strictFunctionTypes. All new tsconfig.json files should have strict: true.",
    timestamp: "Yesterday, 4:45 PM",
    tags: ["typescript", "preferences", "code-style"],
    relevance: 0.88,
  },
  {
    id: "5",
    type: "fact",
    title: "Database connection pool limit is 20 for production",
    content:
      "Production PostgreSQL database has a connection pool limit of 20 connections. This is configured in the DATABASE_POOL_SIZE environment variable. The staging environment allows 10 connections. Connection pooling is handled by PgBouncer in transaction mode. If pool is exhausted, queries queue for up to 30 seconds before timeout.",
    timestamp: "Yesterday, 2:30 PM",
    tags: ["database", "production", "config"],
    relevance: 0.79,
  },
  {
    id: "6",
    type: "preference",
    title: "Use Vitest over Jest for new test suites",
    content:
      "Project standard is to use Vitest instead of Jest for all new test suites. Vitest provides better ESM support, faster execution via native ES modules, and seamless integration with Vite-based projects. Existing Jest tests should be migrated when files are significantly modified.",
    timestamp: "Yesterday, 11:00 AM",
    tags: ["testing", "vitest", "standards"],
    relevance: 0.82,
  },
  {
    id: "7",
    type: "semantic",
    title: "API rate limiting strategy: token bucket with Redis",
    content:
      "The API uses a token bucket rate limiting strategy backed by Redis. Default limits: 100 requests/minute for authenticated users, 20 requests/minute for anonymous. Premium tier gets 500 requests/minute. Rate limit headers (X-RateLimit-Remaining, X-RateLimit-Reset) are included in all responses. Burst allowance is 2x the per-minute rate.",
    timestamp: "2 days ago",
    tags: ["api", "rate-limiting", "redis"],
    relevance: 0.75,
  },
  {
    id: "8",
    type: "episodic",
    title: "Resolved memory leak in WebSocket connection handler",
    content:
      "Identified and fixed a memory leak in the WebSocket connection handler. Event listeners were not being cleaned up on disconnect, causing ~2MB leak per connection cycle. Added proper cleanup in the disconnect handler and implemented a periodic garbage collection check. Memory usage stabilized after the fix.",
    timestamp: "2 days ago",
    tags: ["memory-leak", "websocket", "fix"],
    relevance: 0.71,
  },
  {
    id: "9",
    type: "procedural",
    title: "How to add a new tool to the agent",
    content:
      "1. Create tool definition in src/tools/<tool-name>.ts\n2. Implement the ToolInterface with execute() and describe() methods\n3. Register tool in src/tools/registry.ts\n4. Add tool tests in tests/tools/<tool-name>.test.ts\n5. Update tool documentation in docs/tools.md\n6. Add tool to the agent's tool list in src/agent/config.ts",
    timestamp: "3 days ago",
    tags: ["tools", "development", "guide"],
    relevance: 0.68,
  },
  {
    id: "10",
    type: "fact",
    title: "Supported LLM providers: OpenAI, Anthropic, local Ollama",
    content:
      "The system supports three LLM providers:\n- OpenAI: GPT-4, GPT-3.5-turbo (via API key)\n- Anthropic: Claude 3.5 Sonnet, Claude 3 Haiku (via API key)\n- Local: Ollama with Llama 3, Mistral, CodeLlama (self-hosted)\n\nProvider is configured via LLM_PROVIDER env var. Default is Anthropic Claude 3.5 Sonnet.",
    timestamp: "3 days ago",
    tags: ["llm", "providers", "config"],
    relevance: 0.65,
  },
];

const memoryTypes: MemoryEntry["type"][] = [
  "episodic",
  "semantic",
  "procedural",
  "conversation",
  "fact",
  "preference",
];

const typeLabels: Record<MemoryEntry["type"], string> = {
  episodic: "Episodic",
  semantic: "Semantic",
  procedural: "Procedural",
  conversation: "Conversation",
  fact: "Fact",
  preference: "Preference",
};

const typeColors: Record<MemoryEntry["type"], string> = {
  episodic: "bg-blue-400/10 text-blue-400 border-blue-400/30",
  semantic: "bg-purple-400/10 text-purple-400 border-purple-400/30",
  procedural: "bg-emerald-400/10 text-emerald-400 border-emerald-400/30",
  conversation: "bg-cyan-400/10 text-cyan-400 border-cyan-400/30",
  fact: "bg-amber-400/10 text-amber-400 border-amber-400/30",
  preference: "bg-pink-400/10 text-pink-400 border-pink-400/30",
};

export default function MemoryPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState<Set<MemoryEntry["type"]>>(
    new Set()
  );
  const [showFilters, setShowFilters] = useState(false);

  const toggleFilter = (type: MemoryEntry["type"]) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  const filteredMemories = useMemo(() => {
    return allMemories.filter((entry) => {
      const matchesSearch =
        searchQuery === "" ||
        entry.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        entry.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
        entry.tags?.some((tag) =>
          tag.toLowerCase().includes(searchQuery.toLowerCase())
        );

      const matchesFilter =
        activeFilters.size === 0 || activeFilters.has(entry.type);

      return matchesSearch && matchesFilter;
    });
  }, [searchQuery, activeFilters]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-foreground">
              Memory Browser
            </h1>
            <p className="text-xs text-muted-foreground">
              Explore and search the agent&apos;s memory store
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Brain className="h-4 w-4" />
            <span>{allMemories.length} entries</span>
          </div>
        </div>

        {/* Search Bar */}
        <div className="mt-4 flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search memories by title, content, or tags..."
              className="w-full rounded-lg border border-border bg-input py-2.5 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors ${
              showFilters || activeFilters.size > 0
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-border bg-input text-muted-foreground hover:text-foreground"
            }`}
          >
            <SlidersHorizontal className="h-4 w-4" />
            Filters
            {activeFilters.size > 0 && (
              <span className="ml-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] font-medium text-primary-foreground">
                {activeFilters.size}
              </span>
            )}
          </button>
        </div>

        {/* Filter pills */}
        {showFilters && (
          <div className="mt-3 flex flex-wrap gap-2 animate-fade-in">
            {memoryTypes.map((type) => {
              const isActive = activeFilters.has(type);
              return (
                <button
                  key={type}
                  onClick={() => toggleFilter(type)}
                  className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                    isActive
                      ? typeColors[type]
                      : "border-border bg-muted text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {typeLabels[type]}
                </button>
              );
            })}
            {activeFilters.size > 0 && (
              <button
                onClick={() => setActiveFilters(new Set())}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors underline"
              >
                Clear all
              </button>
            )}
          </div>
        )}
      </div>

      {/* Memory Timeline */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Showing {filteredMemories.length} of {allMemories.length} entries
          </p>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Filter className="h-3 w-3" />
            Sorted by relevance
          </div>
        </div>

        <MemoryTimeline entries={filteredMemories} />
      </div>
    </div>
  );
}
