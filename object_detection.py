'''import cv2
import numpy as np
import os


def load_yolo():
    net = cv2.dnn.readNet(os.path.join("static", "yolov3.weights"), os.path.join("static", "yolov3.cfg"))
    with open(os.path.join("static", "coco.names"), "r") as f:
        classes = [line.strip() for line in f.readlines()]
    layer_names = net.getLayerNames()
    output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]
    return net, classes, output_layers


def detect_objects_with_boxes(img):
    """
    Detection ottimizzata che restituisce sia immagine che dati box
    """
    net, classes, output_layers = load_yolo()
    height, width, channels = img.shape

    # Input più grande per precisione
    input_size = 608
    blob = cv2.dnn.blobFromImage(img, 0.00392, (input_size, input_size), (0, 0, 0), True, crop=False)
    net.setInput(blob)
    outs = net.forward(output_layers)

    class_ids = []
    confidences = []
    boxes = []
    detection_data = []

    # Soglie ottimizzate
    confidence_threshold = 0.4

    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > confidence_threshold:
                center_x = detection[0] * width
                center_y = detection[1] * height
                w = detection[2] * width
                h = detection[3] * height

                x = int(center_x - w / 2)
                y = int(center_y - h / 2)
                w = int(w)
                h = int(h)

                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)

    # NMS per eliminare duplicati
    nms_threshold = 0.3
    indexes = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, nms_threshold)

    # Crea immagine con detection
    result_img = img.copy()

    for i in range(len(boxes)):
        if i in indexes:
            x, y, w, h = boxes[i]
            label = str(classes[class_ids[i]])
            confidence = confidences[i]

            # Disegna su immagine
            cv2.rectangle(result_img, (x, y), (x + w, y + h), (0, 0, 255), 4)
            cv2.putText(result_img, f"{label} {confidence:.2f}", (x, y + 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)

            # Salva dati per overlay
            detection_data.append({
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'label': label,
                'confidence': confidence,
                'class_id': class_ids[i]
            })

    print(f"🎯 Found {len(detection_data)} objects with 608px input")
    for det in detection_data:
        print(f"  - {det['label']} at ({det['x']},{det['y']}) {det['w']}x{det['h']} conf:{det['confidence']:.3f}")

    return result_img, detection_data


def detect_objects(img):
    """Funzione originale per compatibilità"""
    result_img, _ = detect_objects_with_boxes(img)
    return result_img'''


import cv2
import numpy as np
import os

# Colori coerenti per le classi principali, fallback verde per tutte le altre
LABEL_COLORS = {
    'person': (0, 0, 255),    # RED
    # puoi aggiungere altre classi
}
DEFAULT_BOX_COLOR = (0, 255, 0)  # GREEN


def load_yolo():
    net = cv2.dnn.readNet(
        os.path.join("static", "yolov3.weights"),
        os.path.join("static", "yolov3.cfg")
    )
    with open(os.path.join("static", "coco.names"), "r") as f:
        classes = [line.strip() for line in f.readlines()]
    layer_names = net.getLayerNames()
    output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]
    return net, classes, output_layers


def detect_objects_with_boxes(img):
    """
    Detection ottimizzata che restituisce sia immagine annotata che dati box
    """
    net, classes, output_layers = load_yolo()
    height, width, channels = img.shape

    input_size = 608
    blob = cv2.dnn.blobFromImage(img, 0.00392, (input_size, input_size), (0, 0, 0), True, crop=False)
    net.setInput(blob)
    outs = net.forward(output_layers)

    class_ids = []
    confidences = []
    boxes = []
    detection_data = []

    confidence_threshold = 0.4

    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > confidence_threshold:
                center_x = detection[0] * width
                center_y = detection[1] * height
                w = detection[2] * width
                h = detection[3] * height

                x = int(center_x - w / 2)
                y = int(center_y - h / 2)
                w = int(w)
                h = int(h)

                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)

    nms_threshold = 0.3
    indexes = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, nms_threshold)

    result_img = img.copy()

    for i in range(len(boxes)):
        if i in indexes:
            x, y, w, h = boxes[i]
            label = str(classes[class_ids[i]])
            confidence = confidences[i]
            color = LABEL_COLORS.get(label, DEFAULT_BOX_COLOR)

            # Disegna su immagine
            cv2.rectangle(result_img, (x, y), (x + w, y + h), color, 4)
            label_text = f"{label} {confidence:.2f}"
            font_scale = 0.7
            text_thickness = 2
            (label_w, label_h), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thickness)
            center_x = x + w // 2
            text_x = center_x - label_w // 2
            text_y = y - 10
            if text_y - label_h < 0:
                text_y = y + h + label_h + 10
            padding = 6
            cv2.rectangle(result_img,
                        (text_x - padding, text_y - label_h - padding),
                        (text_x + label_w + padding, text_y + padding),
                        color, -1)
            cv2.rectangle(result_img,
                        (text_x - padding, text_y - label_h - padding),
                        (text_x + label_w + padding, text_y + padding),
                        (255, 255, 255), 2)
            cv2.putText(result_img, label_text, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), text_thickness)

            detection_data.append({
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'label': label,
                'confidence': confidence,
                'class_id': class_ids[i]
            })

    print(f"🎯 Found {len(detection_data)} objects with 608px input")
    for det in detection_data:
        print(f"  - {det['label']} at ({det['x']},{det['y']}) {det['w']}x{det['h']} conf:{det['confidence']:.3f}")

    return result_img, detection_data

def detect_objects(img):
    """Compatibilità: restituisce immagine annotata, non i dati box"""
    result_img, _ = detect_objects_with_boxes(img)
    return result_img
