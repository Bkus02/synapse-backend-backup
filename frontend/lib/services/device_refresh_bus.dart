/// Ortam cihaz listesini yeniden yüklemek için hafif pub/sub (sekme değişimi vb.).
class DeviceRefreshBus {
  DeviceRefreshBus._();
  static final DeviceRefreshBus instance = DeviceRefreshBus._();

  final List<void Function()> _listeners = [];

  void subscribe(void Function() listener) {
    if (!_listeners.contains(listener)) {
      _listeners.add(listener);
    }
  }

  void unsubscribe(void Function() listener) {
    _listeners.remove(listener);
  }

  void notify() {
    for (final listener in List<void Function()>.from(_listeners)) {
      listener();
    }
  }
}
