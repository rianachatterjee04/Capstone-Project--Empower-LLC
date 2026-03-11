import { View, Text, Pressable, StyleSheet } from "react-native";
import { respondToDecision } from "../services/decisions";

interface Action {
  id: string;
  label: string;
}

interface DecisionEvent {
  id: string;
  title: string;
  message: string;
  actions: Action[];
}

export default function DecisionCard({ event }: { event: any }) {
  // unwrap bus format: { event: "decision", data: {...} }
  const d: DecisionEvent = event?.data ?? event;
  const actions: Action[] = d?.actions ?? [];

  async function respond(action: string) {
    await respondToDecision(d.id, action);
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>{d?.title}</Text>
      <Text style={styles.message}>{d?.message}</Text>
      <View style={styles.actions}>
        {actions.map(a => (
          <Pressable key={a.id} style={styles.button} onPress={() => respond(a.id)}>
            <Text style={styles.buttonText}>{a.label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#fff", borderRadius: 12, padding: 16, boxShadow: "0 2px 5px rgba(0,0,0,0.12)" },
  title: { fontSize: 16, fontWeight: "700", marginBottom: 4 },
  message: { color: "#555", marginBottom: 12 },
  actions: { flexDirection: "row", gap: 8 },
  button: { backgroundColor: "#000", paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  buttonText: { color: "#fff", fontWeight: "600" },
});
