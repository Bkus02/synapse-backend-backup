import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/recommendation.dart';
import 'recommendation_api.dart';
import 'session_service.dart';

/// Sprint E — tek kaynak: pending öneriyi periyodik ve olay sonrası yeniler.
class RecommendationRefreshService extends ChangeNotifier {
  RecommendationRefreshService._();
  static final RecommendationRefreshService instance =
      RecommendationRefreshService._();

  static const steadyInterval = Duration(seconds: 30);
  static const burstInterval = Duration(seconds: 3);
  static const burstWindow = Duration(seconds: 90);

  Recommendation? _active;
  bool _loading = false;
  Timer? _steadyTimer;
  Timer? _burstTimer;
  DateTime? _burstUntil;
  bool _inFlight = false;
  bool _attached = false;

  Recommendation? get active => _active;
  bool get loading => _loading;
  bool get hasActive => _active != null;

  void attach() {
    if (_attached) return;
    _attached = true;
    SessionService.instance.addListener(_onSessionChanged);
    _onSessionChanged();
  }

  void _onSessionChanged() {
    if (SessionService.instance.hasToken) {
      start();
    } else {
      stop();
    }
  }

  void start() {
    _steadyTimer?.cancel();
    _steadyTimer = Timer.periodic(steadyInterval, (_) => unawaited(_poll()));
    unawaited(_poll());
  }

  void stop() {
    _steadyTimer?.cancel();
    _steadyTimer = null;
    _burstTimer?.cancel();
    _burstTimer = null;
    _burstUntil = null;
    _active = null;
    _loading = false;
    _inFlight = false;
    notifyListeners();
  }

  /// Inference / device toggle / behavior log sonrası kısa aralıklı yenileme.
  void requestImmediateRefresh() {
    if (!SessionService.instance.hasToken) return;
    _burstUntil = DateTime.now().add(burstWindow);
    _ensureBurstTimer();
    unawaited(_poll());
  }

  void invalidateAndRefresh() {
    _active = null;
    notifyListeners();
    requestImmediateRefresh();
  }

  void _ensureBurstTimer() {
    _burstTimer ??= Timer.periodic(burstInterval, (_) {
      final until = _burstUntil;
      if (until == null || DateTime.now().isAfter(until)) {
        _burstTimer?.cancel();
        _burstTimer = null;
        _burstUntil = null;
        return;
      }
      unawaited(_poll());
    });
  }

  Future<void> _poll() async {
    if (!SessionService.instance.hasToken) {
      stop();
      return;
    }
    if (_inFlight) return;
    _inFlight = true;
    final wasLoading = _loading;
    if (!wasLoading) {
      _loading = true;
      notifyListeners();
    }
    try {
      final rec = await RecommendationApi.getActive();
      final changed = rec?.id != _active?.id;
      _active = rec;
      if (changed) notifyListeners();
    } catch (_) {
      // Son bilinen öneriyi koru; ağ hatalarında UI sessiz kalır.
    } finally {
      _inFlight = false;
      if (_loading) {
        _loading = false;
        notifyListeners();
      }
    }
  }
}
