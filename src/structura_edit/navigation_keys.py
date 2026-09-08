from PySide6.QtCore import Qt


MOVEMENT = {
    Qt.Key.Key_W: (0, 0, 1), Qt.Key.Key_Up: (0, 0, 1),
    Qt.Key.Key_S: (0, 0, -1), Qt.Key.Key_Down: (0, 0, -1),
    Qt.Key.Key_A: (-1, 0, 0), Qt.Key.Key_Left: (-1, 0, 0),
    Qt.Key.Key_D: (1, 0, 0), Qt.Key.Key_Right: (1, 0, 0),
    Qt.Key.Key_Q: (0, -1, 0), Qt.Key.Key_E: (0, 1, 0),
    Qt.Key.Key_Space: (0, 1, 0),
}
CYRILLIC = dict(zip("цфывйуаь", (Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S,
                                    Qt.Key.Key_D, Qt.Key.Key_Q, Qt.Key.Key_E, Qt.Key.Key_F, Qt.Key.Key_M)))
COMMAND_MODIFIERS = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
                     | Qt.KeyboardModifier.AltModifier)
SPEED_KEYS = {Qt.Key.Key_Minus: -1, Qt.Key.Key_Underscore: -1,
              Qt.Key.Key_Plus: 1, Qt.Key.Key_Equal: 1}


def fly_shortcut(event):
    return (bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            and (event.key() in (Qt.Key.Key_QuoteLeft, Qt.Key.Key_AsciiTilde)
                 or event.text().lower() == "ё"))


def control_key(event):
    text = event.text().lower()
    if text in CYRILLIC:
        return CYRILLIC[text]
    key = event.key()
    return CYRILLIC.get(chr(key).lower(), key) if 0 < key <= 0x10ffff else key


def key_identity(event):
    if event.nativeScanCode():
        return "scan", event.nativeScanCode()
    if event.nativeVirtualKey():
        return "virtual", event.nativeVirtualKey()
    return "key", control_key(event)


class HeldKeys:
    def __init__(self):
        self.pressed = {}

    @property
    def keys(self):
        return set(self.pressed.values())

    @property
    def axes(self):
        directions = {MOVEMENT[key] for key in self.keys if key in MOVEMENT}
        return tuple(sum(direction[axis] for direction in directions) for axis in range(3))

    def press(self, event):
        if not event.isAutoRepeat():
            self.pressed.setdefault(key_identity(event), control_key(event))

    def release(self, event):
        if not event.isAutoRepeat():
            self.pressed.pop(key_identity(event), None)

    def clear(self):
        self.pressed.clear()
