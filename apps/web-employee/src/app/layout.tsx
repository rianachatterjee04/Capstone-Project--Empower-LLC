import "./globals.css";
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
        {/* 🔴 Connects browser to org brain */}
        <RealtimeBootstrap />

        {/* 🔴 Global approval / alert UI */}
        <DecisionInbox />

        {/* Existing application */}
        {children}
      </body>
    </html>
  );
}

