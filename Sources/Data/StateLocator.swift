import Foundation
import CoreLocation
import Combine

/// One-shot "which state am I in?" lookup.
///
/// The app never stores or transmits coordinates; it reverse-geocodes once,
/// keeps the two-letter state code, and stops updating.
final class StateLocator: NSObject, ObservableObject {
    enum Status: Equatable {
        case idle
        case locating
        case found(String)
        case denied
        case failed(String)
    }

    @Published private(set) var status: Status = .idle

    private let manager = CLLocationManager()
    private let geocoder = CLGeocoder()
    private var onResolve: ((String) -> Void)?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    func detect(onResolve: @escaping (String) -> Void) {
        self.onResolve = onResolve
        status = .locating

        switch manager.authorizationStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .denied, .restricted:
            status = .denied
        default:
            manager.requestLocation()
        }
    }
}

extension StateLocator: CLLocationManagerDelegate {
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways:
            if status == .locating { manager.requestLocation() }
        case .denied, .restricted:
            status = .denied
        default:
            break
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        geocoder.reverseGeocodeLocation(location) { [weak self] places, error in
            guard let self else { return }
            if let error {
                self.status = .failed(error.localizedDescription)
                return
            }
            guard let code = places?.first?.administrativeArea else {
                self.status = .failed("Couldn't identify a state.")
                return
            }
            self.status = .found(code)
            self.onResolve?(code)
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        status = .failed(error.localizedDescription)
    }
}
