import Foundation

// Mirrors the bundle emitted by Scripts/scrape.py.

struct Bundle: Decodable {
    let generatedAt: String
    let drawGames: [DrawGame]
    let states: [String: StateData]
}

struct DrawGame: Decodable, Identifiable {
    let id: String
    let name: String
    let specialLabel: String?
    let draws: [Draw]

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

struct StateData: Decodable {
    let name: String
    let scratchers: [Scratcher]
    let payouts: [String: Payout]?
    /// In-state games like Pick 3 and Pick 4.
    let drawGames: [DrawGame]?
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

struct Scratcher: Decodable, Identifiable {
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
    /// How the print run was obtained: "published", "tier-odds", "overall-odds",
    /// or nil when the state publishes no odds at all.
    let printRunSource: String?

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
