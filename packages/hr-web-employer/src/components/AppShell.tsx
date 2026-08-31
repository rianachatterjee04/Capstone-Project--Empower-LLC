"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { CommandPalette } from "./CommandPalette";
import { AssistantDock } from "./AssistantDock";
import { InboxDrawer } from "./InboxDrawer";
import { ShellStateProvider } from "./ShellState";
import { isSignedIn } from "@/lib/session";

/**
 * Foundry People AppShell.
 *
 * Layout grid:
 *   [primary rail · secondary nav][main column]
 *
 * The main column has a sticky topbar (search + assistant + inbox) and the
 * page content beneath. Overlays — command palette, assistant dock, inbox
 * drawer — are mounted once at this level.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  // Gate the workspace: unauthenticated visitors are sent to the sign-in page.
  useEffect(() => {
    if (!isSignedIn()) {
      router.replace("/");
    } else {
      setReady(true);
    }
  }, [router]);

  if (!ready) return null;

  return (
    <ShellStateProvider>
      <div className="min-h-screen bg-canvas text-ink flex">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Topbar />
          <main className="flex-1 px-4 sm:px-6 lg:px-8 py-5 lg:py-7 max-w-[1400px] w-full mx-auto">{children}</main>
        </div>

        {/* Overlays */}
        <CommandPalette />
        <AssistantDock />
        <InboxDrawer />
      </div>
    </ShellStateProvider>
  );
}
