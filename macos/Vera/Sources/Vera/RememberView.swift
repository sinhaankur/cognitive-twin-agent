import SwiftUI
import AppKit

/// "Remember them…" — the gentle, in-app way to tell Vera who your person was.
///
/// This is the bond-building ritual, carried out of the terminal and into the app
/// where a grieving person can actually find it. One soft question at a time:
/// the people they loved, where their life happened, the things they always said,
/// the small loves, a memory or two. Each answer is saved to the sealed life story
/// on this Mac the instant it's entered — so a session can stop anywhere and
/// nothing is ever lost, and it can be done a little at a time over many sittings.
///
/// The questions + tone are the same as the CLI interview (remember.py); only the
/// delivery is warm and visual now. Everything stays on this machine.
struct RememberView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss

    // One flowing step at a time. The sayings step is the one that makes it feel
    // like them, so it gets the gentlest framing.
    private enum Step: Int, CaseIterable {
        case intro, people, places, sayings, loves, stories, done
    }
    @State private var step: Step = .intro

    // the current answer field(s)
    @State private var field = ""
    @State private var personRelation = ""
    @State private var personNote = ""
    @State private var storyText = ""
    @State private var storyWhen = ""

    @State private var tally = ""          // "2 sayings, 1 memory so far"
    @State private var saving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header

            switch step {
            case .intro:   intro
            case .people:  question(
                "Who was one of the people who mattered most to them?",
                hint: "A name — you can add more, one at a time.",
                extra: {
                    AnyView(VStack(alignment: .leading, spacing: 8) {
                        labeled("Who were they to them?", "son, husband, dearest friend…", $personRelation)
                        labeled("In a line — who were they, really?", "", $personNote)
                    })
                })
            case .places:  question(
                "A place that was theirs —",
                hint: "where they grew up, a home, somewhere they loved.")
            case .sayings: question(
                "Something they always said —",
                hint: "a phrase, a bit of advice, the way they'd greet you. This is the one that makes it feel like them.",
                tender: true)
            case .loves:   question(
                "A small joy that was specifically theirs —",
                hint: "a food they made, a song they loved, a little ritual.")
            case .stories: question(
                "A memory you don't want to lose —",
                hint: "give it a name, then tell it however it comes to you.",
                extra: {
                    AnyView(VStack(alignment: .leading, spacing: 8) {
                        multiline("Tell it —", $storyText)
                        labeled("Roughly when?", "a year, 'when I was small'…", $storyWhen)
                    })
                })
            case .done:    doneView
            }

            Spacer(minLength: 0)
            footer
        }
        .padding(22)
        .frame(width: 520, height: 560)
        .onAppear { refreshTally() }
    }

    // MARK: sections

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Remember them")
                .font(.title2.weight(.semibold))
            if !tally.isEmpty {
                Text(tally).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Let's remember them, a little at a time.")
                .font(.title3)
            Text("There's no rush and no wrong answer — skip anything, stop whenever. A few memories today, a few more another day. Over time, this is what turns \(model.assistantName) into *them* — their words, the way they spoke.")
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Label("Everything you say stays on this Mac, sealed. It never leaves.",
                  systemImage: "lock.fill")
                .font(.caption).foregroundStyle(.green)
        }
    }

    /// One soft question. `tender` gives the sayings step a warmer tint; `extra`
    /// adds the person/story sub-fields.
    private func question(_ title: String, hint: String,
                          tender: Bool = false,
                          extra: (() -> AnyView)? = nil) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.title3.weight(.medium))
                .foregroundStyle(tender ? Color(red: 0.86, green: 0.68, blue: 0.38) : .primary)
            Text(hint)
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if step == .stories {
                labeled("What would you call this memory?", "(a title)", $field)
            } else {
                TextField("", text: $field, prompt: Text("…"))
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 15))
                    .onSubmit { saveAndStay() }
            }
            if let extra { extra() }
        }
    }

    private var doneView: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Thank you for that.", systemImage: "heart.fill")
                .font(.title3).foregroundStyle(.pink)
            Text(tally.isEmpty ? "You can come back any time and add more." :
                    "\(tally)\n\nYou can come back any time and add more — just open Remember them, or simply tell \(model.assistantName) about them while you talk.")
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: footer / actions

    private var footer: some View {
        HStack {
            if step != .intro && step != .done {
                Button("Skip this") { nextStep() }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
            }
            Spacer()
            if saving { ProgressView().controlSize(.small) }
            Button(step == .done ? "Close" : "I'll come back later") { dismiss() }
            if step == .intro {
                Button("Begin") { step = .people }.keyboardShortcut(.defaultAction)
            } else if step == .done {
                EmptyView()
            } else {
                Button(hasAnswer ? "Save & next" : "Next") {
                    if hasAnswer { saveAndNext() } else { nextStep() }
                }
                .keyboardShortcut(.defaultAction)
            }
        }
    }

    private var hasAnswer: Bool {
        switch step {
        case .stories: return !storyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        default:       return !field.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
    }

    /// Save the current answer and advance to the next section.
    private func saveAndNext() { save { nextStep() } }

    /// Save and STAY on the same section (adding several sayings/people in a row).
    private func saveAndStay() {
        guard hasAnswer else { return }
        save { clearFields() }
    }

    private func save(_ then: @escaping () -> Void) {
        let payload = currentPayload()
        guard !payload.isEmpty else { then(); return }
        saving = true
        Task {
            let newTally = await model.addLifeStory(payload)
            await MainActor.run {
                saving = false
                if let t = newTally { tally = t }
                then()
            }
        }
    }

    private func currentPayload() -> [String: String] {
        let t = field.trimmingCharacters(in: .whitespaces)
        switch step {
        case .people where !t.isEmpty:
            return ["kind": "person", "name": t,
                    "relation": personRelation.trimmingCharacters(in: .whitespaces),
                    "note": personNote.trimmingCharacters(in: .whitespaces)]
        case .places where !t.isEmpty:  return ["kind": "place", "text": t]
        case .sayings where !t.isEmpty: return ["kind": "saying", "text": t]
        case .loves where !t.isEmpty:   return ["kind": "love", "text": t]
        case .stories:
            let body = storyText.trimmingCharacters(in: .whitespaces)
            guard !body.isEmpty else { return [:] }
            return ["kind": "story", "title": t, "text": body,
                    "when": storyWhen.trimmingCharacters(in: .whitespaces)]
        default: return [:]
        }
    }

    private func nextStep() {
        clearFields()
        if let next = Step(rawValue: step.rawValue + 1) { step = next }
    }

    private func clearFields() {
        field = ""; personRelation = ""; personNote = ""; storyText = ""; storyWhen = ""
    }

    private func refreshTally() {
        Task {
            let t = await model.lifeStoryStatus()
            await MainActor.run { if let t { tally = t } }
        }
    }

    // MARK: small builders

    private func labeled(_ label: String, _ placeholder: String, _ binding: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            TextField("", text: binding, prompt: Text(placeholder))
                .textFieldStyle(.roundedBorder)
        }
    }

    private func multiline(_ label: String, _ binding: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            TextEditor(text: binding)
                .font(.system(size: 13)).frame(minHeight: 70)
                .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(.secondary.opacity(0.3)))
        }
    }
}
