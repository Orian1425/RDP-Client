import os
import queue
import socket, threading
from pynput import mouse, keyboard
import cv2, numpy as np, struct 
from mss import mss

import socket
import time




class MouseListener:
    def __init__(self,q: queue.Queue):
        self.q = q
        self.listener = mouse.Listener(
            on_move=self.on_move, 
            on_click=self.on_click,
            on_scroll=self.on_scroll
        )
    def on_move(self, x, y, injected = False):
        self.q.put(f"M:{x}:{y}")
    
    def on_click(self, x, y, button, pressed, injected = False):
        self.q.put(f"C:{'P' if pressed else 'R'}:{button}:{x}:{y}")

    def on_scroll(self, x, y, dx, dy, injected = False):
        self.q.put(f"S:{dy}:{dx}")

    def start_listening(self):
        self.listener.start()


class KeyboardListener:
    def __init__(self, q: queue.Queue):
        self.q = q
        self.ctrl_pressed = False
        self.listner = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )

    def on_press(self, key, injected = False):
        try:
            print(f"{key} pressed")
        except AttributeError:
            print(f"special key {key} pressed")
        self.q.put(f"K:P:{key}")

        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.ctrl_pressed = True

        # 2. Check if Escape is pressed WHILE Control is being held down
        if key == keyboard.Key.esc and self.ctrl_pressed:
            print("Ctrl + Esc detected! Shutting down server application...")
            os._exit(0)

    def on_release(self, key, injected = False):
        print(f"{key} released")
        self.q.put(f"K:R:{key}")
        
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.ctrl_pressed = False
        
    def start_listening(self):
        self.listner.start()

class Host: # Protocol - k:a - keyboard, M:10,10 - mouse coords, B:mouse buttons
    def __init__(self, addr: str, port: int):
        self.output_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.output_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.output_socket.bind((addr,port))
        self.output_socket.listen()
        self.con, self.client_addr = self.output_socket.accept()
        
        self.input_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.input_socket.bind((addr, port))

        self.q = queue.Queue()

        self.mouse_listener = MouseListener(self.q)
        self.kb_listener = KeyboardListener(self.q)

        self.last_frame = None
     
    def start_input_capture(self):
        self.mouse_listener.start_listening()
        self.kb_listener.start_listening()
       
    def start_sending_data(self):
        self.start_input_capture()

        input_thread = threading.Thread(target=self.handling_KB_and_mouse_data,args=(self.con,))
        
        input_thread.start()
        
        return input_thread

    def handling_KB_and_mouse_data(self, con: socket.socket):
        while True:
            try:
                data = self.q.get()
                con.sendall(f"{data}\n".encode())
                self.q.task_done()
            except Exception as e:
                print(f"Connection lost: {e}")
                break

    def receive_screen_share(self):
        # 1. Start the network listener in the background
        # We set daemon=True so the thread dies safely when you close the app
        video_thread = threading.Thread(target=self.network_video_packet_listener, daemon=True)
        video_thread.start()
        
        # 2. Start the GUI loop on the MAIN thread
        self.gui_loop()

    def gui_loop(self):
        """Runs on the main thread. Only handles displaying the video."""
        # Create the window once before the loop starts
        cv2.namedWindow('Screen Recording', cv2.WINDOW_NORMAL)
        cv2.setWindowProperty('Screen Recording', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        while True:
            # If the background thread has provided a frame, show it
            if self.last_frame is not None:
                cv2.imshow('Screen Recording', self.last_frame)
            cv2.waitKey(1)
                
        cv2.destroyAllWindows()
    

    def network_video_packet_listener(self):
        frame_buffer = {}
        while True:
            packet, addr = self.input_socket.recvfrom(65535)

            header = packet[:6]
            chunk_data = packet[6:]

            frame_id, chunk_id, total_chunks = struct.unpack('I B B', header)
            if frame_id not in frame_buffer:
                frame_buffer[frame_id] = [None] * total_chunks # initialize item in list for every chunk [None,None,None,None...]
            frame_buffer[frame_id][chunk_id] = chunk_data

            if None not in frame_buffer[frame_id]: # all chunks have the data
                full_frame_data = b''.join(frame_buffer[frame_id])

                np_arr = np.frombuffer(full_frame_data, dtype=np.uint8) # convert bytes to np array
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR) # decode np array to jpg

                if frame is not None:
                    self.last_frame = frame

                del frame_buffer[frame_id]

            
def broadcast_presence(broadcast_port=50001):
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    # Unique token so your client knows it's actually your server
    magic_token = b"Orian" 
    
    print("Broadcasting server presence to the LAN...")
    try:
        while True:
            # Broadcast the token to everyone on the local subnet
            sock.sendto(magic_token, ('<broadcast>', broadcast_port))
            time.sleep(3)  # Announce every 3 seconds
    except KeyboardInterrupt:
        print("Stopping broadcast.")
    finally:
        sock.close()

t = threading.Thread(target=broadcast_presence)
t.start()
host = Host("0.0.0.0", 7777)
thread = host.start_sending_data()
host.receive_screen_share()