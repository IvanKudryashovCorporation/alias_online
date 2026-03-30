import "package:flutter/material.dart";
import "src/screens/home_screen.dart";

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AliasOnlineApp());
}

class AliasOnlineApp extends StatelessWidget {
  const AliasOnlineApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: "Alias Online",
      theme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF3A7BFF)),
        scaffoldBackgroundColor: const Color(0xFF0A1727),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
