import "dart:convert";
import "package:http/http.dart" as http;

class RoomApi {
  const RoomApi({required this.baseUrl});

  final String baseUrl;

  Uri _uri(String path, [Map<String, String>? query]) {
    return Uri.parse("$baseUrl$path").replace(queryParameters: query);
  }

  Future<List<Map<String, dynamic>>> listPublicRooms() async {
    final response = await http.get(_uri("/api/rooms", {"public_only": "1"})).timeout(
          const Duration(seconds: 10),
        );
    if (response.statusCode >= 400) {
      throw Exception("Failed to load rooms (${response.statusCode})");
    }
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return (payload["rooms"] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> joinRoom({
    required String roomCode,
    required String playerName,
  }) async {
    final response = await http
        .post(
          _uri("/api/rooms/$roomCode/join"),
          headers: const {"Content-Type": "application/json"},
          body: jsonEncode({"player_name": playerName}),
        )
        .timeout(const Duration(seconds: 10));
    if (response.statusCode >= 400) {
      throw Exception("Failed to join room (${response.statusCode})");
    }
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return (payload["room"] as Map<String, dynamic>? ?? <String, dynamic>{});
  }
}
