import SwiftUI

/// HomeSetup — teach Vera where home is, so she knows when you come and go.
///
/// The simplest, truest signal for a laptop you carry is your home Wi-Fi: one tap
/// sets whatever network you're on right now as "home". From then on she greets you
/// when you're back on it and goes quiet when you're away. Everything stays sealed
/// on-device; nothing about where you are is ever uploaded.
@MainActor
final class HomeSetup: ObservableObject {
    enum Phase: Equatable { case idle, saving, done(String), failed(String) }
    @Published var phase: Phase = .idle
    @Published var status: String = ""
    @Published var configured = false
    @Published var home: Bool? = nil

    private let client: AgentClient
    init(client: AgentClient = AgentClient()) { self.client = client }

    func refresh() {
        Task {
            let s = await client.homeState()
            await MainActor.run {
                self.configured = s.configured
                self.home = s.home
                self.status = s.status
            }
        }
    }

    func useThisWifi() {
        phase = .saving
        Task {
            let detail = await client.setHome(useCurrentWifi: true)
            let ok = !detail.lowercased().contains("couldn't")
            await MainActor.run {
                self.phase = ok ? .done(detail) : .failed(detail)
                self.refresh()
            }
        }
    }
}

struct HomeSetupView: View {
    @StateObject private var s = HomeSetup()

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "house.fill")
                .font(.system(size: 26))
                .foregroundStyle(Color.accentColor)

            Text("Know when I'm home")
                .font(.system(size: 18, weight: .semibold))

            Text("So I can welcome you home and stay quiet while you're out. "
                 + "The easiest way is your home Wi-Fi — set the network you're on "
                 + "right now, and I'll know you by it.")
                .font(.system(size: 12.5))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)

            // where things stand
            if s.configured {
                Label(whereLine, systemImage: s.home == true ? "house.fill" : "figure.walk")
                    .font(.system(size: 12))
                    .foregroundStyle(s.home == true ? Color.accentColor : .secondary)
            }

            statusLine

            Button { s.useThisWifi() } label: {
                Label(s.configured ? "Add this Wi-Fi as home too" : "Use this Wi-Fi as home",
                      systemImage: "wifi")
                    .frame(width: 240)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(s.phase == .saving)

            Text("Your phone can tell me too — turn it on in the Vera app on iPhone, "
                 + "and I'll know even when this Mac stays home.")
                .font(.system(size: 10.5))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)
        }
        .padding(28)
        .frame(width: 440)
        .onAppear { s.refresh() }
    }

    private var whereLine: String {
        switch s.home {
        case true: return "You're home right now."
        case false: return "You're out right now."
        default: return "Home is set — I'll know next time you come and go."
        }
    }

    @ViewBuilder private var statusLine: some View {
        switch s.phase {
        case .saving:
            Label("Setting home…", systemImage: "house")
                .font(.system(size: 12)).foregroundStyle(.secondary)
        case .done(let m):
            Label(m, systemImage: "checkmark.circle.fill")
                .font(.system(size: 12)).foregroundStyle(Color.accentColor).frame(maxWidth: 360)
        case .failed(let m):
            Label(m, systemImage: "exclamationmark.triangle")
                .font(.system(size: 12)).foregroundStyle(.orange).frame(maxWidth: 360)
        case .idle:
            EmptyView()
        }
    }
}
