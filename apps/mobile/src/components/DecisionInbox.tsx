import { useEffect } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView } from "react-native";
import { useEventStore } from "../state/eventsStore";
import { respondToDecision } from "../services/decisions";

export default function DecisionInbox() {
  const events = useEventStore((s: any) => s.events);
  const remove = useEventStore((s: any) => s.remove);

  const pending = events.filter((e: any) => e.type === "decision_required");

  if (!pending.length) return null;

  return (
    <View style={styles.container}>
      <ScrollView>
        {pending.map((e: any) => (
          <View key={e.id} style={styles.card}>
            <Text style={styles.title}>{e.title}</Text>
            <Text style={styles.message}>{e.message}</Text>

            <View style={styles.actions}>
              {e.actions?.map((a: any) => (
                <Pressable
                  key={a.id}
                  style={styles.button}
                  onPress={async () => {
                    await respondToDecision(e.id, a.id);
                    remove(e.id);
                  }}
                >
                  <Text style={styles.buttonText}>{a.label}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    bottom: 24,
    right: 16,
    left: 16,
    zIndex: 50,
  },
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 6,
    elevation: 4,
  },
  title: { fontSize: 16, fontWeight: "700", marginBottom: 4 },
  message: { color: "#555", marginBottom: 12 },
  actions: { flexDirection: "row", gap: 8 },
  button: {
    backgroundColor: "#000",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  buttonText: { color: "#fff", fontWeight: "600" },
});
