import tkinter as tk
import random
import time

GAME_DURATION = 20

class ClickGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Klick mich! - Mini Spiel")
        self.root.geometry("600x400")
        self.root.resizable(False, False)

        self.score = 0
        self.start_time = None
        self.game_running = False

        self.score_label = tk.Label(root, text="Punkte: 0", font=("Arial", 16))
        self.score_label.pack(pady=10)

        self.timer_label = tk.Label(root, text=f"Zeit: {GAME_DURATION}", font=("Arial", 16))
        self.timer_label.pack(pady=5)

        self.canvas = tk.Canvas(root, width=580, height=300, bg="#222")
        self.canvas.pack(pady=10)

        self.start_button = tk.Button(root, text="Spiel starten", font=("Arial", 14),
                                      command=self.start_game)
        self.start_button.pack(pady=5)

        self.click_button = tk.Button(root, text="Klick mich!", font=("Arial", 12),
                                      command=self.on_click)

        self.canvas.create_window(-100, -100, window=self.click_button, tags="button_window")

    def start_game(self):
        if self.game_running:
            return

        self.score = 0
        self.score_label.config(text="Punkte: 0")
        self.start_time = time.time()
        self.game_running = True
        self.start_button.config(state="disabled")

        self.move_button()
        self.update_timer()

    def move_button(self):
        self.root.update_idletasks()
        btn_width = self.click_button.winfo_width()
        btn_height = self.click_button.winfo_height()

        canvas_width = int(self.canvas["width"])
        canvas_height = int(self.canvas["height"])

        x = random.randint(btn_width // 2, canvas_width - btn_width // 2)
        y = random.randint(btn_height // 2, canvas_height - btn_height // 2)

        self.canvas.coords("button_window", x, y)

    def on_click(self):
        if not self.game_running:
            return

        self.score += 1
        self.score_label.config(text=f"Punkte: {self.score}")
        self.move_button()

    def update_timer(self):
        if not self.game_running:
            return

        elapsed = int(time.time() - self.start_time)
        remaining = max(0, GAME_DURATION - elapsed)
        self.timer_label.config(text=f"Zeit: {remaining}")

        if remaining <= 0:
            self.end_game()
        else:
            self.root.after(100, self.update_timer)

    def end_game(self):
        self.game_running = False
        self.start_button.config(state="normal")
        self.canvas.coords("button_window", -100, -100)
        self.timer_label.config(text="Zeit: 0")
        self.show_result()

    def show_result(self):
        result_window = tk.Toplevel(self.root)
        result_window.title("Spiel vorbei!")
        result_window.geometry("300x150")

        msg = tk.Label(result_window,
                       text=f"Zeit abgelaufen!\nDeine Punkte: {self.score}",
                       font=("Arial", 14))
        msg.pack(pady=20)

        close_btn = tk.Button(result_window, text="OK", font=("Arial", 12),
                              command=result_window.destroy)
        close_btn.pack(pady=10)


if __name__ == "__main__":
    root = tk.Tk()
    game = ClickGame(root)
    root.mainloop()
