import SwiftUI

/// The Brain — how the twin thinks and learns, on iPhone.
///
/// Reuses the Rust core's `ctwin_brain` (via TwinCore.brain) so the graph is the
/// same everywhere: cognitive faculties as CORE nodes, topics learned from your
/// prompts as LEARNED nodes, edges tagged by provenance. Tap a node for its role;
/// type a prompt to light up the likely thought-path. Fully on-device.
struct BrainView: View {
    @EnvironmentObject var model: TwinModel
    @Environment(\.dismiss) private var dismiss

    @State private var graph: BrainGraph = BrainGraph(nodes: [], edges: [], thoughtPath: [])
    @State private var positions: [String: CGPoint] = [:]
    @State private var selected: BrainNode?
    @State private var promptText: String = ""
    @State private var pathSet: Set<String> = []

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                GeometryReader { geo in
                    ZStack {
                        Color(.systemBackground)
                        edgesCanvas(size: geo.size)
                        ForEach(graph.nodes) { node in
                            nodeView(node).position(positions[node.id] ?? center(geo.size))
                        }
                    }
                    .onAppear { reload(); layout(in: geo.size) }
                    .onChange(of: graph.nodes.count) { _ in layout(in: geo.size) }
                }
                footer
            }
            .navigationTitle("The Brain")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
            }
            .safeAreaInset(edge: .top) { tracer }
        }
    }

    // MARK: prompt tracer
    private var tracer: some View {
        HStack {
            TextField("Ask to trace the thought-path…", text: $promptText)
                .textFieldStyle(.roundedBorder)
                .submitLabel(.go)
                .onSubmit { trace() }
            Button("Trace") { trace() }.buttonStyle(.borderedProminent).tint(accent)
        }
        .padding(.horizontal).padding(.vertical, 8)
        .background(.ultraThinMaterial)
    }

    // MARK: edges
    private func edgesCanvas(size: CGSize) -> some View {
        Canvas { ctx, _ in
            for e in graph.edges {
                guard let a = positions[e.source], let b = positions[e.target] else { continue }
                let onPath = !pathSet.isEmpty && pathSet.contains(e.source) && pathSet.contains(e.target)
                var path = Path(); path.move(to: a); path.addLine(to: b)
                ctx.stroke(path, with: .color(edgeColor(e.kind, onPath: onPath)),
                           style: StrokeStyle(lineWidth: onPath ? 2.6 : 1.0,
                                              dash: e.kind == "inferred" ? [4, 4] : []))
            }
        }
        .allowsHitTesting(false)
    }

    // MARK: node
    private func nodeView(_ node: BrainNode) -> some View {
        let isCore = node.kind == "core"
        let onPath = pathSet.contains(node.id)
        let dimmed = !pathSet.isEmpty && !onPath
        let isSel = selected?.id == node.id
        let capsule = Capsule().fill(nodeFill(node.kind))
            .overlay(Capsule().strokeBorder(nodeStroke(node.kind), lineWidth: 1))
        return Text(node.label)
            .font(.system(size: isCore ? 12 : 10, weight: isCore ? .semibold : .regular))
            .lineLimit(1)
            .padding(.horizontal, isCore ? 11 : 8)
            .padding(.vertical, isCore ? 7 : 5)
            .background(capsule)
            .foregroundStyle(nodeText(node.kind))
            .scaleEffect(isSel ? 1.14 : 1.0)
            .opacity(dimmed ? 0.34 : 1.0)
            .shadow(color: onPath ? accent.opacity(0.5) : .clear, radius: 7)
            .onTapGesture { withAnimation(.spring(duration: 0.25)) { selected = isSel ? nil : node } }
    }

    // MARK: footer
    private var footer: some View {
        VStack(spacing: 6) {
            HStack(spacing: 16) {
                legendDot(nodeFill("core"), "Faculty")
                legendDot(nodeFill("learned"), "Learned")
                Spacer()
                Text("\(graph.nodes.filter { $0.kind == "learned" }.count) learned")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            if let s = selected {
                Text(s.role ?? kindWord(s.kind)).font(.caption)
                    .foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            } else {
                Text("Tap a node · type a prompt to trace")
                    .font(.caption).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(.horizontal).padding(.vertical, 10)
        .background(.ultraThinMaterial)
    }
    private func legendDot(_ c: Color, _ label: String) -> some View {
        HStack(spacing: 5) { Circle().fill(c).frame(width: 9, height: 9); Text(label).font(.caption2) }
    }

    // MARK: data
    private func reload() {
        graph = TwinCore.brain(recentPrompts: model.recentPrompts, prompt: promptText)
        pathSet = Set(graph.thoughtPath)
    }
    private func trace() {
        graph = TwinCore.brain(recentPrompts: model.recentPrompts, prompt: promptText)
        withAnimation { pathSet = Set(graph.thoughtPath) }
    }

    // MARK: layout
    private func center(_ size: CGSize) -> CGPoint { CGPoint(x: size.width / 2, y: size.height / 2) }
    private func layout(in size: CGSize) {
        guard size.width > 1, !graph.nodes.isEmpty else { return }
        let c = center(size)
        let R = min(size.width, size.height) * 0.34
        var pos: [String: CGPoint] = [:]
        let ring = graph.nodes.filter { $0.kind == "core" && $0.id != "router" }
        pos["router"] = c
        let ringCount = Double(max(1, ring.count))
        for (i, n) in ring.enumerated() {
            let frac: Double = Double(i) / ringCount
            let ang: Double = frac * 2.0 * Double.pi - Double.pi / 2.0
            pos[n.id] = CGPoint(x: c.x + CGFloat(cos(ang)) * R, y: c.y + CGFloat(sin(ang)) * R)
        }
        let learned = graph.nodes.filter { $0.kind == "learned" }
        if let p = pos["memory"] {
            let count = Double(max(1, learned.count))
            for (i, n) in learned.enumerated() {
                let frac: Double = Double(i) / count
                let ang: Double = frac * 2.0 * Double.pi
                pos[n.id] = CGPoint(x: p.x + CGFloat(cos(ang)) * R * 0.55,
                                    y: p.y + CGFloat(sin(ang)) * R * 0.55)
            }
        }
        positions = pos
    }

    // MARK: palette
    private let accent = Color(red: 0.82, green: 0.31, blue: 0.10)
    private func nodeFill(_ k: String) -> Color {
        k == "core" ? Color.primary.opacity(0.08) : (k == "learned" ? accent.opacity(0.14) : Color.blue.opacity(0.12))
    }
    private func nodeStroke(_ k: String) -> Color {
        k == "core" ? Color.primary.opacity(0.3) : (k == "learned" ? accent.opacity(0.5) : Color.blue.opacity(0.4))
    }
    private func nodeText(_ k: String) -> Color {
        k == "core" ? .primary : (k == "learned" ? accent : .blue)
    }
    private func edgeColor(_ kind: String, onPath: Bool) -> Color {
        if onPath { return accent.opacity(0.9) }
        return kind == "observed" ? accent.opacity(0.3) : Color.primary.opacity(0.15)
    }
    private func kindWord(_ k: String) -> String {
        k == "learned" ? "learned from your usage" : (k == "rhythm" ? "observed active hour" : "built-in faculty")
    }
}
