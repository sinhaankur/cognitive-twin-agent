import Carbon.HIToolbox
import AppKit

/// A global hotkey via Carbon's RegisterEventHotKey — the classic menu-bar-app
/// mechanism: works system-wide, needs NO accessibility permission, and fails
/// loudly (nil) if another app already owns the combo, so the caller can pick
/// a fallback instead of silently doing nothing (the research's top papercut:
/// Raycast, ChatGPT and half the ecosystem fight over ⌥Space).
final class HotKey {
    private var hotKeyRef: EventHotKeyRef?
    private var handlerRef: EventHandlerRef?
    private let action: () -> Void

    /// Carbon modifier masks: optionKey 0x0800, controlKey 0x1000, cmdKey 0x0100.
    init?(keyCode: UInt32, carbonModifiers: UInt32, action: @escaping () -> Void) {
        self.action = action
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                                 eventKind: UInt32(kEventHotKeyPressed))
        let selfPtr = Unmanaged.passUnretained(self).toOpaque()
        let installed = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, _, userData in
                guard let userData else { return noErr }
                let me = Unmanaged<HotKey>.fromOpaque(userData).takeUnretainedValue()
                DispatchQueue.main.async { me.action() }
                return noErr
            },
            1, &spec, selfPtr, &handlerRef)
        guard installed == noErr else { return nil }
        let id = EventHotKeyID(signature: OSType(0x56455241 /* 'VERA' */), id: 1)
        let registered = RegisterEventHotKey(keyCode, carbonModifiers, id,
                                             GetApplicationEventTarget(), 0, &hotKeyRef)
        guard registered == noErr, hotKeyRef != nil else {
            if let h = handlerRef { RemoveEventHandler(h) }
            return nil
        }
    }

    deinit {
        if let r = hotKeyRef { UnregisterEventHotKey(r) }
        if let h = handlerRef { RemoveEventHandler(h) }
    }
}
