// Settings window: a System Settings–style grouped form built with SwiftUI.
//
// Compiled into dist/libVlowGlass.dylib together with VlowGlass.swift and
// driven from Python (vlow/settings_window.py). Python hands over the current
// configuration as JSON and a target/selector; every change made in the
// window is debounced and sent back as JSON to that selector, where Python
// writes config.toml and applies the change live. No Save button — like
// System Settings, edits take effect as you make them.

import AppKit
import Combine
import SwiftUI

struct LocalModelInfo: Codable, Equatable {
    var key = ""
    var name = ""
    var size = ""
    var blurb = ""
}

struct SettingsData: Codable, Equatable {
    var hotkey = "fn"
    var mode = "toggle"
    var backend = "mlx"
    var local_model = "whisper-large-v3"
    var auto_threshold_sec: Double = 60
    var assemblyai_api_key = ""
    var aai_language = ""
    var known_words: [String] = []
    var check_updates = true
    var config_path = ""
    var app_version = ""
    var local_models: [LocalModelInfo] = []  // read-only, from local_models.py
}

struct ModelStatus: Codable, Equatable {
    var model = ""  // LocalModelInfo.key
    var state = "unknown"  // missing | downloading | ready | error
    var progress: Double = 0
    var detail = ""
}

struct KnownWord: Identifiable, Equatable {
    let id = UUID()
    var text: String
}

@objc(VlowSettingsModel)
public final class VlowSettingsModel: NSObject, ObservableObject {
    @Published var data = SettingsData()
    @Published var words: [KnownWord] = []
    @Published var modelStatus: [String: ModelStatus] = [:]  // by model key
    @Published var updateStatus = ""
    var onChange: ((String) -> Void)?
    var onAction: ((String) -> Void)?

    private var lastJSON = ""
    private var bag = Set<AnyCancellable>()

    override init() {
        super.init()
        Publishers.CombineLatest($data, $words)
            .debounce(for: .milliseconds(250), scheduler: RunLoop.main)
            .sink { [weak self] data, words in self?.emit(data, words) }
            .store(in: &bag)
    }

    func load(json: String) {
        guard let raw = json.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(SettingsData.self, from: raw)
        else { return }
        data = parsed
        words = parsed.known_words.map { KnownWord(text: $0) }
        lastJSON = canonical(parsed) ?? ""
    }

    private func canonical(_ d: SettingsData) -> String? {
        let enc = JSONEncoder()
        enc.outputFormatting = [.sortedKeys]
        guard let out = try? enc.encode(d) else { return nil }
        return String(decoding: out, as: UTF8.self)
    }

    private func emit(_ data: SettingsData, _ words: [KnownWord]) {
        var out = data
        out.known_words = words.map { $0.text.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        guard let json = canonical(out), json != lastJSON else { return }
        lastJSON = json
        onChange?(json)
    }
}

private struct SettingsView: View {
    @ObservedObject var model: VlowSettingsModel
    @State private var selectedWord: KnownWord.ID?

    private var hotkeyName: String {
        switch model.data.hotkey {
        case "right_opt": return "Right Option"
        case "left_opt": return "Left Option"
        case "right_cmd": return "Right Command"
        default: return "Fn"
        }
    }

    var body: some View {
        Form {
            Section {
                Picker("Hotkey", selection: $model.data.hotkey) {
                    Text("Fn / Globe").tag("fn")
                    Text("Right Option").tag("right_opt")
                    Text("Left Option").tag("left_opt")
                    Text("Right Command").tag("right_cmd")
                }
                Picker("Mode", selection: $model.data.mode) {
                    Text("Toggle").tag("toggle")
                    Text("Push to talk").tag("ptt")
                }
            } header: {
                Text("Dictation")
            } footer: {
                if model.data.mode == "ptt" {
                    Text("Hold \(hotkeyName) to stream live via AssemblyAI; release to stop.")
                } else {
                    Text("Double-tap \(hotkeyName) to start recording and again to stop and paste. Hold it to stream live via AssemblyAI.")
                }
            }

            Section {
                Picker("Backend", selection: $model.data.backend) {
                    Text("On-device (MLX)").tag("mlx")
                    Text("AssemblyAI (cloud)").tag("assemblyai")
                    Text("Auto — by duration").tag("auto")
                }
                if model.data.backend == "auto" {
                    LabeledContent("Send to cloud above") {
                        HStack(spacing: 4) {
                            TextField(
                                "", value: $model.data.auto_threshold_sec,
                                format: .number.precision(.fractionLength(0))
                            )
                            .frame(width: 56)
                            .multilineTextAlignment(.trailing)
                            Stepper(
                                "", value: $model.data.auto_threshold_sec,
                                in: 5...3600, step: 5
                            )
                            .labelsHidden()
                            Text("seconds").foregroundStyle(.secondary)
                        }
                    }
                }
            } header: {
                Text("Transcription")
            } footer: {
                switch model.data.backend {
                case "mlx":
                    Text("Runs entirely on this Mac using the on-device model selected below.")
                case "assemblyai":
                    Text("Every recording is uploaded to AssemblyAI.")
                default:
                    Text("Short recordings stay on-device; longer ones are uploaded to AssemblyAI.")
                }
            }

            Section {
                Picker("Model", selection: $model.data.local_model) {
                    ForEach(model.data.local_models, id: \.key) { m in
                        Text(m.name).tag(m.key)
                    }
                }
                ForEach(model.data.local_models, id: \.key) { m in
                    let st = model.modelStatus[m.key] ?? ModelStatus()
                    LabeledContent {
                        switch st.state {
                        case "ready":
                            Label("Ready", systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                                .labelStyle(.titleAndIcon)
                        case "downloading":
                            HStack(spacing: 8) {
                                ProgressView(value: st.progress)
                                    .frame(width: 140)
                                Text(st.progress.formatted(.percent.precision(.fractionLength(0))))
                                    .monospacedDigit()
                                    .foregroundStyle(.secondary)
                                    .frame(width: 40, alignment: .trailing)
                            }
                        case "error":
                            Button("Retry Download") { model.onAction?("downloadModel:\(m.key)") }
                        default:
                            Button("Download…") { model.onAction?("downloadModel:\(m.key)") }
                        }
                    } label: {
                        Text(m.name)
                        Text(st.detail.isEmpty ? m.size : st.detail)
                            .font(.caption)
                            .foregroundStyle(st.state == "error" ? .red : .secondary)
                    }
                }
            } header: {
                Text("On-device model")
            } footer: {
                let blurb = model.data.local_models.first { $0.key == model.data.local_model }?.blurb ?? ""
                Text(blurb + (blurb.isEmpty ? "" : " ") + "Needed for the on-device and auto backends; downloaded once from Hugging Face into ~/.cache/huggingface. The AssemblyAI backend works without it.")
            }

            Section {
                SecureField("API key", text: $model.data.assemblyai_api_key)
                TextField(
                    "Language", text: $model.data.aai_language,
                    prompt: Text("auto-detect")
                )
            } header: {
                Text("AssemblyAI")
            } footer: {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Needed for the hold-to-stream gesture and for the cloud and auto backends. Language is an ISO 639-1 code such as de or en; leave it empty to auto-detect.")
                    Link("Get an API key…", destination: URL(string: "https://www.assemblyai.com/dashboard/api-keys")!)
                }
            }

            Section {
                List(selection: $selectedWord) {
                    ForEach($model.words) { $word in
                        TextField("Word or name", text: $word.text)
                            .textFieldStyle(.plain)
                    }
                }
                .frame(minHeight: 120, maxHeight: 160)
                .alternatingRowBackgrounds()
                HStack(spacing: 0) {
                    Button {
                        let w = KnownWord(text: "")
                        model.words.append(w)
                        selectedWord = w.id
                    } label: {
                        Image(systemName: "plus").frame(width: 24, height: 20)
                    }
                    Divider().frame(height: 14)
                    Button {
                        if let id = selectedWord {
                            model.words.removeAll { $0.id == id }
                            selectedWord = nil
                        }
                    } label: {
                        Image(systemName: "minus").frame(width: 24, height: 20)
                    }
                    .disabled(selectedWord == nil)
                    Spacer()
                }
                .buttonStyle(.borderless)
            } header: {
                Text("Known words")
            } footer: {
                Text("Names and terms every backend is nudged toward. Applied from the next recording on.")
            }

            Section {
                LabeledContent {
                    Button("Check Now") { model.onAction?("checkUpdates") }
                } label: {
                    Text("Version \(model.data.app_version)")
                    if !model.updateStatus.isEmpty {
                        Text(model.updateStatus).font(.caption).foregroundStyle(.secondary)
                    }
                }
                Toggle("Check for updates automatically", isOn: $model.data.check_updates)
            } header: {
                Text("Updates")
            } footer: {
                Text("Updates come from the vlow GitHub releases. Installing one replaces the app and relaunches it; macOS will ask for Accessibility again afterwards.")
            }

            Section {
                LabeledContent("Config file") {
                    Button("Show in Finder") {
                        NSWorkspace.shared.selectFile(model.data.config_path, inFileViewerRootedAtPath: "")
                    }
                }
            } footer: {
                Text(model.data.config_path)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
            }
        }
        .formStyle(.grouped)
        .frame(width: 520)
    }
}

@objc(VlowSettings)
public final class VlowSettings: NSObject {
    private static var window: NSWindow?
    private static let model = VlowSettingsModel()

    /// Show (or bring forward) the settings window. `json` is the current
    /// configuration; each change is delivered as JSON to
    /// `[target performSelector:selector withObject:json]` on the main thread,
    /// button presses (e.g. "downloadModel") to `actionSelector` as a string.
    @MainActor
    @objc(show:target:selector:actionSelector:)
    public static func show(_ json: String, target: NSObject, selector: String, actionSelector: String) {
        model.load(json: json)
        let sel = NSSelectorFromString(selector)
        let actionSel = NSSelectorFromString(actionSelector)
        model.onChange = { [weak target] out in
            _ = target?.perform(sel, with: out as NSString)
        }
        model.onAction = { [weak target] name in
            _ = target?.perform(actionSel, with: name as NSString)
        }
        if window == nil {
            let host = NSHostingController(rootView: SettingsView(model: model))
            let w = NSWindow(contentViewController: host)
            w.title = "vlow Settings"
            w.styleMask = [.titled, .closable, .miniaturizable, .resizable]
            w.isReleasedWhenClosed = false
            w.contentMinSize = NSSize(width: 520, height: 480)
            w.contentMaxSize = NSSize(width: 520, height: 2000)
            let screenH = NSScreen.main?.visibleFrame.height ?? 900
            w.setContentSize(NSSize(width: 520, height: min(860, screenH - 60)))
            w.center()
            window = w
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    @MainActor
    @objc(setUpdateStatus:)
    public static func setUpdateStatus(_ text: String) {
        model.updateStatus = text
    }

    /// Update one on-device model row: {"model","state","progress","detail"}.
    @MainActor
    @objc(setModelStatus:)
    public static func setModelStatus(_ json: String) {
        guard let raw = json.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(ModelStatus.self, from: raw)
        else { return }
        model.modelStatus[parsed.model] = parsed
    }

    /// Replace the window's contents (e.g. after config.toml changed on disk).
    @MainActor
    @objc(update:)
    public static func update(_ json: String) {
        model.load(json: json)
    }

    @MainActor
    @objc public static func isVisible() -> Bool {
        window?.isVisible ?? false
    }

    /// Test hook: apply `json` as if the user had edited the form, so the
    /// debounced change callback fires without UI interaction.
    @MainActor
    @objc(simulateEdit:)
    public static func simulateEdit(_ json: String) {
        guard let raw = json.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(SettingsData.self, from: raw)
        else { return }
        model.data = parsed
        model.words = parsed.known_words.map { KnownWord(text: $0) }
    }
}
