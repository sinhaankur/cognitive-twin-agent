import SwiftUI

/// A gentle, private way to teach Anita how a loved one spoke — from their own
/// messages — so she can carry their warmth forward. Everything stays on this
/// machine. Built to be handled with care.
struct VoiceLearnView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var person = "Mom"
    @State private var samples = ""
    @State private var saved = false
    @State private var count = 0

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

            HStack {
                Spacer()
                Button("Close") { dismiss() }
                Button("Teach her") { teach() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(samples.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(22)
        .frame(width: 480, height: 480)
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
