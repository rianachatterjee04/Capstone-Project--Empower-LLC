import "./globals.css";
import { Providers } from "@/components/Providers";
import RealtimeBootstrap from "@/components/RealtimeBootstrap";
import DecisionInbox from "@/components/DecisionInbox";

export const metadata = {
  title: "Foundry People",
  description: "AI-native enterprise HR operating system",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>
          {/* 🔴 Connects browser to org brain */}
          <RealtimeBootstrap />

          {/* 🔴 Global approval / alert UI */}
          <DecisionInbox />

          {/* Application */}
          {children}
        </Providers>
      </body>
    </html>
  );
}
