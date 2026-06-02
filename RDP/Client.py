import math
from queue import Queue
import socket
import struct
import threading
import mss
import numpy as np
import subprocess, sys
import pynput

def install_and_import(package, import_name = None):
    if import_name is None:
        import_name = package
    try:
        __import__(import_name)
    except ImportError:
        subprocess.check_call([sys.executable, '-m','pip','install',package])
install_and_import("opencv-python", "cv2")
install_and_import("mss")

install_and_import("pynput")
install_and_import("pynput.mouse")
install_and_import("pynput.keyboard")

import cv2
from pynput import mouse, keyboard
import mss

class MouseController:
    def __init__(self):
        self.controller = mouse.Controller()

    def set_position(self, x, y):
        self.controller.position = (x,y)

    def press(self, button: mouse.Button):
        self.controller.press(button=button)

    def release(self, button: mouse.Button):
        self.controller.release(button=button)

    def scroll(self, dy: int, dx: int):
        self.controller.scroll(dx, dy)

class KeyboardController:
    def __init__(self):
        self.controller = keyboard.Controller()

    def press(self, key: keyboard.Key):
        self.controller.press(key)

    def release(self, key: keyboard.Key):
        self.controller.release(key)

    def type(self, text: str):
        self.controller.type(text)


MAX_IMAGE_DGRAM = 60000  #max is 65,535 
UNSIGNED_INT_MAX_VALUE = 4294967295


class Client:
    def __init__(self,dest_ip: str, dest_port: int):  
        self.input_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.input_socket.connect((dest_ip, dest_port))

        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_target_addr = (dest_ip, dest_port)
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
    
    def get_commands(self):
        buffer = ""
        while True:
            data = self.input_socket.recv(1024).decode()
            # if not data:
            #     break
            buffer += data
            while "\n" in buffer:
                command, buffer = buffer.split("\n", 1)
                if command.strip():
                    self.execute_command(command.strip())

    def execute_command(self, command: str):
        command_parts = command.split(":")
        command_type = command_parts[0]
        if(command_type == 'M'):
            x = command_parts[1]
            y = command_parts[2]
            self.mouse.set_position(x,y)

        elif(command_type == 'C'):
            pressing_type = command_parts[1]
            button = self.get_button_object(command_parts[2])
            x = command_parts[3]
            y = command_parts[4]
            self.mouse.set_position(x,y)
            if pressing_type == 'P':
                self.mouse.press(button)
            elif pressing_type == 'R':
                self.mouse.release(button)

        elif command_type == 'K':
            pressing_type = command_parts[1]
            key = self.get_key_object(command_parts[2])
            if pressing_type == 'P':
                self.keyboard.press(key)
            elif pressing_type == 'R':
                self.keyboard.release(key)
                
        elif command_type == 'S':
            scroll_type = command_parts[1]
            if scroll_type == 'V': 
                try:
                    dy = int(command_parts[2])
                except:
                    print(f"{dy} not valid number")
                #dy = command_parts[2]
            elif scroll_type == 'H':
                try:
                    dx = int(command_parts[2])
                except:
                    print(f"{dx} not valid number")
            self.mouse.scroll(dy, dx)

        
    def get_button_object(self, button_string):
        button_name = button_string.split('.')[1]
        return getattr(mouse.Button, button_name)
    
    def get_key_object(self, key_string: str):
        # If the string starts with "Key.", it's a special key
        if "Key." in key_string:
            key_name = key_string.split('.')[1]
            return getattr(keyboard.Key, key_name)
        else:
            # It's a regular character (e.g., 'a' or '1')
            return key_string.strip("'")
        
    def start_screen_record(self):
        #con, addr = self.socket.accept()
        video_capture_thread = threading.Thread(target=self.handle_screen_record, args = (self.video_socket,self.udp_target_addr,))
        video_capture_thread.start()
        return video_capture_thread
    
    def draw_mouse(self, monitor, img):
        mouse_x, mouse_y = self.mouse.controller.position # actual coordinates of the mouse on the screen
        draw_x = int(mouse_x - monitor['left']) # coordinates to draw the mouse on the captured image (relative to the top-left corner of the monitor)
        draw_y = int(mouse_y - monitor['top'])
        if 0 <= draw_x < monitor['width'] and 0 <= draw_y < monitor['height']:
            cv2.circle(img, (draw_x, draw_y), 6, (0, 0, 0), -1)
            cv2.circle(img, (draw_x, draw_y), 4, (255, 255, 255), -1)

    def handle_screen_record(self, con:socket.socket, target_addr):
        sct = mss.MSS()
        monitor = sct.monitors[1]
        frame_id = 0
        while True:
            img_raw = np.array(sct.grab(monitor))
            # Convert BGRA to BGR (removes the alpha channel to save data)
            img_bgr = cv2.cvtColor(img_raw, cv2.COLOR_BGRA2BGR)
            self.draw_mouse(monitor, img_bgr)
            #compress to jpeg
            encode_paramaters = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
            _ , encoded_img = cv2.imencode('.jpg',img_bgr,encode_paramaters)
            data = encoded_img.tobytes()

            data_size = len(data)
            total_chunks = math.ceil(data_size / MAX_IMAGE_DGRAM) # how many packets will be needed to send
            for i in range(total_chunks):
                start = i * MAX_IMAGE_DGRAM
                end = min((i+1) * MAX_IMAGE_DGRAM, data_size)
                chunk_data = data[start:end]

                header = struct.pack("I B B", frame_id % UNSIGNED_INT_MAX_VALUE, i, total_chunks)# frame id, chunk id, chunk total
                con.sendto(header + chunk_data, target_addr)
            frame_id += 1

        
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not need to be reachable, just triggers the routing interface
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

client = Client("192.168.24.251", 7777)

thread = client.start_screen_record()
client.get_commands()