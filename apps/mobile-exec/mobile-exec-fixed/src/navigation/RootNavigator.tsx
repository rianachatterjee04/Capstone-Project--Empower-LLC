import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { View, Text } from "react-native";

function DashboardScreen() {
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
      <Text style={{ fontSize: 18 }}>Foundry Executive</Text>
    </View>
  );
}

const Stack = createNativeStackNavigator();

export default function RootNavigator() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="Dashboard" component={DashboardScreen} options={{ title: "Foundry Executive" }} />
    </Stack.Navigator>
  );
}
