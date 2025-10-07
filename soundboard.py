import os
import json
import sounddevice as sd
import soundfile as sf
import tkinter as tk
import ttkbootstrap as ttk
from tkinter import messagebox, simpledialog
import threading
import random
import keyboard  # For global hotkeys
import platform

# === SETTINGS ===
SOUND_FOLDER = "D:/Soundboard"
OUTPUT_DEVICE_NAME = "VB-Audio Virtual Cable"
MAX_COLUMNS = 4
KEYBIND_FILE = "keybinds.json"


# === FIND OUTPUT DEVICE ===
def get_output_device(name):
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if name.lower() in d['name'].lower() and d['max_output_channels'] > 0:
            return i
    return None

output_device = get_output_device(OUTPUT_DEVICE_NAME)
if output_device is None:
    messagebox.showerror("Error", f"Output device '{OUTPUT_DEVICE_NAME}' not found!")
    exit()

# === GLOBALS ===
volume = 1.0
is_playing = False
sound_buttons = []
keybinds = {}  # sound_name: key
current_play_thread = None
stop_flag = threading.Event()

# === LOAD KEYBINDS ===
def load_keybinds():
    global keybinds
    if os.path.exists(KEYBIND_FILE):
        with open(KEYBIND_FILE, "r") as f:
            keybinds = json.load(f)

def save_keybinds():
    with open(KEYBIND_FILE, "w") as f:
        json.dump(keybinds, f, indent=4)


# --- GLOBAL HOTKEY REGISTRATION FOR SOUNDS ---
registered_hotkeys = []

def register_sound_hotkeys():
    global registered_hotkeys
    # Unregister previous hotkeys
    for hk in registered_hotkeys:
        keyboard.remove_hotkey(hk)
    registered_hotkeys = []
    # Register new hotkeys
    for name, key in keybinds.items():
        def make_callback(sound_name=name):
            def callback():
                for sound in sound_files:
                    if os.path.splitext(os.path.basename(sound))[0] == sound_name:
                        play_sound(sound)
                        break
            return callback
        if key:
            hk = keyboard.add_hotkey(key, make_callback())
            registered_hotkeys.append(hk)

def load_keybinds():
    global keybinds
    if os.path.exists(KEYBIND_FILE):
        with open(KEYBIND_FILE, "r") as f:
            keybinds = json.load(f)
    register_sound_hotkeys()

def save_keybinds():
    with open(KEYBIND_FILE, "w") as f:
        json.dump(keybinds, f, indent=4)
    register_sound_hotkeys()

load_keybinds()

# ----  Alt+S  show / hide support  ----
window_visible = False   # module-level flag

def toggle_window():
    """Toggle Tkinter window visibility."""
    global window_visible
    if window_visible:
        root.withdraw()
        window_visible = False
    else:
        root.deiconify()
        root.lift()
        root.focus_force()
        window_visible = True

def start_toggle_hotkey():
    """Run Alt+S listener in a background thread."""
    def _listen():
        keyboard.add_hotkey("alt+s", toggle_window)
        keyboard.wait()      # keep thread alive
    threading.Thread(target=_listen, daemon=True).start()

# === PLAYBACK FUNCTION ===
def play_sound(file_path):
    global is_playing, current_play_thread, stop_flag

    if is_playing:
        return

    def _play():
        global is_playing
        stop_flag.clear()
        try:
            data, samplerate = sf.read(file_path, dtype='float32')
            if len(data.shape) == 1:
                data = data[:, None]
            data = data * volume
            is_playing = True
            sd.play(data, samplerate=samplerate, device=output_device, blocking=False)

            # Wait loop to check stop_flag
            total_frames = data.shape[0]
            frames_played = 0
            block_size = 1024
            while frames_played < total_frames and not stop_flag.is_set():
                frames_played += block_size
                sd.sleep(int(1000 * block_size / samplerate))
            sd.stop()
        except Exception as e:
            print(f"Playback error: {e}")
        finally:
            is_playing = False

    current_play_thread = threading.Thread(target=_play, daemon=True)
    current_play_thread.start()

def stop_all_sounds():
    global stop_flag
    stop_flag.set()

def play_random_sound():
    if sound_files:
        play_sound(random.choice(sound_files))

def change_volume(val):
    global volume
    volume = float(val)

# === LOAD SOUNDS ===
def load_sounds(folder):
    if not os.path.exists(folder):
        messagebox.showerror("Error", f"Folder not found: {folder}")
        return []
    return [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".wav")]

sound_files = load_sounds(SOUND_FOLDER)
if not sound_files:
    messagebox.showerror("Error", f"No .wav files found in {SOUND_FOLDER}")
    exit()

# === KEYBIND GUI WITH SCROLLBAR AND MOUSE WHEEL ===
def open_keybind_editor():
    editor = tk.Toplevel(root)
    editor.title("Edit Keybinds")
    editor.geometry("400x500")
    editor.resizable(False, False)

    lbl = ttk.Label(editor, text="Click a sound to assign a keybind:", font=("Segoe UI", 12))
    lbl.pack(pady=10)

    # --- Clear All Keybinds Button ---
    def clear_all_keybinds():
        global keybinds
        if messagebox.askyesno("Confirm", "Are you sure you want to remove all keybinds?"):
            keybinds = {}
            save_keybinds()
            for child in scroll_frame.winfo_children():
                if isinstance(child, ttk.Button):
                    name = child.cget("text").split(" → ")[0]
                    child.configure(text=f"{name} → ")

    clear_btn = ttk.Button(editor, text="🗑 Clear All Keybinds", bootstyle="danger-outline", command=clear_all_keybinds)
    clear_btn.pack(pady=(0,5))

    # --- Mini Search Bar ---
    search_var_editor = tk.StringVar()
    search_entry_editor = ttk.Entry(editor, textvariable=search_var_editor, width=30)
    search_entry_editor.pack(pady=(0,10))

    def on_editor_search_key(event=None):
        query = search_var_editor.get().lower().strip()
        for btn in scroll_frame.winfo_children():
            if isinstance(btn, ttk.Button):
                name = btn.cget("text").split(" → ")[0].lower()
                if query in name:
                    btn.pack(pady=3)
                else:
                    btn.pack_forget()

    search_entry_editor.bind("<KeyRelease>", on_editor_search_key)

    # --- Scrollable Frame ---
    canvas = tk.Canvas(editor)
    scrollbar = ttk.Scrollbar(editor, orient="vertical", command=canvas.yview)
    scroll_frame = ttk.Frame(canvas)

    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # --- Sound Buttons ---
    for idx, sound in enumerate(sound_files):
        name = os.path.splitext(os.path.basename(sound))[0]
        current_key = keybinds.get(name, "")
        btn = ttk.Button(scroll_frame, text=f"{name} → {current_key}", width=40)
        btn.pack(pady=3)

        def assign_key(event=None, sname=name, b=btn):
            key = simpledialog.askstring("Assign Key", f"Press a key for '{sname}':")
            if key:
                keybinds[sname] = key.lower()
                b.configure(text=f"{sname} → {key.lower()}")
                save_keybinds()

        btn.configure(command=assign_key)

    # --- Mouse Wheel Support ---
    def _on_mousewheel(event):
        import platform
        if platform.system() == 'Windows':
            canvas.yview_scroll(-int(event.delta / 120), "units")
        elif platform.system() == 'Darwin':
            canvas.yview_scroll(-int(event.delta), "units")
        else:  # Linux
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")

    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    canvas.bind_all("<Button-4>", _on_mousewheel)
    canvas.bind_all("<Button-5>", _on_mousewheel)


# === GLOBAL HOTKEY ===
def setup_global_hotkey():
    def hotkey_listener():
        keyboard.add_hotkey('ctrl+s', stop_all_sounds)
        keyboard.wait()
    threading.Thread(target=hotkey_listener, daemon=True).start()

setup_global_hotkey()

# === GUI SETUP ===
root = ttk.Window(themename="darkly")
root.title("🎧 Soundboard")

root.overrideredirect(True)  # removes default title bar

# --- Custom top bar frame ---
top_bar = tk.Frame(root, bg="#1E1E2F", height=30)  # adjust color/height
top_bar.pack(fill="x", side="top")


# --- Drag logic only on top_bar ---
def start_move(event):
    global x_offset, y_offset
    x_offset = event.x
    y_offset = event.y

def do_move(event):
    x = event.x_root - x_offset
    y = event.y_root - y_offset
    root.geometry(f"+{x}+{y}")

top_bar.bind("<ButtonPress-1>", start_move)
top_bar.bind("<B1-Motion>", do_move)
title_label = ttk.Label(root, text="🎵 Soundboard", font=("Segoe UI", 20, "bold"))
title_label.pack(pady=15)

# --- Search Bar ---
search_var = tk.StringVar()
search_entry = ttk.Entry(root, textvariable=search_var, width=30, font=("Segoe UI", 10))
search_entry.insert(0, "Search for sounds...")

search_active = False

def on_search_focus_in(event):
    global search_active
    if search_entry.get() == "Search for sounds...":
        search_entry.delete(0, tk.END)
    search_active = True

def on_search_focus_out(event):
    global search_active
    if search_entry.get().strip() == "":
        search_entry.insert(0, "Search for sounds...")
    search_active = False

def on_search_key(event):
    global search_active
    query = search_var.get().lower().strip()
    if event.keysym == "Escape":
        search_entry.delete(0, tk.END)
        search_entry.insert(0, "Search for sounds...")
        for button in sound_buttons:
            button.grid()
        root.focus()
        search_active = False
        return
    if query == "" or query == "search for sounds...":
        for button in sound_buttons:
            button.grid()
    else:
        for button in sound_buttons:
            text = button.cget("text").lower()
            if query in text:
                button.grid()
            else:
                button.grid_remove()

search_entry.bind("<FocusIn>", on_search_focus_in)
search_entry.bind("<FocusOut>", on_search_focus_out)
search_entry.bind("<KeyRelease>", on_search_key)
search_entry.pack(pady=5)

# --- Controls ---
stop_btn = ttk.Button(root, text="⏹ Stop", bootstyle="danger-outline", command=stop_all_sounds)
stop_btn.pack(pady=5)

random_btn = ttk.Button(root, text="🎲 Random", bootstyle="warning-outline", command=play_random_sound)
random_btn.pack(pady=5)

keybind_editor_btn = ttk.Button(root, text="⌨️ Edit Keybinds", bootstyle="info-outline", command=open_keybind_editor)
keybind_editor_btn.pack(pady=5)

volume_label = ttk.Label(root, text="Volume")
volume_label.pack()
volume_slider = ttk.Scale(root, from_=0.0, to=1.0, orient="horizontal", command=change_volume)
volume_slider.set(volume)
volume_slider.pack(pady=(0,10), fill="x", padx=20)

# --- Sound Buttons ---
frame = ttk.Frame(root)
frame.pack(padx=15, pady=15, fill="both", expand=True)

for idx, sound in enumerate(sound_files):
    name = os.path.splitext(os.path.basename(sound))[0]
    btn = ttk.Button(frame, text=name, width=25, bootstyle="info-outline",
                     command=lambda s=sound: play_sound(s))
    row = idx // MAX_COLUMNS
    col = idx % MAX_COLUMNS
    btn.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
    sound_buttons.append(btn)

for c in range(MAX_COLUMNS):
    frame.grid_columnconfigure(c, weight=1)

# --- KEY PRESS DETECTION ---
def on_key_press(event):
    key = event.keysym.lower()
    for name, assigned_key in keybinds.items():
        if key == assigned_key:
            for sound in sound_files:
                if os.path.splitext(os.path.basename(sound))[0] == name:
                    play_sound(sound)
                    break

# Remove Tkinter key binding, since we now use global hotkeys
# root.bind("<Key>", on_key_press)

# --- PROGRESS BAR ---
progress_var = tk.DoubleVar()
progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
progress_bar.pack(fill="x", padx=15, pady=(0,10))

def update_progress(file_path):
    global stop_flag
    try:
        data, samplerate = sf.read(file_path, dtype='float32')
        total_frames = len(data)
        block_size = 1024
        frames_played = 0
        while frames_played < total_frames and not stop_flag.is_set():
            frames_played += block_size
            percent = min(frames_played / total_frames * 100, 100)
            progress_var.set(percent)
            sd.sleep(int(1000 * block_size / samplerate))
        progress_var.set(0)
    except:
        progress_var.set(0)

# Modify play_sound to update progress bar
def play_sound(file_path):
    global is_playing, current_play_thread, stop_flag

    if is_playing:
        return

    def _play():
        global is_playing
        stop_flag.clear()
        try:
            data, samplerate = sf.read(file_path, dtype='float32')
            if len(data.shape) == 1:
                data = data[:, None]
            data = data * volume
            is_playing = True
            sd.play(data, samplerate=samplerate, device=output_device, blocking=False)

            # Start progress bar thread
            threading.Thread(target=update_progress, args=(file_path,), daemon=True).start()

            # Wait loop
            total_frames = data.shape[0]
            frames_played = 0
            block_size = 1024
            while frames_played < total_frames and not stop_flag.is_set():
                frames_played += block_size
                sd.sleep(int(1000 * block_size / samplerate))
            sd.stop()
        except Exception as e:
            print(f"Playback error: {e}")
        finally:
            progress_var.set(0)
            is_playing = False

    current_play_thread = threading.Thread(target=_play, daemon=True)
    current_play_thread.start()



# --- AUTO CAPTIONS ---
caption_var = tk.StringVar()
caption_label = ttk.Label(root, textvariable=caption_var, font=("Segoe UI", 12, "bold"), anchor="center")
caption_label.pack(pady=(0,5), fill="x")

# Modify play_sound to update caption
def play_sound(file_path):
    global is_playing, current_play_thread, stop_flag

    if is_playing:
        return

    sound_name = os.path.splitext(os.path.basename(file_path))[0]

    def _play():
        global is_playing
        stop_flag.clear()
        caption_var.set(sound_name)  # Set caption at start
        try:
            data, samplerate = sf.read(file_path, dtype='float32')
            if len(data.shape) == 1:
                data = data[:, None]
            data = data * volume
            is_playing = True
            sd.play(data, samplerate=samplerate, device=output_device, blocking=False)

            # Start progress bar thread
            threading.Thread(target=update_progress, args=(file_path,), daemon=True).start()

            # Wait loop
            total_frames = data.shape[0]
            frames_played = 0
            block_size = 1024
            while frames_played < total_frames and not stop_flag.is_set():
                frames_played += block_size
                sd.sleep(int(1000 * block_size / samplerate))
            sd.stop()
        except Exception as e:
            print(f"Playback error: {e}")
        finally:
            progress_var.set(0)
            caption_var.set("")  # Clear caption at end
            is_playing = False

    current_play_thread = threading.Thread(target=_play, daemon=True)
    current_play_thread.start()


# Auto-size window
root.update_idletasks()
window_width = min(root.winfo_reqwidth() + 60, root.winfo_screenwidth() - 100)
window_height = min(root.winfo_reqheight() + 200, root.winfo_screenheight() - 100)
root.geometry(f"{window_width}x{window_height}")
root.withdraw()          # start minimized
start_toggle_hotkey()    # enable Alt+S toggle

root.mainloop()
