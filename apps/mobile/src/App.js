import React, { useState } from "react";
import { SafeAreaView, Text, TextInput, Pressable, View, ScrollView } from "react-native";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL || "";
const supabaseAnon = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || "";
const apiBase = process.env.EXPO_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

const supabase = createClient(supabaseUrl, supabaseAnon);

export default function App() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("");
  const [token, setToken] = useState("");

  async function sendMagic() {
    const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: "foundrypeople://login" } });
    setStatus(error ? error.message : "Check your email for the login link.");
  }

  async function getSession() {
    const { data } = await supabase.auth.getSession();
    const t = data.session?.access_token || "";
    setToken(t);
    setStatus(t ? "Session loaded." : "No session.");
  }

  async function ping() {
    if (!token) return setStatus("No token yet.");
    const res = await fetch(apiBase + "/health", { headers: { Authorization: "Bearer " + token } });
    const js = await res.json();
    setStatus(JSON.stringify(js));
  }

  return (
    <SafeAreaView style={{ flex: 1, padding: 16 }}>
      <ScrollView>
        <Text style={{ fontSize: 22, fontWeight: "600" }}>Foundry People Mobile</Text>
        <Text style={{ marginTop: 8, opacity: 0.7 }}>Scaffold: auth + API wiring</Text>

        <View style={{ marginTop: 16 }}>
          <Text>Email</Text>
          <TextInput value={email} onChangeText={setEmail} placeholder="you@company.com" style={{ borderWidth: 1, padding: 10, borderRadius: 12, marginTop: 6 }} />
          <Pressable onPress={sendMagic} style={{ marginTop: 10, backgroundColor: "black", padding: 12, borderRadius: 12 }}>
            <Text style={{ color: "white", textAlign: "center" }}>Send magic link</Text>
          </Pressable>
          <Pressable onPress={getSession} style={{ marginTop: 10, borderWidth: 1, padding: 12, borderRadius: 12 }}>
            <Text style={{ textAlign: "center" }}>Load session</Text>
          </Pressable>
          <Pressable onPress={ping} style={{ marginTop: 10, borderWidth: 1, padding: 12, borderRadius: 12 }}>
            <Text style={{ textAlign: "center" }}>Ping backend</Text>
          </Pressable>
          <Text style={{ marginTop: 12 }}>{status}</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
