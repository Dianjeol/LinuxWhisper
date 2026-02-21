from pynput import keyboard
import sys

print("⌨️  Keyboard Debugger running...")
print("Please press your 'Command/Super' key, then 'Space', and see what is printed.")
print("Press ESC to exit.")

current_keys = set()

def on_press(key):
    try:
        k = key.char
    except:
        k = key.name
    
    print(f"⬇️  Pressed: {key} (Type: {type(key)})")
    current_keys.add(key)
    
    # Check for our target combo manually
    cmd_pressed = any(k in current_keys for k in [keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r])
    space_pressed = keyboard.Key.space in current_keys
    
    if cmd_pressed and space_pressed:
        print("✅ DETECTED: Command + Space!")

def on_release(key):
    print(f"⬆️  Released: {key}")
    if key in current_keys:
        current_keys.remove(key)
    if key == keyboard.Key.esc:
        return False

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
