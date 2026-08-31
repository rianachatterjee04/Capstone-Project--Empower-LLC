"use client";

import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { AssistantDock } from "./AssistantDock";
import { ShellStateProvider } from "./ShellState";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ShellStateProvider>
      <div className="min-h-screen bg-canvas text-ink flex">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Topbar />
          <main className="flex-1 px-8 py-7 max-w-[1200px] w-full mx-auto">{children}</main>
        </div>
        <AssistantDock />
      </div>
    </ShellStateProvider>
  );
}
