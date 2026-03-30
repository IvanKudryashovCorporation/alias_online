class AppConfig {
  static const String roomServerUrl = String.fromEnvironment(
    "ALIAS_ROOM_SERVER_URL",
    defaultValue: "",
  );
}
