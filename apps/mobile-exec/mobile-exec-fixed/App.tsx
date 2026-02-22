import { NavigationContainer } from "@react-navigation/native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import RealtimeBootstrap from "./src/realtime/RealtimeBootstrap";
import RootNavigator from "./src/navigation/RootNavigator";

export default function App() {
  return (
    <SafeAreaProvider>
      <NavigationContainer>

        {/* 🧠 Connect to Foundry behavioral OS */}
        <RealtimeBootstrap />

        {/* Your existing screens */}
        <RootNavigator />

      </NavigationContainer>
    </SafeAreaProvider>
  );
}

