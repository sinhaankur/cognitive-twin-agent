import SwiftUI

/// The Brain — a graph view of how the twin thinks and learns.
///
/// Core faculties (memory, persona, soul, mood, rhythms, activity, voice, model
/// router) sit as CORE nodes; topics the twin has learned from your local usage
/// orbit Memory as LEARNED nodes; observed active hours orbit Rhythms. Edges are
/// coloured by provenance (wired / observed / inferred), in the spirit of
/// graphify's confidence tags. Type a prompt to light up the likely thought-path.
///
/// All data comes from the local agent (`/api/brain`) — nothing leaves the machine.
struct BrainView: View {
    @EnvironmentObject var model: AppModel   // for the AgentClient (adjust if named differently)

    @State private var graph: BrainGraph?
    @State private var positions: [String: CGPoint] = [:]
    @State private var selected: BrainNode?
    @State private var promptText: String = ""
    @State private var pathSet: Set<String> = []
    @State private var loading = true

    private let client = AgentClient()

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.4)
            GeometryReader { geo in
                ZStack {
                    Color(nsColor: .textBackgroundColor).opacity(0.02)
                    if let g = graph {
                        edgesCanvas(g, size: geo.size)
                        ForEach(g.nodes) { node in
                            nodeView(node)
                                .position(positions[node.id] ?? center(geo.size))
                        }
                    } else if loading {
                        ProgressView("Reading the brain…")
                    } else {
                        VStack(spacing: 8) {
                            Text("Couldn't reach the twin.").font(.headline)
                            Text("Start the agent server, then reopen.").foregroundStyle(.secondary)
                        }
                    }
                }
                .onAppear { layout(in: geo.size) }
                .onChange(of: graph?.nodes.count) { _ in layout(in: geo.size) }
            }
            footer
        }
        .frame(minWidth: 720, minHeight: 560)
        .task { await load() }
    }

    // MARK: header / prompt

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text("The Brain").font(.system(size: 22, weight: .semibold))
                if let g = graph {
                    Text("\(g.memoryCount) memories · \(g.nodes.filter { $0.kind == "learned" }.count) learned topics"
                         + (g.partOfDay.isEmpty ? "" : " · \(g.partOfDay)"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer()
            HStack(spacing: 8) {
                TextField("Ask something to see the thought-path…", text: $promptText)
                    .textFieldStyle(.roundedBorder).frame(width: 260)
                    .onSubmit { Task { await trace() } }
                Button("Trace") { Task { await trace() } }
                Button { Task { await load() } } label: { Image(systemName: "arrow.clockwise") }
                    .help("Refresh")
            }
        }
        .padding(16)
    }

    // MARK: edges

    private func edgesCanvas(_ g: BrainGraph, size: CGSize) -> some View {
        Canvas { ctx, _ in
            for e in g.edges {
                guard let a = positions[e.source], let b = positions[e.target] else { continue }
                let onPath = !pathSet.isEmpty && pathSet.contains(e.source) && pathSet.contains(e.target)
                var path = Path()
                path.move(to: a); path.addLine(to: b)
                let color = edgeColor(e.kind, onPath: onPath)
                ctx.stroke(path, with: .color(color),
                           style: StrokeStyle(lineWidth: onPath ? 2.6 : 1.0,
                                              dash: e.kind == "inferred" ? [4, 4] : []))
            }
        }
        .allowsHitTesting(false)
    }

    // MARK: nodes

    private func nodeView(_ node: BrainNode) -> some View {
        let isCore = node.kind == "core"
        let onPath = pathSet.contains(node.id)
        let dimmed = !pathSet.isEmpty && !onPath
        let fontSize: CGFloat = isCore ? 12 : 10
        let weight: Font.Weight = isCore ? .semibold : .regular
        let padH: CGFloat = isCore ? 12 : 9
        let padV: CGFloat = isCore ? 8 : 5
        let isSel = selected?.id == node.id

        let capsule = Capsule()
            .fill(nodeFill(node.kind))
            .overlay(Capsule().strokeBorder(nodeStroke(node.kind), lineWidth: 1))

        return Text(node.label)
            .font(.system(size: fontSize, weight: weight))
            .lineLimit(1)
            .padding(.horizontal, padH)
            .padding(.vertical, padV)
            .background(capsule)
            .foregroundStyle(nodeText(node.kind))
            .scaleEffect(isSel ? 1.12 : 1.0)
            .opacity(dimmed ? 0.32 : 1.0)
            .shadow(color: onPath ? accent.opacity(0.5) : .clear, radius: 8)
            .onTapGesture { selected = isSel ? nil : node }
            .help(node.role ?? node.label)
    }

    // MARK: footer / legend + selection

    private var footer: some View {
        HStack(spacing: 18) {
            legendDot(nodeFill("core"), "Faculty")
            legendDot(nodeFill("learned"), "Learned")
            legendDot(nodeFill("rhythm"), "Rhythm")
            Spacer()
            if let s = selected {
                Text("\(s.label)").fontWeight(.semibold)
                Text(s.role ?? kindWord(s.kind)).foregroundStyle(.secondary).lineLimit(1)
            } else {
                Text("Tap a node · type a prompt to trace the thought-path")
                    .foregroundStyle(.secondary)
            }
        }
        .font(.caption)
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(.ultraThinMaterial)
    }

    private func legendDot(_ c: Color, _ label: String) -> some View {
        HStack(spacing: 5) { Circle().fill(c).frame(width: 9, height: 9); Text(label) }
    }

    // MARK: layout

    private func center(_ size: CGSize) -> CGPoint { CGPoint(x: size.width / 2, y: size.height / 2) }

    /// Place the Model router at center; faculties in a ring; learned topics +
    /// rhythms orbit their parent (memory / rhythms).
    private func layout(in size: CGSize) {
        guard let g = graph, size.width > 1 else { return }
        let c = center(size)
        let R = min(size.width, size.height) * 0.32
        var pos: [String: CGPoint] = [:]

        let core = g.nodes.filter { $0.kind == "core" }
        let ring = core.filter { $0.id != "router" }
        pos["router"] = c
        let ringCount = Double(max(1, ring.count))
        for (i, n) in ring.enumerated() {
            let frac: Double = Double(i) / ringCount
            let ang: Double = frac * 2.0 * Double.pi - Double.pi / 2.0
            let x = c.x + CGFloat(cos(ang)) * R
            let y = c.y + CGFloat(sin(ang)) * R
            pos[n.id] = CGPoint(x: x, y: y)
        }
        // orbit children around their parent
        func orbit(_ children: [BrainNode], around parent: String, radius: CGFloat) {
            guard let p = pos[parent] else { return }
            let count = Double(max(1, children.count))
            for (i, n) in children.enumerated() {
                let frac: Double = Double(i) / count
                let ang: Double = frac * 2.0 * Double.pi
                let x = p.x + CGFloat(cos(ang)) * radius
                let y = p.y + CGFloat(sin(ang)) * radius
                pos[n.id] = CGPoint(x: x, y: y)
            }
        }
        orbit(g.nodes.filter { $0.kind == "learned" }, around: "memory", radius: R * 0.6)
        orbit(g.nodes.filter { $0.kind == "rhythm" }, around: "rhythms", radius: R * 0.5)
        positions = pos
    }

    // MARK: data

    private func load() async {
        loading = true
        let g = await client.brain(prompt: promptText.isEmpty ? nil : promptText)
        await MainActor.run {
            graph = g
            pathSet = Set(g?.thoughtPath ?? [])
            loading = false
        }
    }
    private func trace() async {
        guard !promptText.isEmpty else { pathSet = []; return }
        let g = await client.brain(prompt: promptText)
        await MainActor.run {
            if let g { graph = g; pathSet = Set(g.thoughtPath) }
        }
    }

    // MARK: palette

    private let accent = Color(red: 0.82, green: 0.31, blue: 0.10)
    private func nodeFill(_ k: String) -> Color {
        switch k {
        case "core": return Color.primary.opacity(0.08)
        case "learned": return accent.opacity(0.14)
        case "rhythm": return Color.blue.opacity(0.12)
        default: return Color.gray.opacity(0.1)
        }
    }
    private func nodeStroke(_ k: String) -> Color {
        switch k {
        case "core": return Color.primary.opacity(0.3)
        case "learned": return accent.opacity(0.5)
        case "rhythm": return Color.blue.opacity(0.4)
        default: return .gray
        }
    }
    private func nodeText(_ k: String) -> Color {
        k == "core" ? .primary : (k == "learned" ? accent : .blue)
    }
    private func edgeColor(_ kind: String, onPath: Bool) -> Color {
        if onPath { return accent.opacity(0.9) }
        switch kind {
        case "observed": return accent.opacity(0.3)
        case "inferred": return Color.secondary.opacity(0.3)
        default: return Color.primary.opacity(0.15)
        }
    }
    private func kindWord(_ k: String) -> String {
        k == "learned" ? "learned from your usage" : (k == "rhythm" ? "observed active hour" : "built-in faculty")
    }
}
