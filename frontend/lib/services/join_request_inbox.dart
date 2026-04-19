import '../models/environment_summary.dart';
import '../models/join_request.dart';
import 'environment_api.dart';
import 'session_service.dart';

class JoinRequestInboxItem {
  const JoinRequestInboxItem({
    required this.request,
    required this.environment,
  });

  final JoinRequest request;
  final EnvironmentSummary environment;
}

/// Loads pending join requests for environments where the current user is admin.
/// Used by the in-app notifications sheet (no push yet).
class JoinRequestInbox {
  JoinRequestInbox._();

  static Future<List<JoinRequestInboxItem>> loadPendingForAdmin() async {
    final uid = SessionService.instance.user?['id'] as String?;
    if (uid == null) return [];
    final envs = await EnvironmentApi.listForUser(uid);
    final adminEnvs = envs.where((e) => e.adminId == uid).toList();
    final out = <JoinRequestInboxItem>[];
    for (final env in adminEnvs) {
      final reqs = await EnvironmentApi.listJoinRequests(
        environmentId: env.id,
        adminUserId: uid,
      );
      for (final r in reqs) {
        out.add(JoinRequestInboxItem(request: r, environment: env));
      }
    }
    out.sort((a, b) => b.request.id.compareTo(a.request.id));
    return out;
  }

  static Future<int> pendingCountForAdmin() async {
    final list = await loadPendingForAdmin();
    return list.length;
  }
}
