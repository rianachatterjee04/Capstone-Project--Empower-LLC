import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { View, Text } from "react-native";

// Placeholder home screen — replace with your real screens
function HomeScreen() {
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
      <Text style={{ fontSize: 18 }}>Foundry People</Text>
    </View>
  );
}

const Stack = createNativeStackNavigator();

export default function RootNavigator() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="Home" component={HomeScreen} options={{ title: "Foundry People" }} />
    </Stack.Navigator>
  );
}
