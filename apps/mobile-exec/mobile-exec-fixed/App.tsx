import { SafeAreaProvider } from "react-native-safe-area-context";
import RealtimeBootstrap from "./src/realtime/RealtimeBootstrap";
import RootNavigator from "./src/navigation/RootNavigator";

export default function App() {
  return (
    <SafeAreaProvider>
      <RealtimeBootstrap />
      <RootNavigator />
    </SafeAreaProvider>
  );
}