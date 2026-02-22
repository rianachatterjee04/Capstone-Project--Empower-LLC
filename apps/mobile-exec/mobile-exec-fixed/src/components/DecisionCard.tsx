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

export default function DecisionCard({ event }: { event: DecisionEvent }) {
  async function respond(action: string) {
    await respondToDecision(event.id, action);
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>{event.title}</Text>
      <Text style={styles.message}>{event.message}</Text>
      <View style={styles.actions}>
        {event.actions.map(a => (
          <Pressable key={a.id} style={styles.button} onPress={() => respond(a.id)}>
            <Text style={styles.buttonText}>{a.label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 16,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.12,
    shadowRadius: 5,
    elevation: 3,
  },
  title: { fontSize: 16, fontWeight: "700", marginBottom: 4 },
  message: { color: "#555", marginBottom: 12 },
  actions: { flexDirection: "row", gap: 8 },
  button: { backgroundColor: "#000", paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  buttonText: { color: "#fff", fontWeight: "600" },
});
