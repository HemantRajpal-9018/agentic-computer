"use client";

import "./globals.css";
import { Inter } from "next/font/google";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  GitBranch,
  Brain,
  Terminal,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/workflows", label: "Workflows", icon: GitBranch },
  { href: "/memory", label: "Memory", icon: Brain },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased`}>
        <div className="flex h-screen overflow-hidden">
          {/* Sidebar */}
          <aside
            className={`flex flex-col border-r border-border bg-card transition-all duration-300 ${
              collapsed ? "w-16" : "w-60"
            }`}
          >
            {/* Logo */}
            <div className="flex h-14 items-center border-b border-border px-4">
              <Terminal className="h-6 w-6 shrink-0 text-primary" />
              {!collapsed && (
                <span className="ml-3 text-sm font-semibold tracking-tight text-foreground">
                  Agentic Computer
                </span>
              )}
            </div>

            {/* Navigation */}
            <nav className="flex-1 space-y-1 px-2 py-4">
              {navItems.map((item) => {
                const isActive = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground"
                    }`}
                    title={collapsed ? item.label : undefined}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!collapsed && <span className="ml-3">{item.label}</span>}
                  </Link>
                );
              })}
            </nav>

            {/* Collapse toggle */}
            <div className="border-t border-border p-2">
              <button
                onClick={() => setCollapsed(!collapsed)}
                className="flex w-full items-center justify-center rounded-md py-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
              >
                {collapsed ? (
                  <ChevronRight className="h-4 w-4" />
                ) : (
                  <ChevronLeft className="h-4 w-4" />
                )}
              </button>
            </div>

            {/* Status indicator */}
            <div className="border-t border-border px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse-dot" />
                {!collapsed && (
                  <span className="text-xs text-muted-foreground">
                    Agent Online
                  </span>
                )}
              </div>
            </div>
          </aside>

          {/* Main content */}
          <main className="flex-1 overflow-y-auto">
            <div className="h-full">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
