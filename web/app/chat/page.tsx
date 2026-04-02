"use client";

import { useState } from "react";
import { Send, Paperclip, Settings2 } from "lucide-react";
import ChatMessage, { ChatMessageProps } from "@/components/ChatMessage";

const initialMessages: ChatMessageProps[] = [
  {
    role: "user",
    content: "Can you analyze the authentication module and suggest improvements?",
    timestamp: "10:23 AM",
  },
  {
    role: "assistant",
    content:
      "I'll analyze the authentication module for you. Let me start by reading the relevant files and understanding the current implementation.",
    timestamp: "10:23 AM",
    toolCalls: [
      {
        name: "file_read",
        params: { path: "src/auth/middleware.ts" },
        result: "// Authentication middleware\nexport function authMiddleware(req, res, next) {\n  const token = req.headers.authorization;\n  // ... 48 more lines",
        status: "done",
        duration: "0.3s",
      },
      {
        name: "file_read",
        params: { path: "src/auth/jwt.ts" },
        result: "// JWT utilities\nimport jwt from 'jsonwebtoken';\n// ... 62 more lines",
        status: "done",
        duration: "0.2s",
      },
    ],
  },
  {
    role: "assistant",
    content:
      "After analyzing the authentication module, here are my findings:\n\n**Issues Found:**\n1. The JWT secret is hardcoded in `jwt.ts` - this should use environment variables\n2. No token refresh mechanism is implemented\n3. The middleware doesn't handle expired tokens gracefully\n\n**Recommendations:**\n- Move secrets to environment variables using `process.env.JWT_SECRET`\n- Implement a `/auth/refresh` endpoint with rotating refresh tokens\n- Add proper error responses with `401 Unauthorized` for expired tokens\n- Consider adding rate limiting to prevent brute force attacks\n\nWould you like me to implement any of these changes?",
    timestamp: "10:24 AM",
    toolCalls: [
      {
        name: "code_analysis",
        params: { scope: "src/auth/**", checks: ["security", "best-practices"] },
        result: "Found 3 issues: 1 critical (hardcoded secret), 2 warnings (no refresh, poor error handling)",
        status: "done",
        duration: "1.2s",
      },
    ],
  },
  {
    role: "user",
    content: "Yes, please implement the environment variable fix and the token refresh endpoint.",
    timestamp: "10:25 AM",
  },
  {
    role: "assistant",
    content:
      "I'm implementing the changes now. I'll update the JWT configuration to use environment variables and create a new refresh token endpoint.",
    timestamp: "10:25 AM",
    toolCalls: [
      {
        name: "file_write",
        params: { path: "src/auth/jwt.ts", description: "Update JWT to use env vars" },
        result: "File updated successfully",
        status: "done",
        duration: "0.4s",
      },
      {
        name: "file_write",
        params: { path: "src/auth/refresh.ts", description: "Create refresh token endpoint" },
        result: "File created successfully",
        status: "done",
        duration: "0.5s",
      },
      {
        name: "test_run",
        params: { suite: "auth", watch: false },
        status: "running",
        duration: "3.2s",
      },
    ],
  },
];

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessageProps[]>(initialMessages);
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;

    const newMessage: ChatMessageProps = {
      role: "user",
      content: input,
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };

    setMessages((prev) => [...prev, newMessage]);
    setInput("");

    // Simulate assistant response
    setTimeout(() => {
      const response: ChatMessageProps = {
        role: "assistant",
        content:
          "I understand your request. Let me work on that for you. I'll analyze the relevant code and provide a solution.",
        timestamp: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        toolCalls: [
          {
            name: "code_search",
            params: { query: input.slice(0, 50) },
            status: "running",
          },
        ],
      };
      setMessages((prev) => [...prev, response]);
    }, 1000);
  };

  return (
    <div className="flex h-full flex-col">
      {/* Chat Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">
            Agent Chat
          </h1>
          <p className="text-xs text-muted-foreground">
            Interactive conversation with the agentic system
          </p>
        </div>
        <button className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
          <Settings2 className="h-4 w-4" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {messages.map((msg, idx) => (
          <ChatMessage key={idx} {...msg} />
        ))}
      </div>

      {/* Input Bar */}
      <div className="border-t border-border px-6 py-4">
        <div className="flex items-end gap-3">
          <button className="shrink-0 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
            <Paperclip className="h-4 w-4" />
          </button>
          <div className="flex-1">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Send a message to the agent..."
              rows={1}
              className="w-full resize-none rounded-lg border border-border bg-input px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="shrink-0 rounded-lg bg-primary p-3 text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
