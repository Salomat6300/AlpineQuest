import tkinter as tk
from tkinter import ttk, messagebox
from ttkbootstrap import Style
from PIL import Image, ImageTk
import cv2
import face_recognition
import numpy as np
from datetime import datetime
import threading
import queue
import io
import os
import psycopg2
from psycopg2 import sql
import mediapipe as mp

# Database Class
class FaceDB:
    def __init__(self, dbname, user, password, host, port):
        self.dbname = dbname
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.connection = None

    def ulanish(self):
        try:
            self.connection = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            return True
        except Exception as e:
            print(f"Bazaga ulanib bolmadi: {e}")
            return False

    def ulanishni_yopish(self):
        if self.connection:
            self.connection.close()

    def jadvallarni_yaratish(self):
        if not self.ulanish():
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS face_data (
                    id SERIAL PRIMARY KEY,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    img BYTEA NOT NULL,
                    encoding FLOAT[128] NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS face_log_data (
                    id SERIAL PRIMARY KEY,
                    id_name INTEGER REFERENCES face_data(id),
                    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            self.connection.commit()
            print("Jadvallar yaratildi.")
            return True
        except Exception as e:
            print(f"Xatolik: {e}")
            return False
        finally:
            self.ulanishni_yopish()

    def yuz_qoshish(self, yuz_rasmi, yuz_kodi):
        if not self.ulanish():
            return None
        try:
            cursor = self.connection.cursor()
            _, buffer = cv2.imencode(".jpg", yuz_rasmi)
            io_buf = io.BytesIO(buffer)
            kod_royxati = yuz_kodi.tolist()
            cursor.execute(
                sql.SQL("""
                    INSERT INTO face_data (img, encoding, first_name, last_name)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """),
                (io_buf.read(), kod_royxati, "Aniqlanmagan!", "Aniqlanmagan!")
            )
            yuz_id = cursor.fetchone()[0]
            cursor.execute(
                sql.SQL("INSERT INTO face_log_data (id_name) VALUES (%s)"),
                (yuz_id,)
            )
            self.connection.commit()
            return yuz_id
        except Exception as e:
            print(f"Yuz qoshishda xatolik: {e}")
            return None
        finally:
            self.ulanishni_yopish()


    def get_user_details(self, user_id):
        """Foydalanuvchi ma'lumotlarini olish"""
        if not self.ulanish():
            return None
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT first_name, last_name, created_at FROM face_data WHERE id = %s",
                    (user_id,)
                )
                result = cursor.fetchone()
                if result:
                    return {
                        'ism': result[0] or "Mavjud emas",
                        'familiya': result[1] or "Mavjud emas",
                        'created_at': result[2].strftime("%Y-%m-%d %H:%M:%S") if result[2] else "Mavjud emas"
                    }
        except Exception as e:
            print("Foydalanuvchi ma'lumotlarini olishda xatolik:", e)
        
        return None

    def barcha_yuzlarni_olish(self):
        if not self.ulanish():
            return [], []
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, encoding FROM face_data")
            qatorlar = cursor.fetchall()
            yuz_ids = []
            yuz_kodlari = []
            for qator in qatorlar:
                yuz_ids.append(qator[0])
                yuz_kodlari.append(np.array(qator[1]))
            return yuz_ids, yuz_kodlari
        except Exception as e:
            print(f"Xatolik: {e}")
            return [], []
        finally:
            self.ulanishni_yopish()

    def kirishni_loglash(self, yuz_id):
        if not self.ulanish():
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                sql.SQL("INSERT INTO face_log_data (id_name) VALUES (%s)"),
                (yuz_id,)
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Log yozishda xatolik: {e}")
            return False
        finally:
            self.ulanishni_yopish()

    def foydalanuvchi_malumotlari(self):
        if not self.ulanish():
            return []
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT 
                    fd.id,
                    fd.first_name,
                    fd.last_name,
                    to_char(fd.created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at,
                    to_char(MAX(fl.entry_time), 'YYYY-MM-DD HH24:MI:SS') as last_entry
                FROM face_data fd
                LEFT JOIN face_log_data fl ON fd.id = fl.id_name
                GROUP BY fd.id, fd.created_at
                ORDER BY fd.id DESC
            """)
            rows = cursor.fetchall()
            return rows
        except Exception as e:
            print(f"Xatolik: {e}")
            return []
        finally:
            self.ulanishni_yopish()

    def update_user_info(self, user_id, ism, familiya):
        """Foydalanuvchi ism va familiyasini yangilash"""
        if not self.ulanish():
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE face_data SET first_name = %s, last_name = %s WHERE id = %s",
                (ism, familiya, user_id)
            )
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Ma'lumotlarni yangilashda xatolik: {e}")
            self.connection.rollback()
            return False

    def foydalanuvchini_ochirish(self, face_id):
        if not self.ulanish():
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM face_log_data WHERE id_name = %s", (face_id,))
            cursor.execute("DELETE FROM face_data WHERE id = %s", (face_id,))
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Xatolik: {e}")
            return False
        finally:
            self.ulanishni_yopish()

    def get_user_image(self, face_id):
        if not self.ulanish():
            return None
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT img FROM face_data WHERE id = %s", (face_id,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"Xatolik: {e}")
            return None
        finally:
            self.ulanishni_yopish()

# Face Orientation Detector
class FaceOrientationDetector:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=True)

    def detect(self, frame):
        h, w, _ = frame.shape
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(frame_rgb)

        if not results.multi_face_landmarks:
            return False

        landmarks = results.multi_face_landmarks[0].landmark

        left_eye = landmarks[33]
        right_eye = landmarks[263]
        nose = landmarks[1]

        left_eye_x = left_eye.x * w
        right_eye_x = right_eye.x * w
        left_eye_y = left_eye.y * h
        right_eye_y = right_eye.y * h
        nose_x = nose.x * w
        nose_y = nose.y * h

        eye_width = abs(right_eye_x - left_eye_x)
        eye_x_center = (left_eye_x + right_eye_x) / 2
        nose_x_offset = abs(nose_x - eye_x_center)
        yaw_ok = nose_x_offset < eye_width * 0.08

        eye_y_avg = (left_eye_y + right_eye_y) / 2
        vertical_dist = abs(nose_y - eye_y_avg)
        vertical_ratio = vertical_dist / eye_width
        pitch_ok = 0.3 < vertical_ratio < 0.6

        return yaw_ok and pitch_ok

# Login Window
class LoginWindow:
    def __init__(self, parent, on_success_callback):
        self.parent = parent
        self.on_success = on_success_callback
        self.window = tk.Toplevel(parent)
        self.window.title("Tizimga kirish")
        self.window.resizable(False, False)

        # Set window icon
        try:
            self.window.iconbitmap('face.ico')
        except:
            pass

        # Styling
        self.style = Style(theme='morph')
        self.window.configure(bg=self.style.colors.bg)

        #login page ni elementlarini joylashtirish
        main_frame = ttk.Frame(self.window,padding=(30, 30))
        main_frame.pack(padx=10, pady=10)

        # Logo
        try:
            logo_img = Image.open('assets/logo.png')
            logo_img = logo_img.resize((100, 100), Image.LANCZOS)
            self.logo = ImageTk.PhotoImage(logo_img)
            ttk.Label(main_frame, image=self.logo).pack(pady=(0, 20))
        except:
            ttk.Label(
                main_frame, 
                text="🔒", 
                font=('Helvetica', 48), 
                foreground=self.style.colors.primary
            ).pack(pady=(0, 20))

        # Title
        ttk.Label(
            main_frame, 
            text="Tizimga kirish", 
            font=('Helvetica', 16, 'bold'),
            foreground=self.style.colors.primary
        ).pack(pady=(0, 20))

        # Login form
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(fill=tk.X, pady=10)

        # Username
        ttk.Label(form_frame, text="Login:", font=('Helvetica', 11), foreground=self.style.colors.primary).pack(anchor=tk.W, pady=(5, 0))
        self.username_entry = ttk.Entry(form_frame, foreground=self.style.colors.primary, font=('Helvetica', 11))
        self.username_entry.pack(fill=tk.X, pady=5)
        self.username_entry.focus_set()

        # Password
        ttk.Label(form_frame, text="Parol:", font=('Helvetica', 11), foreground=self.style.colors.primary).pack(anchor=tk.W, pady=(10, 0))
        self.password_entry = ttk.Entry(form_frame, foreground=self.style.colors.primary, show="*", font=('Helvetica', 11))
        self.password_entry.pack(fill=tk.X, pady=5)

        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(20, 0))

        # Login button
        login_btn = ttk.Button(
            buttons_frame,
            text="Kirish",
            command=self.authenticate,
            bootstyle="primary",
            width=10
        )
        login_btn.pack(side=tk.LEFT, padx=5)

        # Cancel button
        cancel_btn = ttk.Button(
            buttons_frame,
            text="Bekor qilish",
            command=self.window.destroy,
            bootstyle="primary",
            width=10
        )
        cancel_btn.pack(side=tk.RIGHT, padx=5)

        # Center buttons
        ttk.Frame(buttons_frame).pack(side=tk.LEFT, expand=True)
        ttk.Frame(buttons_frame).pack(side=tk.RIGHT, expand=True)

        # Bind Enter key to login
        self.window.bind('<Return>', lambda e: self.authenticate())

        # Center the window
        self.center_window(1080, 720)

        # Modal holat
        self.window.transient(parent)
        self.window.grab_set()
        parent.wait_window(self.window)

    def center_window(self, width, height):
        """Oynani ekranning markazida ochish"""
        self.window.update_idletasks()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def authenticate(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if username == "admin" and password == "123":
            self.username_entry.delete(0, tk.END)
            self.password_entry.delete(0, tk.END)
            self.window.destroy()
            self.on_success()
        else:
            messagebox.showerror("Xatolik", "Noto'g'ri login yoki parol!", parent=self.window)

# Users Window
import tkinter as tk
from tkinter import ttk, messagebox
from ttkbootstrap import Style
from PIL import Image, ImageTk
import io

# Users Window
class UsersWindow:
    def __init__(self, parent, face_db):
        self.parent = parent
        self.face_db = face_db
        self.window = tk.Toplevel(parent)
        self.window.title("Foydalanuvchilar boshqaruvi")
        self.window.minsize(1080, 720)

        # Set window icon
        try:
            self.window.iconbitmap('face.ico')
        except:
            pass
        
        # Styling Foydalanuvchilar page
        self.style = Style(theme='morph')
        self.window.configure(bg=self.style.colors.bg)
        
        # Configure grid
        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        
        # Main container
        main_container = ttk.Frame(self.window, padding=10)
        main_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_container.grid_rowconfigure(1, weight=1)
        main_container.grid_columnconfigure(0, weight=1)
        
        # Header
        header_frame = ttk.Frame(main_container)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # Title with icon
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(side=tk.LEFT)

        # Title as LabelFrame style for Treeview
        table_frame = ttk.LabelFrame(
            main_container,
            text="Foydalanuvchilar ro'yxati",
            padding=15,
            style='primary.TLabelframe'
        )
        table_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # Treeview with scrollbars inside LabelFrame
        self.tree = ttk.Treeview(
            table_frame,
            columns=("id", "ism", "familiya", "created_at", "last_entry"),
            show="headings",
            selectmode="browse",
            style="primary"
        )

        # Vertical scrollbar
        vsb = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
            style="primary"
        )
        self.tree.configure(yscrollcommand=vsb.set)

        # Horizontal scrollbar
        hsb = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.tree.xview,
            style="primary"
        )
        self.tree.configure(xscrollcommand=hsb.set)

        # Grid layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Configure columns
        self.tree.heading("id", text="ID", anchor=tk.CENTER)
        self.tree.heading("ism", text="Ism", anchor=tk.CENTER)
        self.tree.heading("familiya", text="Familiya", anchor=tk.CENTER)
        self.tree.heading("created_at", text="Yaratilgan vaqt", anchor=tk.CENTER)
        self.tree.heading("last_entry", text="Oxirgi kirish vaqti", anchor=tk.CENTER)

        self.tree.column("id", width=80, anchor=tk.CENTER)
        self.tree.column("ism", width=150, anchor=tk.CENTER)
        self.tree.column("familiya", width=150, anchor=tk.CENTER)
        self.tree.column("created_at", width=200, anchor=tk.CENTER)
        self.tree.column("last_entry", width=200, anchor=tk.CENTER)

        # Style the treeview
        self.style.configure('primary.Treeview', font=('Helvetica', 10))
        self.style.configure('primary.Treeview.Heading', font=('Helvetica', 11, 'bold'))

        # Treeview tags for coloring rows
        self.tree.tag_configure('normal', background='white', foreground='black')  # default
        self.tree.tag_configure('selected', background='#0d6efd', foreground='white')  # primary

        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # User details frame
        details_frame = ttk.LabelFrame(
            main_container,
            text="Foydalanuvchi ma'lumotlari",
            padding=15,
            width=350,
            style='primary.TLabelframe'
        )
        details_frame.grid(row=1, column=1, sticky="nsew")
        details_frame.grid_propagate(False)
        
        # User image
        self.user_image = ttk.Label(details_frame, style='primary.TLabel')
        self.user_image.pack(pady=(0, 20))
        
        # User info container
        info_container = ttk.Frame(details_frame)
        info_container.pack(fill=tk.X)
        
        # ID frame
        id_frame = ttk.Frame(info_container)
        id_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            id_frame,
            text="ID : ",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).pack(side=tk.LEFT)
        self.id_label = ttk.Label(
            id_frame,
            text="",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.id_label.pack(side=tk.LEFT, padx=(5, 0))

        # Ism frame
        ism_frame = ttk.Frame(info_container)
        ism_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            ism_frame,
            text="Ism : ",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).pack(side=tk.LEFT)
        self.ism_label = ttk.Label(
            ism_frame,
            text="",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.ism_label.pack(side=tk.LEFT, padx=(5, 0))

        # Familiya frame
        familiya_frame = ttk.Frame(info_container)
        familiya_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            familiya_frame,
            text="Familiya : ",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).pack(side=tk.LEFT)
        self.familiya_label = ttk.Label(
            familiya_frame,
            text="",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.familiya_label.pack(side=tk.LEFT, padx=(5, 0))

        # Created at frame
        created_frame = ttk.Frame(info_container)
        created_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            created_frame,
            text="Yaratilgan vaqt : ",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).pack(side=tk.LEFT)
        self.created_label = ttk.Label(
            created_frame,
            text="",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.created_label.pack(side=tk.LEFT)

        # Last entry frame
        last_entry_frame = ttk.Frame(info_container)
        last_entry_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            last_entry_frame,
            text="Oxirgi kirish vaqti : ",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).pack(side=tk.LEFT)
        self.last_entry_label = ttk.Label(
            last_entry_frame,
            text="",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.last_entry_label.pack(side=tk.LEFT)
        
        # Button frame
        button_frame = ttk.Frame(details_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))
        
        # Edit button
        edit_btn = ttk.Button(
            button_frame,
            text="Tahrirlash",
            command=self.edit_user,
            bootstyle="primary",
            width=23
        )
        edit_btn.pack(side=tk.LEFT, fill=tk.X, padx=(0, 5))
        
        # Delete button
        delete_btn = ttk.Button(
            button_frame,
            text="O'chirish",
            command=self.delete_user,
            bootstyle="danger",
            width=23
        )
        delete_btn.pack(side=tk.LEFT, fill=tk.X, padx=(5, 0))
        
        # Load initial data
        self.load_users()
        
        # Center the window
        self.center_window(1080, 720)
        
        # Modal holat
        self.window.transient(parent)
        self.window.grab_set()

    def center_window(self, width, height):
        """Oynani ekranning markazida ochish"""
        self.window.update_idletasks()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
    
    def load_users(self):
        users = self.face_db.foydalanuvchi_malumotlari()
        
        # Clear existing data
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add new data with proper handling of empty values
        for user in users:
            # Convert None values to empty strings and handle empty values
            processed_values = []
            for value in user:
                if value is None:
                    processed_values.append("")
                else:
                    processed_values.append(value)
            
            self.tree.insert("", tk.END, values=processed_values)
    
    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
            
        item = self.tree.item(selected[0])
        user_id = item['values'][0]
        
        # Get user image
        img_bytes = self.face_db.get_user_image(user_id)
        
        if img_bytes:
            try:
                img = Image.open(io.BytesIO(img_bytes))
                img.thumbnail((300, 300))
                
                photo = ImageTk.PhotoImage(img)
                self.user_image.config(image=photo)
                self.user_image.image = photo
            except Exception as e:
                print("Error loading image:", e)
                self.show_blank_image()
        else:
            self.show_blank_image()
        
        # Update labels with proper handling of empty values
        self.id_label.config(text=str(user_id))
        
        # Handle empty name values
        ism_value = item['values'][1]
        self.ism_label.config(text=ism_value if ism_value and ism_value.strip() != "" else "Mavjud emas")
        
        # Handle empty surname values
        familiya_value = item['values'][2]
        self.familiya_label.config(text=familiya_value if familiya_value and familiya_value.strip() != "" else "Mavjud emas")
        
        # Handle created_at
        created_value = item['values'][3]
        self.created_label.config(text=created_value if created_value else "Mavjud emas")
        
        # Handle last_entry
        last_entry_value = item['values'][4]
        self.last_entry_label.config(text=last_entry_value if last_entry_value else "Mavjud emas")
    
    def show_blank_image(self):
        blank = Image.new('RGB', (300, 300), (50, 50, 50))
        photo = ImageTk.PhotoImage(blank)
        self.user_image.config(image=photo)
        self.user_image.image = photo
    
    def edit_user(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Ogohlantirish",
                "Iltimos, foydalanuvchini tanlang!",
                parent=self.window
            )
            return

        item = self.tree.item(selected[0])
        user_id = item['values'][0]
        current_ism = item['values'][1] or ""
        current_familiya = item['values'][2] or ""
        
        # Tahrirlash oynasini ochish
        edit_window = tk.Toplevel(self.window)
        edit_window.title("Foydalanuvchini tahrirlash")
        edit_window.resizable(False, False)
        
        try:
            edit_window.iconbitmap('face.ico')
        except:
            pass
        
        # Markazga joylash
        edit_window.update_idletasks()
        w = 400
        h = 300
        ws = edit_window.winfo_screenwidth()
        hs = edit_window.winfo_screenheight()
        x = (ws // 2) - (w // 2)
        y = (hs // 2) - (h // 2)
        edit_window.geometry(f'{w}x{h}+{x}+{y}')
        
        # Modal holat
        edit_window.transient(self.window)
        edit_window.grab_set()
        
        # Asosiy konteyner
        main_frame = ttk.Frame(edit_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Sarlavha
        ttk.Label(
            main_frame, 
            text=f"ID-{user_id} foydalanuvchisini tahrirlash",
            font=('Helvetica', 12, 'bold')
        ).pack(pady=(0, 20))
        
        # Ism kiritish
        ism_frame = ttk.Frame(main_frame)
        ism_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(ism_frame, text="Ism:").pack(side=tk.LEFT)
        ism_entry = ttk.Entry(ism_frame)
        ism_entry.pack(side=tk.RIGHT, fill=tk.X, padx=(10, 0))
        ism_entry.insert(0, current_ism)
        
        # Familiya kiritish
        familiya_frame = ttk.Frame(main_frame)
        familiya_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Label(familiya_frame, text="Familiya:").pack(side=tk.LEFT)
        familiya_entry = ttk.Entry(familiya_frame)
        familiya_entry.pack(side=tk.RIGHT, fill=tk.X, padx=(10, 0))
        familiya_entry.insert(0, current_familiya)
        
        # Tugmalar
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))
        
        def save_changes():
            new_ism = ism_entry.get().strip()
            new_familiya = familiya_entry.get().strip()
            
            if self.face_db.update_user_info(user_id, new_ism, new_familiya):
                messagebox.showinfo(
                    "Muvaffaqiyatli",
                    "Foydalanuvchi ma'lumotlari muvaffaqiyatli yangilandi!",
                    parent=edit_window
                )
                self.load_users()
                edit_window.destroy()
            else:
                messagebox.showerror(
                    "Xatolik",
                    "Ma'lumotlarni yangilashda xatolik yuz berdi!",
                    parent=edit_window
                )
        
        def cancel_edit():
            edit_window.destroy()
        
        ttk.Button(
            button_frame,
            text="Yangilash",
            command=save_changes,
            bootstyle="success"
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        ttk.Button(
            button_frame,
            text="Bekor qilish",
            command=cancel_edit,
            bootstyle="secondary"
        ).pack(side=tk.RIGHT, padx=(0, 5))
    
    def delete_user(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Ogohlantirish",
                "Iltimos, foydalanuvchini tanlang!",
                parent=self.window
            )
            return

        item = self.tree.item(selected[0])
        user_id = item['values'][0]

        # Maxsus Ha/Yo'q dialog
        def confirm_delete(user_id):
            top = tk.Toplevel(self.window)
            top.title("Tasdiqlash")
            top.resizable(False, False)

            try:
                top.iconbitmap('face.ico')
            except Exception as e:
                print("Icon yuklashda xatolik:", e)

            tk.Label(top, text=f"{user_id}-ID foydalanuvchisini o'chirishni istaysizmi?").pack(padx=20, pady=20)

            result = {'value': False}

            def yes():
                result['value'] = True
                top.destroy()

            def no():
                result['value'] = False
                top.destroy()

            btn_frame = tk.Frame(top)
            btn_frame.pack(pady=10)
            tk.Button(btn_frame, text="Ha", width=10, command=yes).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="Yo'q", width=10, command=no).pack(side=tk.LEFT, padx=5)

            top.update_idletasks()
            w = top.winfo_width()
            h = top.winfo_height()
            ws = top.winfo_screenwidth()
            hs = top.winfo_screenheight()
            x = (ws // 2) - (w // 2)
            y = (hs // 2) - (h // 2)
            top.geometry(f'{w}x{h}+{x}+{y}')

            top.grab_set()
            top.wait_window()
            return result['value']

        confirm = confirm_delete(user_id)

        if confirm:
            if self.face_db.foydalanuvchini_ochirish(user_id):
                messagebox.showinfo(
                    "Muvaffaqiyatli",
                    "Foydalanuvchi muvaffaqiyatli o'chirildi!",
                    parent=self.window
                )
                self.load_users()

                # Clear details
                self.id_label.config(text="")
                self.ism_label.config(text="")
                self.familiya_label.config(text="")
                self.created_label.config(text="")
                self.last_entry_label.config(text="")
                self.show_blank_image()
            else:
                messagebox.showerror(
                    "Xatolik",
                    "Foydalanuvchini o'chirishda xatolik yuz berdi!",
                    parent=self.window
                )


class FaceRecognitionApp:
    def __init__(self, root):
        self.root = root
        self.style = Style(theme='morph')
        self.root.title("Yuzni tanib olish tizimi")
        self.root.minsize(1080, 720)  # Oynani kengaytiramiz

        # Set window icon
        try:
            self.root.iconbitmap('face.ico')
        except:
            pass

        # Oynani markazda ochish
        self.center_window(1080, 720)
        
        # Configure grid - 2 ta ustun: 75% kamera, 25% ma'lumotlar
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=4)  # Kamera uchun 75%
        self.root.grid_columnconfigure(1, weight=1)  # Ma'lumotlar uchun 25%
        
        # Kamera konteyneri (chap tomonda)
        camera_container = ttk.Frame(root)
        camera_container.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        camera_container.grid_rowconfigure(1, weight=1)
        camera_container.grid_columnconfigure(0, weight=1)

        # Foydalanuvchi ma'lumotlari paneli (o'ng tomonda)
        self.info_panel = ttk.Frame(root, width=250)
        self.info_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 5), pady=10)
        self.info_panel.grid_propagate(False)
        self.info_panel.grid_rowconfigure(1, weight=1)
        
        # Foydalanuvchi ma'lumotlari panelini sozlash
        self.setup_info_panel()

        # Camera frame - fixed size
        self.camera_frame = ttk.LabelFrame(
            camera_container,
            text="Kamera",
            style='primary.TLabelframe'
        )
        self.camera_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.camera_frame.grid_rowconfigure(0, weight=1)
        self.camera_frame.grid_columnconfigure(0, weight=1)
        
        # Video container - fixed size
        self.video_container = ttk.Frame(self.camera_frame)
        self.video_container.grid(row=0, column=0, sticky="nsew")
        self.video_container.grid_rowconfigure(0, weight=1)
        self.video_container.grid_columnconfigure(0, weight=1)
        
        # Video label - fixed size
        self.video_label = ttk.Label(self.video_container)
        self.video_label.grid(row=0, column=0, sticky="nsew")
        
        # Control panel
        self.control_panel = ttk.Frame(camera_container)
        self.control_panel.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        
        # Status label
        self.status_label = ttk.Label(
            self.control_panel,
            text="Holat: Tizim hozir ishlamayapti",
            anchor=tk.W,
            style='primary',
            font=('Helvetica', 10)
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Users button
        self.users_btn = ttk.Button(
            self.control_panel,
            text="Foydalanuvchilar",
            command=self.show_login_window,
            bootstyle="primary",
            width=15
        )
        self.users_btn.pack(side=tk.RIGHT, padx=5)
        
        # Buttons frame
        self.buttons_frame = ttk.Frame(camera_container)
        self.buttons_frame.grid(row=3, column=0, pady=10)
        
        # Start button
        self.start_btn = ttk.Button(
            self.buttons_frame,
            text="Yoqish",
            command=self.start_recognition,
            bootstyle="primary",
            width=10
        )
        self.start_btn.pack(side=tk.LEFT, padx=10)
        
        # Stop button
        self.stop_btn = ttk.Button(
            self.buttons_frame,
            text="To'xtatish",
            command=self.stop_recognition,
            bootstyle="primary",
            width=10
        )
        self.stop_btn.pack(side=tk.LEFT, padx=10)
        
        # Initialize face recognition
        self.face_db = FaceDB("face_db", "postgres", "123", "localhost", "5432")
        self.video_capture = None
        self.known_face_ids = []
        self.known_face_encodings = []
        self.face_detector = FaceOrientationDetector()
        self.last_log_times = {}
        self.running = False
        self.frame_queue = queue.Queue(maxsize=1)
        self.current_user_id = None

        self.clear_user_info()
        
        # Check for GPU acceleration
        self.gpu_enabled = False
        try:
            import dlib
            if dlib.DLIB_USE_CUDA:
                self.gpu_enabled = True
                print("GPU acceleration is enabled for face recognition")
            else:
                print("Warning: GPU acceleration not available for face recognition")
        except:
            print("Warning: Could not check GPU acceleration status")
            
    def setup_info_panel(self):
        """Foydalanuvchi ma'lumotlari panelini sozlash"""
        # Asosiy konteyner - butun panelni to'ldiradi
        main_container = ttk.Frame(self.info_panel)
        main_container.grid(row=0, column=0, sticky="nsew")
        main_container.grid_rowconfigure(1, weight=1)  # Ma'lumotlar qismi kengayadi
        main_container.grid_columnconfigure(0, weight=1)
        
        # Ma'lumotlar konteyneri - kengayadi va qisqaradi
        info_container = ttk.LabelFrame(
            main_container,
            text="Foydalanuvchi ma'lumotlari",
            padding=15,
            style='primary.TLabelframe'
        )
        info_container.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        info_container.grid_rowconfigure(2, weight=1)  # Rasm va ma'lumotlar uchun
        info_container.grid_columnconfigure(0, weight=1)
        
        # User image - container markazida
        self.user_image_label = ttk.Label(
            info_container,
            style='primary.TLabel',
            anchor=tk.CENTER
        )
        self.user_image_label.grid(row=0, column=0, pady=(0, 15), sticky="n")
        
        # Ma'lumotlar gridi
        details_frame = ttk.Frame(info_container)
        details_frame.grid(row=1, column=0, sticky="nsew")
        details_frame.grid_columnconfigure(1, weight=1)
        
        # ID
        ttk.Label(
            details_frame,
            text="ID:",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.user_id_label = ttk.Label(
            details_frame,
            text="-",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.user_id_label.grid(row=0, column=1, sticky="w", pady=(0, 8), padx=(5, 0))
        
        # Ism
        ttk.Label(
            details_frame,
            text="Ism:",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.user_name_label = ttk.Label(
            details_frame,
            text="-",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.user_name_label.grid(row=1, column=1, sticky="w", pady=(0, 8), padx=(5, 0))
        
        # Familiya
        ttk.Label(
            details_frame,
            text="Familiya:",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).grid(row=2, column=0, sticky="w", pady=(0, 8))
        self.user_surname_label = ttk.Label(
            details_frame,
            text="-",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.user_surname_label.grid(row=2, column=1, sticky="w", pady=(0, 8), padx=(5, 0))
        
        # Yaratilgan vaqt
        ttk.Label(
            details_frame,
            text="Yaratilgan vaqt:",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.user_created_label = ttk.Label(
            details_frame,
            text="-",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.user_created_label.grid(row=3, column=1, sticky="w", pady=(0, 8), padx=(5, 0))
        
        # Oxirgi kirish
        ttk.Label(
            details_frame,
            text="Oxirgi kirish:",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).grid(row=4, column=0, sticky="w", pady=(0, 8))
        self.user_last_entry_label = ttk.Label(
            details_frame,
            text="-",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.user_last_entry_label.grid(row=4, column=1, sticky="w", pady=(0, 8), padx=(5, 0))
        
        # Holat
        ttk.Label(
            details_frame,
            text="Holat:",
            font=('Helvetica', 10, 'bold'),
            foreground=self.style.colors.primary
        ).grid(row=5, column=0, sticky="w", pady=(0, 8))
        self.user_status_label = ttk.Label(
            details_frame,
            text="Kutilmoqda...",
            font=('Helvetica', 10),
            foreground=self.style.colors.primary
        )
        self.user_status_label.grid(row=5, column=1, sticky="w", pady=(0, 8), padx=(5, 0))
        
        # Tozalash tugmasi - pastki qismda
        button_frame = ttk.Frame(main_container)
        button_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        button_frame.grid_columnconfigure(0, weight=1)
        
        self.clear_btn = ttk.Button(
            button_frame,
            text="Tozalash",
            command=self.clear_user_info,
            bootstyle="primary",
            width=15
        )
        self.clear_btn.grid(row=0, column=0)
        
        # Boshlang'ich rasmni ko'rsatish
        self.show_default_image()
        
        # Ma'lumotlar panelini moslashuvchan qilish
        self.info_panel.grid_rowconfigure(0, weight=1)
        self.info_panel.grid_columnconfigure(0, weight=1)
            
    def center_window(self, width, height):
        """Oynani ekranning markazida ochish"""
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def show_login_window(self):
        LoginWindow(self.root, self.show_users_window)
    
    def show_users_window(self):
        UsersWindow(self.root, self.face_db)
    
    def start_recognition(self):
        if self.running:
            return
            
        self.known_face_ids, self.known_face_encodings = self.face_db.barcha_yuzlarni_olish()
        self.video_capture = cv2.VideoCapture(0)
        
        if not self.video_capture.isOpened():
            messagebox.showerror("Xatolik", "Kamerani ochib bo'lmadi!")
            return
        
        if self.known_face_encodings:
            self.known_face_encodings = np.array(self.known_face_encodings)
            
        self.running = True
        self.status_label.config(text="Holat: Yuzni aniqlash amalga oshirilyapti")
        self.user_status_label.config(text="Yuzni aniqlash...")
        
        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self.process_frames,
            daemon=True
        )
        self.processing_thread.start()
        
        # Start updating GUI
        self.update_frame()
    
    def stop_recognition(self): 
        if not self.running:
            return
            
        self.running = False
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None
            
        # Clear video display
        blank = Image.new('RGB', (1080, 720), (217, 227, 241))
        blank_img = ImageTk.PhotoImage(blank)
        self.video_label.config(image=blank_img)
        self.video_label.image = blank_img
        
        self.status_label.config(text="Holat: Tizim to'xtatilgan")
        self.user_status_label.config(text="Tizim to'xtatilgan")
    
    def process_frames(self):
        while self.running:
            ret, frame = self.video_capture.read()
            if not ret:
                continue
                
            frame = cv2.flip(frame, 1)
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            try:
                # Detect faces
                face_locations = face_recognition.face_locations(
                    rgb_frame,
                    model="cnn" if self.gpu_enabled else "hog"
                )
                face_locations = [(t*2, r*2, b*2, l*2) for (t, r, b, l) in face_locations]

                # Yuzlar sonini tekshirish
                face_count = len(face_locations)
                
                name = "Yuz topilmadi"
                if face_count==0:
                    # Yuz topilmasa
                    cv2.putText(frame, "Yuz topilmadi", (50, 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    self.user_status_label.config(text="Yuz topilmadi")
                elif face_count==1:
                    # Get face encodings
                    face_encodings = face_recognition.face_encodings(
                        rgb_frame,
                        [face_locations[0]],
                        num_jitters=1
                    )
                    
                    if face_encodings:
                        
                        face_encoding = face_encodings[0]
                        top, right, bottom, left = face_locations[0]
                        
                        # Check face orientation
                        sub_frame = frame[top:bottom, left:right]
                        orientation_ok = self.face_detector.detect(sub_frame)
                        
                        if not orientation_ok:
                            name = "Yuz holati noto'g'ri"
                            self.user_status_label.config(text="Yuz holati noto'g'ri")
                        else:
                            if len(self.known_face_encodings) > 0:
                                # Compare with known faces
                                distances = face_recognition.face_distance(
                                    self.known_face_encodings, 
                                    face_encoding
                                )
                                best_match = np.argmin(distances)
                                
                                if distances[best_match] < 0.5:
                                    face_id = self.known_face_ids[best_match]
                                    name = f"ID-{face_id}"
                                    
                                    # Yangi foydalanuvchi aniqlangan bo'lsa, ma'lumotlarni yangilash
                                    if self.current_user_id != face_id:
                                        self.update_user_info(face_id)
                                        self.current_user_id = face_id
                                    
                                    # Log entry if needed
                                    needs_log = (
                                        face_id not in self.last_log_times or 
                                        (datetime.now() - self.last_log_times[face_id]).total_seconds() >= 30
                                    )
                                    
                                    if needs_log:
                                        self.face_db.kirishni_loglash(face_id)
                                        self.last_log_times[face_id] = datetime.now()
                                        # Oxirgi kirish vaqtini yangilash
                                        self.update_last_entry_time(face_id)
                                else:
                                    name = "Noma'lum shaxs!"
                                    self.user_status_label.config(text="Noma'lum shaxs!")
                                    self.clear_user_info()
                            else:
                                name = "Noma'lum shaxs!"
                                self.user_status_label.config(text="Noma'lum shaxs!")
                                self.clear_user_info()
                            
                            # Add new face if unknown
                            if name == "Noma'lum shaxs!":
                                face_image = frame[top:bottom, left:right]
                                face_id = self.face_db.yuz_qoshish(face_image, face_encoding)
                                
                                if face_id:
                                    name = f"ID-{face_id}"
                                    self.known_face_ids.append(face_id)
                                    self.known_face_encodings = np.vstack([
                                        self.known_face_encodings, 
                                        face_encoding
                                    ]) if len(self.known_face_encodings) > 0 else np.array([face_encoding])
                                    self.last_log_times[face_id] = datetime.now()
                                    # Yangi foydalanuvchi ma'lumotlarini yangilash
                                    self.update_user_info(face_id)
                                    self.current_user_id = face_id
                        
                        # Draw rectangle and label
                        cv2.putText(frame, name, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                else:
                    # Ko'p yuz topilgan
                    cv2.putText(frame, f"Ogohlantirish: {face_count} ta yuz aniqlandi!", (50, 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    self.user_status_label.config(text=f"{face_count} ta yuz aniqlandi!")
            
            except Exception as e:
                print("Xatolik:", e)
            
            # Add frame to queue if empty
            if self.frame_queue.empty():
                self.frame_queue.put(frame)
    
    def update_frame(self):
        if not self.running:
            return
            
        try:
            frame = self.frame_queue.get_nowait()
            
            # Convert to RGB
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert to PIL Image
            pil_image = Image.fromarray(rgb_image)
            
            # Container o'lchamini olish
            container_width = self.video_container.winfo_width()
            container_height = self.video_container.winfo_height()
            
            # Agar container o'lchamlari mavjud bo'lsa
            if container_width > 1 and container_height > 1:
                # Proportional resize
                img_ratio = pil_image.width / pil_image.height
                container_ratio = container_width / container_height
                
                if container_ratio > img_ratio:
                    # Container wider than image
                    new_height = container_height
                    new_width = int(new_height * img_ratio)
                else:
                    # Container taller than image
                    new_width = container_width
                    new_height = int(new_width / img_ratio)
                
                # Yangi o'lchamlar 0 dan katta bo'lishi kerak
                if new_width > 0 and new_height > 0:
                    pil_image = pil_image.resize((new_width, new_height), Image.LANCZOS)
            
            # Convert to Tkinter PhotoImage
            img_tk = ImageTk.PhotoImage(image=pil_image)
            
            # Update label
            self.video_label.imgtk = img_tk
            self.video_label.config(image=img_tk)
            
        except queue.Empty:
            pass
            
        self.root.after(30, self.update_frame)  # 30ms delay for smoother video
    
    def update_user_info(self, user_id):
        user_info = self.face_db.get_user_details(user_id)
            
        if user_info:
            # Rasmni yangilash
            img_bytes = self.face_db.get_user_image(user_id)
            if img_bytes:
                try:
                    img = Image.open(io.BytesIO(img_bytes))
                    img.thumbnail((200, 200))
                    photo = ImageTk.PhotoImage(img)
                    self.user_image_label.config(image=photo)
                    self.user_image_label.image = photo
                except Exception as e:
                    print("Rasm yuklashda xatolik:", e)
                    self.show_default_image()
            else:
                self.show_default_image()
            
            # Ma'lumotlarni yangilash
            self.user_id_label.config(text=str(user_id))
            self.user_name_label.config(text=user_info.get('ism', 'Mavjud emas'))
            self.user_surname_label.config(text=user_info.get('familiya', 'Mavjud emas'))
            self.user_created_label.config(text=user_info.get('created_at', 'Mavjud emas'))
            
            # Oxirgi kirish vaqtini yangilash
            self.update_last_entry_time(user_id)
            
            # Holatni yangilash
            self.user_status_label.config(text="Tanildi")
        else:
            self.clear_user_info()
    
    def update_last_entry_time(self, user_id):
        """Oxirgi kirish vaqtini yangilash"""
        if not self.face_db.ulanish():
            return None
        try:
            with self.face_db.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT MAX(entry_time) FROM face_log_data WHERE id_name = %s",
                    (user_id,)
                )
                result = cursor.fetchone()
                if result and result[0]:
                    self.user_last_entry_label.config(text=result[0].strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    self.user_last_entry_label.config(text="Mavjud emas")
        except Exception as e:
            print("Oxirgi kirish vaqtini olishda xatolik:", e)
            self.user_last_entry_label.config(text="Mavjud emas")
    
    def show_default_image(self):
        """Standart rasmni ko'rsatish"""
        blank = Image.new('RGB', (200, 200), (50, 50, 50))
        photo = ImageTk.PhotoImage(blank)
        self.user_image_label.config(image=photo)
        self.user_image_label.image = photo
    
    def clear_user_info(self):
        """Foydalanuvchi ma'lumotlarini tozalash"""
        self.current_user_id = None
        self.user_id_label.config(text="-")
        self.user_name_label.config(text="-")
        self.user_surname_label.config(text="-")
        self.user_created_label.config(text="-")
        self.user_last_entry_label.config(text="-")
        self.user_status_label.config(text="Kutilmoqda...")
        self.show_default_image()

if __name__ == "__main__":
    # Create assets directory if not exists
    if not os.path.exists('assets'):
        os.makedirs('assets')

    # Initialize database
    face_db = FaceDB("face_db", "postgres", "123", "localhost", "5432")
    face_db.jadvallarni_yaratish()
    
    # Create and run app
    root = tk.Tk()
    app = FaceRecognitionApp(root)
    root.mainloop()