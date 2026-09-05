import Foundation

// Mirrors the files emitted by Scripts/split.py.
//
// `core.json` is small and always loaded: every jurisdiction plus the draw
// games sold there. Scratch-off inventories are much larger and only exist for
// some states, so each lives in its own file loaded on demand.

struct Core: Decodable {
    let generatedAt: String?
    let drawGames: [DrawGame]
    let states: [String: StateSummary]
}

struct StateSummary: Decodable {
    let name: String
    let scratcherCount: Int
    /// Best value ratio among this state's games; nil where there are none.
    let bestRatio: Double?
    let payouts: [String: Payout]?
    /// In-state games like Pick 3 and Pick 4.
    let drawGames: [DrawGame]?

    var hasScratchers: Bool { scratcherCount > 0 }
}

struct ScratcherFile: Decodable {
    let generatedAt: String?
    let state: String
    let name: String
    let scratchers: [Scratcher]
}

struct DrawGame: Decodable, Identifiable {
    let id: String
    let name: String
    let specialLabel: String?
    /// Jurisdictions selling this game; nil means everywhere (Powerball,
    /// Mega Millions). Millionaire for Life runs in 31 of the 46.
    let states: [String]?
    let draws: [Draw]

    func sold(in code: String) -> Bool {
        states?.contains(code) ?? true
    }

    /// Same-day games publish more than one draw a day; those are all "latest".
    var latestDraws: [Draw] {
        guard let newest = draws.first?.date else { return [] }
        return draws.filter { $0.date == newest }
    }
}

struct Draw: Decodable {
    let date: String
    let numbers: [Int]
    /// Powerball / Mega Ball / Fireball. Absent for games without one.
    let special: Int?
    let multiplier: String?
    /// Distinguishes same-day draws, e.g. "Daytime" and "Evening".
    let label: String?
}

struct Payout: Decodable {
    let drawDate: String?
    let tiers: [PayoutTier]
}

struct PayoutTier: Decodable, Identifiable {
    let match: String
    let prize: Double?
    let winners: Int

    var id: String { match }
}

struct Scratcher: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let number: String?
    let price: Double?
    let topPrize: Double?
    let overallOdds: Double?
    let tiers: [PrizeTier]
    let url: String?

    let ticketsPrinted: Int?
    let ticketsRemaining: Int?
    let pctPrizesRemaining: Double?
    let evNow: Double?
    let evStart: Double?
    let ratio: Double?
    let returnPct: Double?
    let topPrizesRemaining: Int?
    let endingSoon: Bool?
    /// Expected value minus ticket price. Negative for essentially every
    /// lottery game; the size is what varies.
    let netPerTicket: Double?
    /// "published", "tier-odds", "overall-odds", or nil when no odds exist.
    let printRunSource: String?

    /// Identity is the game number the state assigns, not the whole record:
    /// two reads of the same game differ as its prizes are claimed, and they
    /// are still the same game. Hand-written because the prize tiers are not
    /// Hashable and have no business being dragged into this.
    static func == (lhs: Scratcher, rhs: Scratcher) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }

    /// Plain-English note on how solid this game's numbers are.
    var provenance: String {
        switch printRunSource {
        case "published":
            return "This state publishes its print run, so tickets remaining is "
                + "scaled from a real number rather than an inferred one."
        case "tier-odds":
            return "Tickets printed is inferred from the published odds at each "
                + "prize tier."
        case "overall-odds":
            return "Tickets printed is inferred from the game's overall odds, "
                + "which is coarser than per-tier odds."
        default:
            return "This state publishes prize counts but no odds, so ticket "
                + "counts are unavailable. The value ratio doesn't need them — "
                + "the print run cancels out of it."
        }
    }
}

struct PrizeTier: Decodable, Identifiable {
    let value: Double
    let odds: Double?
    let total: Int
    let remaining: Int

    var id: Double { value }
    var claimed: Int { max(0, total - remaining) }
}

// MARK: - Formatting

enum Fmt {
    /// "5 Sep" from an ISO timestamp, for a line that only needs the day.
    static func dayMonth(_ iso: String?) -> String? {
        guard let iso, let date = ISO8601DateFormatter().date(from: iso) else {
            return nil
        }
        let out = DateFormatter()
        out.dateFormat = "d MMM"
        return out.string(from: date)
    }

    static func money(_ value: Double?, compact: Bool = false) -> String {
        guard let value else { return "—" }
        if compact {
            switch value {
            case 1_000_000_000...:
                return "$\(String(format: "%.2f", value / 1_000_000_000))B"
            case 1_000_000...:
                let millions = value / 1_000_000
                let digits = millions < 10 && millions != millions.rounded() ? 1 : 0
                return "$\(String(format: "%.\(digits)f", millions))M"
            case 1_000...:
                return "$\(Int(value / 1_000))K"
            default:
                break
            }
        }
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.maximumFractionDigits = 0
        return "$" + (f.string(from: NSNumber(value: value)) ?? "\(Int(value))")
    }

    /// Two decimals, for figures where the cents carry the meaning: a net of
    /// "−$1" reads as a rounding artefact, "−$1.23" reads as a number.
    static func cents(_ value: Double?) -> String {
        guard let value else { return "—" }
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.minimumFractionDigits = 2
        f.maximumFractionDigits = 2
        return "$" + (f.string(from: NSNumber(value: value)) ?? String(value))
    }

    static func count(_ value: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        return f.string(from: NSNumber(value: value)) ?? "\(value)"
    }

    /// "2026-08-12" -> "Wed Aug 12"
    static func drawDate(_ iso: String) -> String {
        let parser = DateFormatter()
        parser.dateFormat = "yyyy-MM-dd"
        parser.timeZone = TimeZone(identifier: "UTC")
        guard let date = parser.date(from: iso) else { return iso }
        let out = DateFormatter()
        out.dateFormat = "EEE MMM d"
        out.timeZone = TimeZone(identifier: "UTC")
        return out.string(from: date)
    }
}
