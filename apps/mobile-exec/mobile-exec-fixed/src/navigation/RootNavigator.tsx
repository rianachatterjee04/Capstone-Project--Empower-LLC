import { useState } from "react";
import { View, Text, Pressable, ScrollView, StyleSheet } from "react-native";
import { useEventStore } from "../state/eventsStore";
import { useRealtime } from "../hooks/useRealtime";
import DecisionCard from "../components/DecisionCard";

function DashboardScreen() {
  const events = useEventStore((s: any) => s.events);
  useRealtime();

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>Foundry Executive</Text>
      <Text style={styles.sub}>Live decisions from the behavioral OS</Text>

      {events.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>No decisions yet — they'll appear here in real time.</Text>
        </View>
      ) : (
        <View style={styles.list}>
          {events.map((e: any) => (
            <DecisionCard key={e.id} event={e} />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

type Screen = "dashboard";

export default function RootNavigator() {
  const [screen] = useState<Screen>("dashboard");

  return (
    <View style={styles.root}>
      <View style={styles.navbar}>
        <Text style={styles.navTitle}>Foundry People</Text>
      </View>
      <View style={styles.body}>
        {screen === "dashboard" && <DashboardScreen />}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#fff" },
  navbar: {
    height: 56,
    backgroundColor: "#000",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  navTitle: { color: "#fff", fontSize: 17, fontWeight: "700" },
  body: { flex: 1 },
  screen: { flex: 1 },
  content: { padding: 16, gap: 12 },
  heading: { fontSize: 24, fontWeight: "700", marginBottom: 4 },
  sub: { fontSize: 14, color: "#666", marginBottom: 16 },
  empty: {
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 12,
    padding: 20,
    alignItems: "center",
  },
  emptyText: { color: "#999", fontSize: 14, textAlign: "center" },
  list: { gap: 12 },
});