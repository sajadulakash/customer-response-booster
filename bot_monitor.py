import os
import cv2
import numpy as np
import logging
import subprocess
import threading
import time
from pathlib import Path
from dotenv import load_dotenv
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import easyocr
import mss

# Initialize EasyOCR reader (English only)
try:
    reader = easyocr.Reader(['en'], gpu=False)
    logger_temp = logging.getLogger()
    logger_temp.info("✅ EasyOCR initialized")
except Exception as e:
    logger_temp = logging.getLogger()
    logger_temp.error(f"❌ Failed to initialize EasyOCR: {e}")
    reader = None

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

# Configuration
AUTOHOTKEY_SCRIPT_PATH = os.getenv("AUTOHOTKEY_SCRIPT_PATH", str(Path(__file__).parent / "CallAutomation.ahk"))
TEXT_TO_MONITOR = "Folder is empty"
TIMEOUT_SECONDS = 35  # 35 seconds

# Global variables
selected_zone = None
monitoring = False
text_not_found_time = None


class ScreenZoneSelector:
    def __init__(self, root):
        self.root = root
        self.root.title("Screen Zone Selector - Draw Zone to Monitor")
        
        # Get screen dimensions
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]
        
        # Capture full screenshot once
        self.screenshot = self.sct.grab(self.monitor)
        self.frame = np.array(self.screenshot)
        self.frame = cv2.cvtColor(self.frame, cv2.COLOR_BGRA2RGB)
        
        # Store original dimensions for coordinate mapping
        self.orig_height, self.orig_width = self.frame.shape[:2]
        
        # Scale to 1080 width while maintaining aspect ratio
        self.scale_width = 1080
        self.scale_ratio = self.scale_width / self.orig_width
        self.scale_height = int(self.orig_height * self.scale_ratio)
        
        # Resize frame for display
        self.frame_resized = cv2.resize(self.frame, (self.scale_width, self.scale_height))
        
        # Set window size
        self.root.geometry(f"{self.scale_width}x{self.scale_height + 80}")
        
        # Canvas for drawing
        self.canvas = tk.Canvas(self.root, bg='gray', cursor="crosshair", 
                               width=self.scale_width, height=self.scale_height)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Buttons frame
        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(button_frame, text="Click and drag to select zone, then press 'Next'", 
                font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        
        tk.Button(button_frame, text="Reload SS", command=self.reload_screenshot, 
                 bg="blue", fg="white", font=("Arial", 10, "bold")).pack(side=tk.RIGHT, padx=5)
        
        tk.Button(button_frame, text="Next", command=self.select_zone, 
                 bg="green", fg="white", font=("Arial", 10, "bold")).pack(side=tk.RIGHT, padx=5)
        
        # Mouse tracking
        self.start_x = None
        self.start_y = None
        
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        # Display static screenshot
        self.display_screen()
    
    def display_screen(self):
        """Display static screenshot on canvas"""
        # Convert to PIL Image
        image = Image.fromarray(cv2.cvtColor(self.frame_resized, cv2.COLOR_BGR2RGB))
        self.photo = ImageTk.PhotoImage(image)
        
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
    
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
    
    def on_drag(self, event):
        if self.start_x and self.start_y:
            self.canvas.delete("rect")
            self.canvas.create_rectangle(
                self.start_x, self.start_y, event.x, event.y,
                outline="red", width=3, tags="rect"
            )
    
    def on_release(self, event):
        global selected_zone
        # Map scaled coordinates back to original screen coordinates
        x1 = int(min(self.start_x, event.x) / self.scale_ratio)
        y1 = int(min(self.start_y, event.y) / self.scale_ratio)
        x2 = int(max(self.start_x, event.x) / self.scale_ratio)
        y2 = int(max(self.start_y, event.y) / self.scale_ratio)
        
        selected_zone = (x1, y1, x2, y2)
        logger.info(f"✅ Zone selected (scaled): ({min(self.start_x, event.x)}, {min(self.start_y, event.y)}, {max(self.start_x, event.x)}, {max(self.start_y, event.y)})")
        logger.info(f"✅ Zone selected (original coords): {selected_zone}")
    
    def reload_screenshot(self):
        """Reload screenshot with current PC screen"""
        # Capture new screenshot
        self.screenshot = self.sct.grab(self.monitor)
        self.frame = np.array(self.screenshot)
        self.frame = cv2.cvtColor(self.frame, cv2.COLOR_BGRA2RGB)
        
        # Update original dimensions
        self.orig_height, self.orig_width = self.frame.shape[:2]
        
        # Recalculate scale
        self.scale_ratio = self.scale_width / self.orig_width
        self.scale_height = int(self.orig_height * self.scale_ratio)
        
        # Resize frame for display
        self.frame_resized = cv2.resize(self.frame, (self.scale_width, self.scale_height))
        
        # Update window size
        self.root.geometry(f"{self.scale_width}x{self.scale_height + 80}")
        
        # Clear canvas and redraw
        self.canvas.config(width=self.scale_width, height=self.scale_height)
        self.display_screen()
        logger.info("🔄 Screenshot reloaded")
    
    def select_zone(self):
        if not selected_zone:
            messagebox.showerror("Error", "Please select a zone first!")
            return
        
        self.root.destroy()


class MonitoringApp:
    def __init__(self, root):
        global selected_zone
        
        self.root = root
        self.root.title("Screen Zone Monitor - Text Change Detector")
        self.root.geometry("900x600")
        
        self.monitoring = False
        self.last_detected_text = None
        self.text_unchanged_time = None
        self.selected_zone = selected_zone
        self.sct = mss.mss()
        
        # Title
        tk.Label(self.root, text="Screen Zone Monitor", 
                font=("Arial", 16, "bold")).pack(pady=10)
        
        # Status label
        self.status_label = tk.Label(
            self.root, 
            text="Ready to start monitoring", 
            font=("Arial", 12),
            bg="lightblue",
            wraplength=800,
            pady=10
        )
        self.status_label.pack(pady=10, padx=10, fill=tk.X)
        
        # Canvas for preview
        self.canvas = tk.Canvas(self.root, bg='gray', height=300)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Text display
        self.text_label = tk.Label(
            self.root,
            text="Detected text will appear here",
            font=("Arial", 10),
            wraplength=800,
            justify=tk.LEFT
        )
        self.text_label.pack(pady=5, padx=10, fill=tk.X)
        
        # Buttons
        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(button_frame, text="Start Monitoring", command=self.start_monitoring,
                 bg="green", fg="white", font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Stop Monitoring", command=self.stop_monitoring,
                 bg="red", fg="white", font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=5)
        
        logger.info(f"📊 Selected Zone: {self.selected_zone}")
    
    def get_screenshot_region(self):
        """Get screenshot of the selected zone"""
        x1, y1, x2, y2 = self.selected_zone
        
        region = {
            'left': x1,
            'top': y1,
            'width': x2 - x1,
            'height': y2 - y1
        }
        
        # Create new mss instance for threading safety
        with mss.mss() as sct:
            screenshot = sct.grab(region)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        return frame
    
    def extract_text(self, frame):
        """Extract text from frame using EasyOCR"""
        try:
            if reader is None:
                logger.error("❌ OCR reader not initialized")
                return ""
            
            # EasyOCR expects RGB format
            results = reader.readtext(frame)
            
            # Extract text from results
            text = '\n'.join([result[1] for result in results])
            return text.strip()
        except Exception as e:
            logger.error(f"❌ OCR Error: {type(e).__name__}: {e}")
            return ""
    
    def run_autohotkey_script(self):
        """Run the AutoHotkey script"""
        try:
            if not Path(AUTOHOTKEY_SCRIPT_PATH).exists():
                logger.error(f"AutoHotkey script not found at {AUTOHOTKEY_SCRIPT_PATH}")
                return False
            
            autohotkey_paths = [
                "AutoHotkey.exe",
                "C:\\Program Files\\AutoHotkey\\AutoHotkey.exe",
                "C:\\Program Files (x86)\\AutoHotkey\\AutoHotkey.exe",
            ]
            
            autohotkey_exe = None
            for path in autohotkey_paths:
                if Path(path).exists():
                    autohotkey_exe = path
                    break
            
            if not autohotkey_exe:
                logger.error("AutoHotkey.exe not found")
                return False
            
            logger.info(f"🚀 Running AutoHotkey script")
            subprocess.run([autohotkey_exe, AUTOHOTKEY_SCRIPT_PATH], timeout=15, check=False)
            logger.info("✅ AutoHotkey script executed")
            return True
        except Exception as e:
            logger.error(f"❌ Error running AutoHotkey: {e}")
            return False
    
    def monitor_zone(self):
        """Monitor the selected zone in real-time"""
        while self.monitoring:
            try:
                # Get screenshot of zone
                frame = self.get_screenshot_region()
                
                # Extract text
                extracted_text = self.extract_text(frame)
                
                # If no text detected, don't start countdown
                if not extracted_text or extracted_text.strip() == "":
                    self.last_detected_text = None
                    self.text_unchanged_time = None
                    status = f"⏸️  No text detected in zone"
                    logger.debug(f"⏸️  No text detected")
                # Check if text has changed
                elif extracted_text != self.last_detected_text:
                    # Text changed
                    self.last_detected_text = extracted_text
                    self.text_unchanged_time = None
                    status = f"✅ Text CHANGED - Timer reset"
                    logger.info(f"✅ Text CHANGED:\n{extracted_text}")
                else:
                    # Text hasn't changed (and text exists)
                    if self.text_unchanged_time is None:
                        self.text_unchanged_time = time.time()
                        logger.info(f"⏰ Text unchanged - Starting countdown")
                    
                    time_elapsed = time.time() - self.text_unchanged_time
                    status = f"⏳ Text UNCHANGED for {time_elapsed:.1f}s / {TIMEOUT_SECONDS}s"
                    
                    if time_elapsed > TIMEOUT_SECONDS:
                        logger.info(f"")
                        logger.info(f"🚨 TIMEOUT TRIGGERED! ⏰")
                        logger.info(f"   Text unchanged for {time_elapsed:.1f} seconds")
                        logger.info(f"   Running AutoHotkey script...")
                        logger.info(f"")
                        
                        self.run_autohotkey_script()
                        self.text_unchanged_time = None
                        self.last_detected_text = None
                
                # Display preview and text
                self.display_preview(frame, extracted_text, status)
                
                time.sleep(1)
            
            except Exception as e:
                logger.error(f"❌ Monitoring Error: {e}")
                time.sleep(1)
    
    def display_preview(self, frame, text, status):
        """Display preview on canvas"""
        try:
            frame_resized = cv2.resize(frame, (880, 300))
            image = Image.fromarray(frame_resized)
            photo = ImageTk.PhotoImage(image)
            
            self.canvas.create_image(0, 0, image=photo, anchor=tk.NW)
            self.canvas.image = photo
            
            self.status_label.config(text=status)
            self.text_label.config(text=f"Detected: {text[:300] if text else 'No text detected'}")
            self.root.update_idletasks()
        except:
            pass
    
    def start_monitoring(self):
        if self.monitoring:
            messagebox.showinfo("Info", "Already monitoring")
            return
        
        self.monitoring = True
        self.last_detected_text = None
        self.text_unchanged_time = None
        logger.info("🎬 Starting monitoring...")
        logger.info(f"📍 Zone: {self.selected_zone}")
        logger.info(f"🔍 Monitoring for text CHANGES (not specific text)")
        logger.info(f"⏱️  Timeout: {TIMEOUT_SECONDS} seconds of unchanged text")
        
        thread = threading.Thread(target=self.monitor_zone, daemon=True)
        thread.start()
    
    def stop_monitoring(self):
        self.monitoring = False
        logger.info("🛑 Monitoring stopped")
        self.status_label.config(text="Monitoring stopped")


def main():
    logger.info("=" * 60)
    logger.info("🎯 SCREEN ZONE MONITOR")
    logger.info("=" * 60)
    logger.info("Step 1: Select a zone on your screen")
    logger.info("")
    
    root1 = tk.Tk()
    selector = ScreenZoneSelector(root1)
    root1.mainloop()
    
    if not selected_zone:
        logger.error("❌ No zone selected. Exiting.")
        return
    
    logger.info("")
    logger.info("Step 2: Monitoring zone...")
    logger.info("")
    
    root2 = tk.Tk()
    app = MonitoringApp(root2)
    root2.mainloop()


if __name__ == "__main__":
    main()
