import sys
import os
import pygame
import queue
import time
import pyaudio
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QLabel, QComboBox, QFrame, QGraphicsOpacityEffect,
                             QPushButton, QSpinBox, QCheckBox, QGraphicsDropShadowEffect, QSlider)
from PySide6.QtCore import Qt, QTimer, Slot, Signal, QThread, QPropertyAnimation, QPoint, QEasingCurve, QUrl
from PySide6.QtGui import QPixmap, QColor, QFont, QIcon, QMovie
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from voice_engine import VoiceEngine
from config_manager import ConfigManager
from timer_logic import SpellTimer
import PySide6.QtGui as QtGui
from PySide6.QtWidgets import QToolTip
from PySide6.QtGui import QPainter, QPainterPath, QPolygon

class HoverButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)

    def enterEvent(self, event):
        tooltip = self.toolTip()
        if tooltip:
            QToolTip.showText(QtGui.QCursor.pos(), tooltip, self)
        super().enterEvent(event)



class SpeechBubble(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(250)
        self.setMinimumHeight(60)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.layout = QVBoxLayout(self)
        self.label = QLabel("")
        self.label.setFont(QFont("Comic Sans MS", 12))
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color: #333; background: transparent; border: none; padding: 5px;")
        self.layout.addWidget(self.label)
        
        self.hide()

    def setText(self, text):
        self.label.setText(text)
        self.adjustSize()
        self.setFixedWidth(max(250, self.label.width() + 20))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Bubble Body
        rect = self.rect().adjusted(1, 1, -12, -1) # Leave space for the triangle on the right
        painter.setBrush(QColor("#FFFDE7"))
        painter.setPen(QtGui.QPen(QColor("#333"), 2))
        painter.drawRoundedRect(rect, 15, 15)
        
        # Triangle pointing right (towards Gragas)
        triangle = QPolygon([
            QPoint(rect.right(), rect.center().y() - 10),
            QPoint(rect.right() + 10, rect.center().y()),
            QPoint(rect.right(), rect.center().y() + 10)
        ])
        painter.drawPolygon(triangle)
        # Hide the border between bubble and triangle
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(triangle)

class BootControl(QWidget):
    def __init__(self, role, parent):
        super().__init__()
        self.role = role.lower()
        self.main_window = parent
        self.init_ui()

    def init_ui(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(10)
        self.layout.setAlignment(Qt.AlignCenter)

        # Ionian
        self.ionian = HoverButton()
        self.setup_btn(self.ionian, "Ionian_Boots_of_Lucidity_HD.png", "Ionian Boots (+10 Haste)")
        self.ionian.clicked.connect(self.on_ionian_clicked)
        self.layout.addWidget(self.ionian)

        # Crimson
        self.crimson = HoverButton()
        self.setup_btn(self.crimson, "Crimson_Lucidity_HD.png", "Crimson Boots (+20 Haste)")
        self.crimson.clicked.connect(self.on_crimson_clicked)
        self.layout.addWidget(self.crimson)

    def setup_btn(self, btn, icon_name, tooltip):
        btn.setCheckable(True)
        btn.setFixedSize(50, 50)
        btn.setToolTip(tooltip)
        icon_path = f"assets/images/{icon_name}"
        
        # CSS for hover and active state
        btn.setStyleSheet(f"""
            QPushButton {{
                border: 2px solid #333;
                border-radius: 5px;
                background: #111;
                image: url("{icon_path.replace('\\', '/')}");
                padding: 2px;
            }}
            QPushButton:hover {{
                border: 2px solid #C89B3C;
            }}
            QPushButton:checked {{
                border: 2px solid #00FF00;
                background: #222;
            }}
            QPushButton:checked:hover {{
                border: 2px solid #00FF00;
            }}
        """)

    def on_ionian_clicked(self):
        checked = self.ionian.isChecked()
        if checked:
            self.main_window.play_sound("button_1.wav")
        else:
            self.crimson.setChecked(False)
        self.update_haste()

    def on_crimson_clicked(self):
        if not self.ionian.isChecked():
            self.main_window.play_sound("beep-error.wav")
            self.crimson.setChecked(False)
            return
        
        checked = self.crimson.isChecked()
        if checked:
            self.main_window.play_sound("button_2.wav")
        self.update_haste()

    def update_haste(self):
        h = 0
        if self.crimson.isChecked(): h = 20
        elif self.ionian.isChecked(): h = 10
        self.main_window.role_haste[self.role] = h

class RoleColumn(QFrame):
    def __init__(self, role_name):
        super().__init__()
        self.role_name = role_name
        self.active_timers = {} # spell_name: SpellTimer
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignCenter)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("border: 1px solid #333; border-radius: 10px; background: #222;")
        
        # Role Header with Reset
        self.header_layout = QHBoxLayout()
        self.label = QLabel(self.role_name.upper())
        self.label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.label.setStyleSheet("color: #C89B3C; margin: 10px;")
        self.header_layout.addWidget(self.label)
        
        self.reset_btn = QPushButton("✕")
        self.reset_btn.setFixedSize(24, 24)
        self.reset_btn.setToolTip(f"Reset {self.role_name} timers")
        self.reset_btn.setStyleSheet("""
            QPushButton { 
                background: #333; color: #888; border-radius: 12px; font-weight: bold; border: 1px solid #444;
            } 
            QPushButton:hover { 
                background: #900; color: #fff; border: 1px solid #f00;
            }
        """)
        self.reset_btn.clicked.connect(self.clear_timers)
        self.header_layout.addWidget(self.reset_btn)
        
        self.layout.addLayout(self.header_layout)
        
        # Grid for spells (usually 2 per role in LoL)
        self.spells_layout = QVBoxLayout()
        self.layout.addLayout(self.spells_layout)
        
        self.spell_widgets = {}

    def setup_boot_checkbox(self, checkbox, icon_name, haste_val):
        pass # To be removed
        checkbox.setFixedSize(40, 40)
        path = f"assets/images/{icon_name}"
        if os.path.exists(path):
            pixmap = QPixmap(path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            checkbox.setStyleSheet(f"""
                QCheckBox::indicator {{ width: 32px; height: 32px; }}
                QCheckBox::indicator:unchecked {{ image: url({path.replace('\\', '/')}); opacity: 0.3; }}
                QCheckBox::indicator:checked {{ image: url({path.replace('\\', '/')}); opacity: 1.0; }}
            """)
        checkbox.stateChanged.connect(lambda s: self.on_boot_changed(checkbox, haste_val, s))

    def on_boot_changed(self, checkbox, haste_val, state):
        pass # To be removed

    def add_spell_widget(self, spell_name):
        spell_name = spell_name.lower()
        if spell_name in self.spell_widgets:
            return
            
        container = QWidget()
        layout = QVBoxLayout(container)
        
        img_label = QLabel()
        
        # Determine icon path (Teleport has two variants)
        img_name = f"{spell_name.capitalize()}_HD"
        if spell_name == "teleport" and self.window() and hasattr(self.window(), 'unleashed_check'):
             if self.window().unleashed_check.isChecked():
                 img_name = "Unleashed_Teleport_HD"
                 
        img_path = f"assets/images/{img_name}.png"
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            img_label.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        timer_label = QLabel("READY")
        timer_label.setFont(QFont("Digital-7", 24, QFont.Bold))
        timer_label.setStyleSheet("color: #00FF00;")
        timer_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(img_label)
        layout.addWidget(timer_label)
        
        self.spells_layout.addWidget(container)
        self.spell_widgets[spell_name] = {
            "img": img_label,
            "timer": timer_label,
            "opacity": QGraphicsOpacityEffect(img_label)
        }
        img_label.setGraphicsEffect(self.spell_widgets[spell_name]["opacity"])

    def is_timer_active(self, spell_name):
        return spell_name.lower() in self.active_timers and self.active_timers[spell_name.lower()].is_running

    def start_timer(self, spell_name, on_finished_callback, override_duration=None, is_debug=False, haste=0):
        spell_name = spell_name.lower()
        
        if self.is_timer_active(spell_name):
            return False # Already active
            
        # 2-Summoner Cap Check
        active_count = sum(1 for t in self.active_timers.values() if t.is_running)
        if active_count >= 2:
            return False # Cap reached
            
        if spell_name not in self.spell_widgets:
            self.add_spell_widget(spell_name)
            
        timer = SpellTimer(spell_name, 
                          callback_tick=lambda t: self.update_timer_ui(spell_name, t),
                          callback_finished=lambda: self.on_timer_finished(spell_name, on_finished_callback))
        
        if override_duration is not None:
            timer.base_cd = int(override_duration)
        elif haste > 0:
            # Formula: CD * (100 / (100 + Haste))
            timer.base_cd = int(timer.base_cd * (100 / (100 + haste)))
            
        self.active_timers[spell_name] = timer
        timer.start()
        
        # Update UI to "On CD" state
        self.spell_widgets[spell_name]["opacity"].setOpacity(0.3)
        
        color = "#A335EE" if is_debug else "#FF3333" # Purple for debug
        self.spell_widgets[spell_name]["timer"].setStyleSheet(f"color: {color};")
        return True

    def update_timer_ui(self, spell_name, remaining):
        mins = remaining // 60
        secs = remaining % 60
        self.spell_widgets[spell_name]["timer"].setText(f"{mins}:{secs:02d}")

    def on_timer_finished(self, spell_name, callback):
        self.spell_widgets[spell_name]["opacity"].setOpacity(1.0)
        self.spell_widgets[spell_name]["timer"].setText("READY")
        self.spell_widgets[spell_name]["timer"].setStyleSheet("color: #00FF00;")
        callback(self.role_name, spell_name)

    def update_spell_icon(self, spell_name, is_unleashed):
        if spell_name.lower() != "teleport" or spell_name.lower() not in self.spell_widgets:
            return
        
        variant = "Unleashed_Teleport_HD" if is_unleashed else "Teleport_HD"
        img_path = f"assets/images/{variant}.png"
        
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            self.spell_widgets[spell_name.lower()]["img"].setPixmap(
                pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def clear_timers(self):
        # 1. Internal logic reset
        for timer in self.active_timers.values():
            timer.is_running = False
        self.active_timers.clear()
        
        # 2. Visual reset: Remove all spell widgets
        while self.spells_layout.count():
            item = self.spells_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        self.spell_widgets.clear()
            
        # 3. Flash effect
        self.setStyleSheet("border: 2px solid white; border-radius: 10px; background: #666;")
        QTimer.singleShot(150, lambda: self.setStyleSheet("border: 1px solid #333; border-radius: 10px; background: #222;"))

    def tick(self):
        for timer in list(self.active_timers.values()):
            timer.tick()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Barrel Timer - Gragas Edition")
        self.setMinimumSize(1300, 1200)
        self.setStyleSheet("""
            QMainWindow { background-color: #0F0F0F; color: #F0E6D2; }
            QToolTip { 
                background-color: #1a1a1a; 
                color: #C89B3C; 
                border: 1px solid #C89B3C; 
                font-size: 18px; 
                font-weight: bold;
                padding: 5px;
            }
        """)
        
        icon_path = "assets/images/gragas_barrel_timer.png"
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        pygame.mixer.init()
        self.config = ConfigManager.load_config()
        self.sound_queue = queue.Queue()
        self.is_playing_sound = False
        self.role_haste = {r: 0 for r in ["top", "jungler", "mid", "adc", "support"]}
        self.game_time = 0
        self.game_timer_running = False
        
        self.init_ui()
        self.init_voice_engine()
        
        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.global_tick)
        self.master_timer.start(1000)
        
        # Audio Queue Processor
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.process_audio_queue)
        self.queue_timer.start(100)

        self.play_sound("welcome.wav")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Wallpaper Background with 80% Opacity Overlay
        bg_path = "assets/images/background_0.jpg"
        if os.path.exists(bg_path):
             central_widget.setObjectName("central_widget")
             central_widget.setStyleSheet(f"""
                #central_widget {{
                    background-image: url("{bg_path.replace('\\', '/')}");
                    background-position: center;
                    background-repeat: no-repeat;
                }}
             """)

        # Main container with dark overlay (simulating 80% transparency/darkening)
        self.overlay = QWidget(central_widget)
        self.overlay.setStyleSheet("background: rgba(10, 10, 10, 220);")
        
        # Ensure overlay covers central_widget
        overlay_layout = QVBoxLayout(central_widget)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addWidget(self.overlay)
        
        self.main_layout = QVBoxLayout(self.overlay)
               # Header with centered title
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)

        # Left: Controls
        left_box = QWidget()
        left_box.setFixedWidth(550) # Balanced with right_box for centering
        left_layout = QVBoxLayout(left_box)
        mic_label = QLabel("MICROPHONE:")
        mic_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        mic_label.setStyleSheet("color: #C89B3C;")
        left_layout.addWidget(mic_label)
        
        mic_row = QHBoxLayout()
        # Mic Icon (Gracioso style - moved to mic_row, now GIF)
        self.mic_icon = QLabel()
        self.mic_icon.setFixedSize(50, 80)
        mic_gif_path = "assets/images/gragas_micro.gif"
        if os.path.exists(mic_gif_path):
            self.mic_movie = QMovie(mic_gif_path)
            self.mic_movie.setScaledSize(self.mic_icon.size())
            self.mic_icon.setMovie(self.mic_movie)
            self.mic_movie.start()
        mic_row.addWidget(self.mic_icon)
        
        self.mic_select = QComboBox()
        self.populate_mics()
        self.mic_select.setCurrentIndex(self.get_mic_index_from_config())
        self.mic_select.currentIndexChanged.connect(self.on_mic_changed)
        self.mic_select.setStyleSheet("background: #222; border: 1px solid #C89B3C;")
        mic_row.addWidget(self.mic_select)
        self.listening_indicator = QLabel("● Listening Active")
        self.listening_indicator.setStyleSheet("color: #00FF00; font-weight: bold;")
        mic_row.addWidget(self.listening_indicator)
        
        self.mute_btn = QPushButton("MUTE")
        self.mute_btn.setCheckable(True)
        self.mute_btn.toggled.connect(self.on_mute_toggled)
        self.mute_btn.setStyleSheet("QPushButton { background: #444; } QPushButton:checked { background: #900; }")
        mic_row.addWidget(self.mute_btn)
        left_layout.addLayout(mic_row)
        header_layout.addWidget(left_box)

        header_layout.addStretch()

        # Center: Branding (with background logo)
        title_container = QWidget()
        title_container.setFixedSize(600, 200)
        bg_logo_path = "assets/images/barrel_0.png"
        if os.path.exists(bg_logo_path):
            title_container.setStyleSheet(f"""
                QWidget {{
                    background-image: url("{bg_logo_path.replace('\\', '/')}");
                    background-position: center;
                    background-repeat: no-repeat;
                }}
            """)
        
        title_vbox = QVBoxLayout(title_container)
        title_vbox.setAlignment(Qt.AlignCenter)
        
        self.brand_label = QLabel("BARREL TIMER")
        self.brand_label.setFont(QFont("Impact", 48))
        self.brand_label.setStyleSheet("color: #C89B3C; background: transparent; margin-bottom: 0px;")
        self.brand_label.setAlignment(Qt.AlignCenter)
        title_vbox.addWidget(self.brand_label)
        
        self.sub_brand_label = QLabel("by Rener - v1.9.4-alpha")
        self.sub_brand_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.sub_brand_label.setStyleSheet("color: #00FF00; background: transparent;")
        self.sub_brand_label.setAlignment(Qt.AlignCenter)
        title_vbox.addWidget(self.sub_brand_label)
        
        header_layout.addWidget(title_container)

        header_layout.addStretch()

        # Right: Logo & Unleashed
        right_box = QWidget()
        right_box.setFixedWidth(550) # Increased to fit bubble
        right_layout = QVBoxLayout(right_box)
        
        logo_row = QHBoxLayout()
        logo_row.setAlignment(Qt.AlignRight)
        
        self.speech_bubble = SpeechBubble()
        logo_row.addWidget(self.speech_bubble)

        self.logo_label = QLabel()
        self.logo_label.setFixedSize(160, 160)
        self.logo_label.setAlignment(Qt.AlignCenter)
        
        # Idle Movie (GIF)
        idle_path = "assets/images/gragas_idle.gif"
        self.idle_movie = None
        if os.path.exists(idle_path):
            self.idle_movie = QMovie(idle_path)
            self.idle_movie.setScaledSize(self.logo_label.size())
            self.logo_label.setMovie(self.idle_movie)
            self.idle_movie.start()
        else:
            # Fallback to static if idle.gif doesn't exist
            logo_path = "assets/images/gragas_barrel_timer.png"
            if os.path.exists(logo_path):
                self.static_pixmap = QPixmap(logo_path).scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.logo_label.setPixmap(self.static_pixmap)
        
        # Speaking Movie (GIF)
        gif_path = "assets/images/gragas_barrel_timer_speaking.gif"
        self.speaking_movie = None
        if os.path.exists(gif_path):
            self.speaking_movie = QMovie(gif_path)
            self.speaking_movie.setScaledSize(self.logo_label.size())
            
        logo_row.addWidget(self.logo_label)
        right_layout.addLayout(logo_row)
        
        # Shake Animation setup
        self.shake_anim = QPropertyAnimation(self.logo_label, b"pos")
        self.shake_anim.setDuration(50)
        self.shake_anim.setLoopCount(-1)
        
        # Unleashed TP Toggle Area
        tp_area = QHBoxLayout()
        tp_area.setAlignment(Qt.AlignRight)
        
        tp_icon_label = QLabel()
        tp_icon_path = "assets/images/Unleashed_Teleport_HD.png"
        if os.path.exists(tp_icon_path):
            pixmap = QPixmap(tp_icon_path)
            tp_icon_label.setPixmap(pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        tp_area.addWidget(tp_icon_label)

        self.unleashed_check = QCheckBox("Min 10+? (Unleashed TP CD)")
        self.unleashed_check.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.unleashed_check.setStyleSheet("color: #C89B3C; padding: 5px; border: 1px solid #C89B3C; border-radius: 5px; background: #1a1a1a;")
        self.unleashed_check.stateChanged.connect(self.on_unleashed_changed)
        tp_area.addWidget(self.unleashed_check)
        
        right_layout.addLayout(tp_area)

        # Game Chrono (Repositioned under Gragas Logo)
        chrono_box = QWidget()
        chrono_hbox = QHBoxLayout(chrono_box)
        chrono_hbox.setAlignment(Qt.AlignRight)
        chrono_hbox.setContentsMargins(0, 5, 0, 0)

        self.chrono_widget = QWidget()
        self.chrono_widget.setFixedSize(180, 80)
        bg_path = "assets/images/clock_bg.png"
        self.chrono_widget.setStyleSheet(f"""
            QWidget {{
                background-image: url("{bg_path.replace('\\', '/')}");
                background-position: center;
                background-repeat: no-repeat;
            }}
        """)
        
        chrono_inner_layout = QVBoxLayout(self.chrono_widget)
        chrono_inner_layout.setAlignment(Qt.AlignCenter)
        chrono_inner_layout.setContentsMargins(0, 0, 0, 0)
        
        self.chrono_label = QLabel("00:00")
        self.chrono_label.setFont(QFont("Segoe UI", 28, QFont.Bold))
        self.chrono_label.setStyleSheet("color: #C89B3C; background: transparent;")
        self.chrono_label.setAlignment(Qt.AlignCenter)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(5)
        shadow.setXOffset(2)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.chrono_label.setGraphicsEffect(shadow)
        chrono_inner_layout.addWidget(self.chrono_label)
        
        # Adjustment Buttons (Corners)
        btn_style = """
            QPushButton { 
                background: rgba(0,0,0,150); color: #C89B3C; border: 1px solid #C89B3C; border-radius: 12px; font-weight: bold; 
            } 
            QPushButton:hover { background: #C89B3C; color: #000; }
        """
        self.minus_10_btn = HoverButton("➖", self.chrono_widget)
        self.minus_10_btn.setFixedSize(24, 24)
        self.minus_10_btn.move(10, 50)
        self.minus_10_btn.setStyleSheet(btn_style)
        self.minus_10_btn.setToolTip("Shift + Click to fast decrease (-60s)")
        self.minus_10_btn.clicked.connect(self.on_minus_clicked)
        
        self.plus_10_btn = HoverButton("➕", self.chrono_widget)
        self.plus_10_btn.setFixedSize(24, 24)
        self.plus_10_btn.move(146, 50)
        self.plus_10_btn.setStyleSheet(btn_style)
        self.plus_10_btn.setToolTip("Shift + Click to fast increase (+60s)")
        self.plus_10_btn.clicked.connect(self.on_plus_clicked)
        
        chrono_hbox.addWidget(self.chrono_widget)
        
        # Start/Pause & Reset Buttons
        controls_vbox = QVBoxLayout()
        controls_vbox.setSpacing(5)
        
        self.start_game_btn = QPushButton("START GAME")
        self.start_game_btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.start_game_btn.setFixedSize(110, 35)
        self.start_game_btn.setStyleSheet("QPushButton { background: #111; color: #00FF00; border: 2px solid #00FF00; border-radius: 5px; } QPushButton:hover { background: #004400; }")
        self.start_game_btn.clicked.connect(self.toggle_game_timer)
        controls_vbox.addWidget(self.start_game_btn)

        self.reset_game_btn = QPushButton("RESET")
        self.reset_game_btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.reset_game_btn.setFixedSize(110, 35)
        self.reset_game_btn.setStyleSheet("QPushButton { background: #111; color: #C89B3C; border: 2px solid #C89B3C; border-radius: 5px; } QPushButton:hover { background: #900; color: #fff; border: 2px solid #f00; }")
        self.reset_game_btn.clicked.connect(self.reset_game_timer)
        controls_vbox.addWidget(self.reset_game_btn)
        
        chrono_hbox.addLayout(controls_vbox)
        right_layout.addWidget(chrono_box)
        
        header_layout.addWidget(right_box)
        self.main_layout.addWidget(header_widget)

        # Voice Set Row (Compact)
        settings_row = QHBoxLayout()
        settings_row.setContentsMargins(50, 0, 50, 5)
        v_label = QLabel("VOICE SET:")
        v_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        settings_row.addWidget(v_label)
        self.version_select = QComboBox()
        self.version_select.addItems(["v1", "v2"])
        self.version_select.setCurrentText(self.config.get("voice_set", "v1"))
        self.version_select.setStyleSheet("background: #333; border: 1px solid #C89B3C;")
        self.version_select.currentTextChanged.connect(self.on_version_changed)
        settings_row.addWidget(self.version_select)
        
        settings_row.addSpacing(30)
        
        vol_label = QLabel("VOL:")
        vol_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        settings_row.addWidget(vol_label)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.config.get("volume", 98)))
        self.volume_slider.setFixedWidth(150)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #C89B3C; height: 8px; background: #222; margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: #C89B3C; border: 1px solid #C89B3C; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
        """)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        settings_row.addWidget(self.volume_slider)
        
        settings_row.addStretch()
        self.main_layout.addLayout(settings_row)

        # Centered Debug Subtitle
        self.debug_subtitle = QLabel("[ DEBUG MODE ACTIVE ]")
        self.debug_subtitle.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.debug_subtitle.setStyleSheet("color: #A020F0; margin: 5px;")
        self.debug_subtitle.setAlignment(Qt.AlignCenter)
        self.debug_subtitle.setVisible(self.config.get("debug_mode", False))
        self.main_layout.addWidget(self.debug_subtitle)

        # Boots Row (Above cards)
        self.boots_row = QHBoxLayout()
        self.boots_row.setContentsMargins(20, 0, 20, 0)
        self.role_boot_widgets = {}
        for role in ["top", "jungler", "mid", "adc", "support"]:
            container = BootControl(role, self)
            self.boots_row.addWidget(container)
            self.role_boot_widgets[role] = container
        self.main_layout.addLayout(self.boots_row)
        
        # 5 Columns
        self.columns_layout = QHBoxLayout()
        roles = ["top", "jungler", "mid", "adc", "support"]
        self.role_widgets = {}
        for role in roles:
            col = RoleColumn(role)
            self.columns_layout.addWidget(col)
            self.role_widgets[role] = col
            
        self.main_layout.addLayout(self.columns_layout)


        
        # Voice Console (Input Preview)
        self.console_container = QWidget()
        self.console_layout = QHBoxLayout(self.console_container)
        self.voice_console = QLabel("Last heard: ...")
        self.voice_console.setFont(QFont("Consolas", 10))
        self.voice_console.setStyleSheet("color: #666; background: #1a1a1a; padding: 5px 15px; border-radius: 5px;")
        self.voice_console.setAlignment(Qt.AlignCenter)
        self.voice_console.setFixedWidth(400)
        self.console_layout.addWidget(self.voice_console)
        self.main_layout.addWidget(self.console_container, alignment=Qt.AlignCenter)
        
        # Fade Timer for Voice Console
        self.console_timer = QTimer(self)
        self.console_timer.setSingleShot(True)
        self.console_timer.timeout.connect(self.hide_voice_console)
        
        # Footer / Status
        self.status_label = QLabel("Ready for commands (e.g., 'Mid Flash')")
        self.status_label.setStyleSheet("color: #888; font-style: italic; padding: 10px;")
        
        footer_layout = QHBoxLayout()
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        
        # Debug Controls - Moved here (Bottom Right)
        debug_container = QHBoxLayout()
        debug_label = QLabel("DEBUG:")
        debug_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
        debug_container.addWidget(debug_label)
        
        self.debug_check = QCheckBox()
        self.debug_check.setChecked(self.config.get("debug_mode", False))
        self.debug_check.stateChanged.connect(self.on_debug_changed)
        debug_container.addWidget(self.debug_check)
        
        self.debug_spin = QSpinBox()
        self.debug_spin.setRange(1, 600)
        self.debug_spin.setValue(self.config.get("debug_duration", 5))
        self.debug_spin.setSuffix("s")
        self.debug_spin.setFixedWidth(60)
        self.debug_spin.valueChanged.connect(self.on_debug_duration_changed)
        debug_container.addWidget(self.debug_spin)
        footer_layout.addLayout(debug_container)
        
        patch_label = QLabel("LOL Patch 26.5")
        patch_label.setStyleSheet("color: #555; font-size: 10px; margin-left: 20px; margin-right: 20px;")
        footer_layout.addWidget(patch_label)
        
        self.main_layout.addLayout(footer_layout)

    def populate_mics(self):
        p = pyaudio.PyAudio()
        info = p.get_host_api_info_by_index(0)
        num_devices = info.get('deviceCount')
        for i in range(0, num_devices):
            if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                name = p.get_device_info_by_host_api_device_index(0, i).get('name')
                self.mic_select.addItem(name, i)
        p.terminate()

    def get_mic_index_from_config(self):
        stored_idx = self.config.get("microphone_index")
        if stored_idx is None: return 0
        for i in range(self.mic_select.count()):
            if self.mic_select.itemData(i) == stored_idx:
                return i
        return 0

    def init_voice_engine(self):
        model_path = os.path.join("models", "vosk-model-small-en-us-0.15")
        mic_idx = self.config.get("microphone_index")
        self.voice_thread = VoiceEngine(model_path, mic_index=mic_idx)
        self.voice_thread.command_detected.connect(self.on_command_detected)
        self.voice_thread.status_updated.connect(self.update_status)
        self.voice_thread.text_detected.connect(self.update_voice_console)
        self.voice_thread.start()

    def update_voice_console(self, text):
        self.voice_console.setText(f"Last heard: {text}")
        self.voice_console.setStyleSheet("color: #AAA; background: #222; padding: 5px 15px; border-radius: 5px; border: 1px solid #444;")
        self.console_timer.start(3000)

    def hide_voice_console(self):
        self.voice_console.setStyleSheet("color: #444; background: #1a1a1a; padding: 5px 15px; border-radius: 5px; border: none;")
        self.voice_console.setText("Last heard: ...")

    @Slot(bool)
    def on_mute_toggled(self, checked):
        self.voice_thread.set_muted(checked)
        if checked:
            self.listening_indicator.setText("● Muted")
            self.listening_indicator.setStyleSheet("color: #FF3333; font-weight: bold;")
        else:
            self.listening_indicator.setText("● Listening Active")
            self.listening_indicator.setStyleSheet("color: #00FF00; font-weight: bold;")

    def on_mic_changed(self, index):
        mic_idx = self.mic_select.itemData(index)
        self.config["microphone_index"] = mic_idx
        self.voice_thread.set_microphone(mic_idx)
        ConfigManager.save_config(self.config)

    @Slot(str, str)
    def on_command_detected(self, role, spell):
        if role in self.role_widgets:
            # Handle Debug Mode
            is_debug = self.debug_check.isChecked()
            
            # Smite Exclusivity Check
            if spell.lower() == "smite" and role.lower() != "jungler":
                self.play_sound("beep-error.wav")
                self.update_status(f"Error: Smite is exclusive to Jungler!")
                return

            timer_duration = int(self.debug_spin.value()) if is_debug else None
            
            # Unleashed Teleport Logic
            if not is_debug and spell.lower() == "teleport":
                timer_duration = 240 if self.unleashed_check.isChecked() else 360
            
            # Get haste from centralized widgets
            haste = self.role_haste.get(role.lower(), 0)
            
            started = self.role_widgets[role].start_timer(spell, self.on_timer_ready, 
                                                       override_duration=timer_duration, 
                                                       is_debug=is_debug,
                                                       haste=haste)
            
            if started:
                self.play_sound("beep.wav")
                haste_info = " [Botas Activas]" if haste > 0 else ""
                status = f"Tracking: {role} {spell}{haste_info}"
                if is_debug: status += " (in debug mode)"
                self.update_status(status)
            else:
                self.play_sound("beep-error.wav")
                # Could be already active or cap reached
                active_count = sum(1 for t in self.role_widgets[role].active_timers.values() if t.is_running)
                if active_count >= 2:
                    msg = f"Error: {role} already has 2 summoners active!"
                else:
                    msg = f"Error: {role} {spell} is already active!"
                self.update_status(msg)

        elif role == "game" and spell == "start":
            if self.game_timer_running:
                self.play_sound("beep-error.wav")
                self.update_status("Game already started!")
            else:
                self.start_game_timer()
                self.play_sound("beep.wav")
                self.update_status("Game Clock Started!")

    def on_timer_ready(self, role, spell):
        sound_file = f"{role}_{spell}_ready.wav"
        self.sound_queue.put(sound_file)

    def start_gragas_speaking(self, duration_ms):
        if self.idle_movie:
            self.idle_movie.stop()
            
        if self.speaking_movie:
            self.logo_label.setMovie(self.speaking_movie)
            self.speaking_movie.start()
        
        # Shake effect logic
        origin = self.logo_label.pos()
        self.shake_origin = QPoint(origin.x(), origin.y())
        
        self.shake_anim.setStartValue(self.shake_origin)
        # Fix: PySide6 requires a sequence of tuples [(progress, value), ...]
        self.shake_anim.setKeyValues([
            (0.2, self.shake_origin + QPoint(2, -2)),
            (0.4, self.shake_origin + QPoint(-2, 2)),
            (0.6, self.shake_origin + QPoint(1, -1)),
            (0.8, self.shake_origin + QPoint(-1, 1)),
            (1.0, self.shake_origin)
        ])
        self.shake_anim.start()
        
        # Manually stop after duration
        QTimer.singleShot(duration_ms, self.stop_gragas_speaking)

    def stop_gragas_speaking(self):
        if self.speaking_movie:
            self.speaking_movie.stop()
            
        if self.idle_movie:
            self.logo_label.setMovie(self.idle_movie)
            self.idle_movie.start()
        elif hasattr(self, 'static_pixmap'):
            self.logo_label.setMovie(None)
            self.logo_label.setPixmap(self.static_pixmap)
        
        self.shake_anim.stop()
        if hasattr(self, 'shake_origin'):
            self.logo_label.move(self.shake_origin)
        
        # Important: Allow next sound in queue
        self.is_playing_sound = False

    def set_gragas_speech(self, text, duration_ms=3000):
        self.speech_bubble.setText(text)
        self.speech_bubble.show()
        
        # Adjust duration if text is very long
        actual_duration = max(duration_ms, len(text) * 50)
        
        QTimer.singleShot(actual_duration, self.speech_bubble.hide)


    def on_plus_clicked(self):
        amount = 60 if QApplication.keyboardModifiers() & Qt.ShiftModifier else 10
        self.adjust_game_timer(amount)

    def on_minus_clicked(self):
        amount = -60 if QApplication.keyboardModifiers() & Qt.ShiftModifier else -10
        self.adjust_game_timer(amount)

    def process_audio_queue(self):
        if not self.is_playing_sound and not self.sound_queue.empty():
            filename = self.sound_queue.get()
            self.play_sound_sync(filename)

    def play_sound_sync(self, filename):
        voice_set = self.config.get("voice_set", "v1")
        is_immediate = filename in ["beep.wav", "beep-error.wav", "button_1.wav", "button_2.wav"]
        
        if is_immediate:
            path = os.path.join("assets", "sounds", filename)
        else:
            if filename == "jungler_heal_ready.wav":
                alt_path = os.path.join(ConfigManager.get_voice_set_path(voice_set), "jungle_heal_ready.wav")
                if os.path.exists(alt_path):
                    filename = "jungle_heal_ready.wav"
            path = os.path.join(ConfigManager.get_voice_set_path(voice_set), filename)
            
        if os.path.exists(path):
            try:
                sound = pygame.mixer.Sound(path)
                # Apply master volume from config (0-100 -> 0.0-1.0)
                vol = self.volume_slider.value() / 100.0 if hasattr(self, 'volume_slider') else (self.config.get("volume", 70) / 100.0 / 1.42)
                sound.set_volume(vol)
                sound.play()
                
                if not is_immediate:
                    self.is_playing_sound = True
                    # Sync animation with sound duration
                    duration_ms = int(sound.get_length() * 1000) + 200
                    self.start_gragas_speaking(duration_ms)
                    
                    # Speech Bubble Integration
                    speech_text = None
                    if filename == "welcome.wav":
                        speech_text = "Hey! Listening and ready!"
                    elif "ready.wav" in filename:
                        if filename == "unleashed_teleports_ready.wav":
                            speech_text = "Teleports are Unleashed! Time for a gank!"
                        else:
                            # e.g. top_flash_ready.wav -> "TOP FLASH Ready!"
                            parts = filename.replace("_ready.wav", "").split("_")
                            if len(parts) >= 2:
                                role_name = parts[0].upper()
                                spell_name = parts[1].upper()
                                speech_text = f"{role_name} {spell_name} Ready!"
                    
                    if speech_text:
                        self.set_gragas_speech(speech_text, duration_ms)
                else:
                    self.is_playing_sound = False
            except Exception as e:
                print(f"Error playing sound {path}: {e}")
                self.is_playing_sound = False
        else:
            print(f"Sound not found: {path}")
            self.is_playing_sound = False

    def play_sound(self, filename):
        # Immediate sounds skip the queue
        if filename in ["beep.wav", "beep-error.wav", "button_1.wav", "button_2.wav"]:
            path = os.path.join("assets", "sounds", filename)
            if os.path.exists(path):
                sound = pygame.mixer.Sound(path)
                vol = self.volume_slider.value() / 100.0 if hasattr(self, 'volume_slider') else (self.config.get("volume", 70) / 100.0 / 1.42)
                sound.set_volume(vol)
                sound.play()
            return
        self.sound_queue.put(filename)

    def global_tick(self):
        active_list = []
        is_debug = self.debug_check.isChecked()
        for role, col in self.role_widgets.items():
            col.tick()
            haste = self.role_haste.get(role.lower(), 0)
            for spell, timer in col.active_timers.items():
                if timer.is_running:
                    haste_tag = " [Botas]" if haste > 0 else ""
                    active_list.append(f"[{role.capitalize()} {spell.capitalize()}{haste_tag}: {timer.remaining_time}s]")
        
        if active_list:
            status = "Tracking: " + " | ".join(active_list)
            if is_debug: status += " [DEBUG ACTIVE]"
            self.status_label.setText(status)
        else:
            status = "Ready for commands (e.g., 'Mid Flash')"
            if is_debug: status += " [DEBUG ACTIVE]"
            self.status_label.setText(status)

        # Game Timer Logic
        if self.game_timer_running:
            self.game_time += 1
            self.update_chrono_ui()
            
            # Unleashed Check at 10:00 (600s)
            if self.game_time == 600:
                if not self.unleashed_check.isChecked():
                    self.unleashed_check.setChecked(True)
                    self.trigger_unleashed_event()

    def update_chrono_ui(self):
        mins = self.game_time // 60
        secs = self.game_time % 60
        self.chrono_label.setText(f"{mins:02d}:{secs:02d}")

    def toggle_game_timer(self):
        if self.game_timer_running:
            self.game_timer_running = False
            self.start_game_btn.setText("RESUME GAME")
            self.start_game_btn.setStyleSheet("QPushButton { background: #111; color: #C89B3C; border: 2px solid #C89B3C; padding: 10px; border-radius: 5px; }")
        else:
            self.start_game_timer()

    def start_game_timer(self):
        self.game_timer_running = True
        self.start_game_btn.setText("PAUSE GAME")
        self.start_game_btn.setStyleSheet("QPushButton { background: #111; color: #FF3333; border: 2px solid #FF3333; padding: 10px; border-radius: 5px; }")

    def reset_game_timer(self):
        self.game_time = 0
        self.game_timer_running = False
        self.update_chrono_ui()
        self.start_game_btn.setText("START GAME")
        self.unleashed_check.setChecked(False)
        self.start_game_btn.setStyleSheet("QPushButton { background: #111; color: #00FF00; border: 2px solid #00FF00; padding: 10px; border-radius: 5px; }")
        self.play_sound("button_1.wav")

    def adjust_game_timer(self, seconds):
        self.game_time = max(0, self.game_time + seconds)
        self.update_chrono_ui()
        # Handle case where user skips past 10:00
        if self.game_time >= 600 and not self.unleashed_check.isChecked():
             self.unleashed_check.setChecked(True)
             self.trigger_unleashed_event()

    def trigger_unleashed_event(self):
        # Golden Glow effect
        self.chrono_label.setStyleSheet("color: #FFD700; background: #000; border: 3px solid #FFD700; border-radius: 10px; padding: 10px;")
        QTimer.singleShot(2000, lambda: self.chrono_label.setStyleSheet("color: #FFFFFF; background: #000; border: 2px solid #333; border-radius: 10px; padding: 10px;"))
        
        # Audio/Animation logic removed play_sound as it is redundant (on_unleashed_changed plays it)
        self.update_status("TELEPORT UNLEASHED!")

    def update_status(self, text):
        self.status_label.setText(text)

    def on_version_changed(self, version):
        self.config["voice_set"] = version
        ConfigManager.save_config(self.config)

    def on_debug_changed(self, state):
        is_active = (state == 2) # Qt.Checked is 2 in PySide6
        self.config["debug_mode"] = is_active
        self.debug_subtitle.setVisible(is_active)
        ConfigManager.save_config(self.config)

    def on_debug_duration_changed(self, val):
        self.config["debug_duration"] = val
        ConfigManager.save_config(self.config)

    def on_unleashed_changed(self, state):
        is_on = (state == 2) # Qt.Checked
        for col in self.role_widgets.values():
            col.update_spell_icon("teleport", is_on)
        
        status = "Teleport Evolved! (240s)" if is_on else "Teleport Standard (360s)"
        self.update_status(status)
        if is_on:
            self.play_sound("unleashed_teleports_ready.wav")
        else:
            self.play_sound("button_2.wav")

    def on_volume_changed(self, value):
        self.config["volume"] = value
        ConfigManager.save_config(self.config)
        # Apply volume (scaled 0.0-1.0) for subsequent sounds
        pass

    def closeEvent(self, event):
        self.voice_thread.stop()
        pygame.mixer.quit()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
