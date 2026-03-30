import "package:flutter/material.dart";
import "../config.dart";

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final configured = AppConfig.roomServerUrl.trim().isNotEmpty;
    return Scaffold(
      appBar: AppBar(title: const Text("Alias Online")),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                "Flutter migration lane",
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 12),
              Text(
                configured
                    ? "Room server configured"
                    : "Set ALIAS_ROOM_SERVER_URL in flutter run/build args.",
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 18),
              FilledButton(
                onPressed: () {},
                child: const Text("Create room (next milestone)"),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
