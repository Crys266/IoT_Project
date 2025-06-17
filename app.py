from flask import Flask, request, Response, render_template, jsonify
import cv2
import numpy as np
import os
from queue import Queue
from object_detection import detect_objects

app = Flask(__name__)
frame_queue = Queue(maxsize=1)
negative_effect = False
object_detection = False
current_command = ""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def gen_frames():
    while True:
        frame = frame_queue.get()
        img_array = np.frombuffer(frame, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if negative_effect:
            img = cv2.bitwise_not(img)  # Apply negative effect

        if object_detection:
            img = detect_objects(img)  # Apply object detection

        ret, buffer = cv2.imencode('.jpg', img)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/upload', methods=['POST'])
def upload():
    img_data = request.data
    if frame_queue.full():
        frame_queue.get()
    frame_queue.put(img_data)
    return "OK", 200

@app.route('/toggle_negative', methods=['POST'])
def toggle_negative():
    global negative_effect
    negative_effect = not negative_effect
    return jsonify(status="negative effect toggled", negative_effect=negative_effect)

@app.route('/toggle_object_detection', methods=['POST'])
def toggle_object_detection():
    global object_detection
    object_detection = not object_detection
    return jsonify(status="object detection toggled", object_detection=object_detection)

@app.route('/control', methods=['POST'])
def control():
    global current_command
    direction = request.form.get('direction')
    current_command = direction
    return jsonify(status="command received", direction=direction)

@app.route('/get_command', methods=['GET'])
def get_command():
    global current_command
    return current_command

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)