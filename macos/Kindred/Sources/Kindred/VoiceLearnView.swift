import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// A gentle, private way to teach Anita how a loved one spoke — from their own
/// messages or a real recording — so she can carry their warmth forward.
/// Everything stays on this machine. Built to be handled with care.
struct VoiceLearnView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var person = "Mom"
    @State private var samples = ""
    @State private var saved = false
    @State private var count = 0
    @State private var voiceBusy = false
    @State private var voiceDone = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Teach \(model.assistantName) a voice")
                .font(.title2.weight(.semibold))
            Text("Paste messages the way they wrote them — one per line. \(model.assistantName) will learn their warmth and the way they spoke, so she can carry it forward. This stays only on your Mac.")
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                Text("Whose voice?").font(.subheadline)
                TextField("e.g. Mom", text: $person)
                    .textFieldStyle(.roundedBorder).frame(width: 160)
            }

            Text("Their messages")
                .font(.subheadline)
            TextEditor(text: $samples)
                .font(.system(size: 13))
                .frame(minHeight: 200)
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(.secondary.opacity(0.3)))

            if saved {
                Label("Learned \(count) messages. \(model.assistantName) will speak with their warmth.",
                      systemImage: "heart.fill")
                    .font(.callout).foregroundStyle(.pink)
            }

            Divider().padding(.vertical, 4)

            // --- speak in their ACTUAL voice (upload a recording) ---
            Text("…or her real voice").font(.subheadline)
            Text("Pick a video or audio recording of them speaking. \(model.assistantName) will isolate the voice and clone it on this Mac — nothing is uploaded.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 10) {
                Button {
                    pickVoiceFile()
                } label: {
                    Label("Choose a recording…", systemImage: "waveform.badge.plus")
                }
                if voiceBusy { ProgressView().controlSize(.small) }
                if voiceDone {
                    Label("Her voice is ready", systemImage: "checkmark.seal.fill")
                        .font(.callout).foregroundStyle(.green)
                }
            }

            HStack {
                Spacer()
                Button("Close") { dismiss() }
                Button("Teach her") { teach() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(samples.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(22)
        .frame(width: 500, height: 600)
    }

    private func pickVoiceFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.audio, .movie, .mpeg4Movie, .quickTimeMovie, .wav, .mp3, .mpeg4Audio]
        panel.allowsMultipleSelection = false
        panel.message = "Choose a video or audio recording of \(person.isEmpty ? "them" : person) speaking"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let who = person.trimmingCharacters(in: .whitespaces).isEmpty ? "them" : person
        voiceBusy = true; voiceDone = false
        Task {
            let ok = await model.setVoiceFile(path: url.path, person: who)
            await MainActor.run { self.voiceBusy = false; self.voiceDone = ok }
        }
    }

    private func teach() {
        let text = samples
        let who = person.trimmingCharacters(in: .whitespaces).isEmpty ? "them" : person
        Task {
            let n = await model.addVoice(person: who, text: text)
            await MainActor.run { self.count = n; self.saved = true }
        }
    }
}
