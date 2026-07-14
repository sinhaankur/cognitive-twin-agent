import Photos

/// Her window into your Photos — strictly behind the "Read my Photos" switch.
/// Nothing runs until the user flips it ON (and macOS asks its own permission
/// on top). Even then she reads METADATA ONLY: album titles and dates — never
/// pixels, never people, nothing uploaded, nothing copied. From those she
/// learns life events — birthdays, anniversaries, weddings, remembrances,
/// family gatherings — plus unnamed annual spikes worth asking about (a day
/// that fills with photos every year is usually somebody's birthday).
/// The derived events go to the local server, which stores them as ordinary
/// memories (dedup-safe, source "photos").
enum PhotosReader {

    /// keyword → the kind of life event an album title names
    private static let kinds: [(String, [String])] = [
        ("birthday",     ["birthday", "bday", "b-day", "turns ", "cake smash"]),
        ("anniversary",  ["anniversary", "anniv"]),
        ("wedding",      ["wedding", "engagement", "shaadi", "marriage"]),
        ("remembrance",  ["memorial", "funeral", "in memory", "in loving memory", "rip ", "remembrance"]),
        ("family event", ["family", "reunion", "baby shower", "graduation", "newborn",
                          "christening", "baptism", "diwali", "christmas", "thanksgiving", "eid", "holi"]),
        ("trip",         ["trip", "vacation", "honeymoon", "holiday "]),
    ]

    static func scanAndSend(completion: @escaping (String) -> Void) {
        PHPhotoLibrary.requestAuthorization(for: .readWrite) { status in
            guard status == .authorized || status == .limited else {
                completion("Photos access not allowed"); return
            }
            DispatchQueue.global(qos: .utility).async {
                let (events, scanned) = scan()
                post(["events": events, "scanned": scanned])
                completion("read \(events.count) life events from \(scanned) photos' metadata")
            }
        }
    }

    private static func classify(_ title: String) -> String? {
        let t = title.lowercased()
        for (kind, words) in kinds where words.contains(where: { t.contains($0) }) {
            return kind
        }
        return nil
    }

    private static func scan() -> ([[String: Any]], Int) {
        var events: [[String: Any]] = []
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"

        // 1. named albums whose titles name a life event
        let albums = PHAssetCollection.fetchAssetCollections(
            with: .album, subtype: .albumRegular, options: nil)
        albums.enumerateObjects { album, _, _ in
            guard let title = album.localizedTitle, let kind = classify(title) else { return }
            let opts = PHFetchOptions()
            opts.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
            let assets = PHAsset.fetchAssets(in: album, options: opts)
            guard assets.count > 0 else { return }
            var ev: [String: Any] = ["kind": kind, "title": title, "count": assets.count]
            if let d = assets.firstObject?.creationDate { ev["date"] = fmt.string(from: d) }
            if let d = assets.lastObject?.creationDate { ev["until"] = fmt.string(from: d) }
            events.append(ev)
        }

        // 2. unnamed annual spikes: a day that fills with photos year after year
        var byDay: [Int: [Int: Int]] = [:]     // month*100+day → year → photos
        var scanned = 0
        let all = PHAsset.fetchAssets(with: .image, options: nil)
        scanned = all.count
        let cal = Calendar.current
        all.enumerateObjects { asset, _, _ in
            guard let d = asset.creationDate else { return }
            let c = cal.dateComponents([.year, .month, .day], from: d)
            guard let y = c.year, let m = c.month, let day = c.day else { return }
            byDay[m * 100 + day, default: [:]][y, default: 0] += 1
        }
        let annual = byDay.compactMap { entry -> (Int, [Int], Int)? in
            let busy = entry.value.filter { $0.value >= 6 }
            guard busy.count >= 2 else { return nil }
            return (entry.key, busy.keys.sorted(), busy.values.reduce(0, +))
        }
        .sorted { $0.2 > $1.2 }
        .prefix(8)
        for (key, years, total) in annual {
            events.append(["kind": "annual", "monthday": String(format: "%02d-%02d", key / 100, key % 100),
                           "years": years, "count": total])
        }
        return (events, scanned)
    }

    private static func post(_ body: [String: Any]) {
        guard let url = URL(string: "http://127.0.0.1:7878/api/photos/events"),
              let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        URLSession.shared.dataTask(with: req).resume()
    }
}
