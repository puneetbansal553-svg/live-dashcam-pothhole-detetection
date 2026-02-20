import cv2
import numpy as np
import os
import csv
from gpiozero import LED, Buzzer
from time import sleep
from threading import Thread
import urllib.request

# ==============================
# PHONE IP WEBCAM URL
# ==============================
URL = "http://10.0.3.11:8080/video"

# ==============================
# GPIO
# ==============================
led = LED(14)
buzzer = Buzzer(15)

# ==============================
# PARAMETERS
# ==============================
RESIZE_WIDTH = 640
RESIZE_HEIGHT = 480
ROI_TOP = 300
CANNY_THRESH_LOW = 70
CANNY_THRESH_HIGH = 150
GAUSSIAN_BLUR = (7,7)
CONTOUR_AREA_MIN = 2000
ASPECT_RATIO_MIN = 0.5
ASPECT_RATIO_MAX = 2.0
SOLIDITY_MIN = 0.5
EXTENT_MIN = 0.4
DETECTION_FRAMES = 3
DARKNESS_THRESH = 80  # average pixel intensity threshold
SAVE_FRAMES = True
SAVE_DIR = "anomaly_frames"
CSV_FILE = "potholes.csv"

if SAVE_FRAMES and not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE,"w",newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Frame","x","y","w","h"])

frame_count = 0
anomaly_history = []

# ==============================
# THREAD FOR MJPEG CAPTURE
# ==============================
class VideoStream:
    def __init__(self, url):
        self.url = url
        self.frame = None
        self.stopped = False
        Thread(target=self.update, daemon=True).start()

    def update(self):
        stream = urllib.request.urlopen(self.url)
        bytes_data = b''
        while not self.stopped:
            bytes_data += stream.read(1024)
            a = bytes_data.find(b'\xff\xd8')
            b = bytes_data.find(b'\xff\xd9')
            if a != -1 and b != -1:
                jpg = bytes_data[a:b+2]
                bytes_data = bytes_data[b+2:]
                img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                self.frame = cv2.resize(img,(RESIZE_WIDTH,RESIZE_HEIGHT))

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True

vs = VideoStream(URL)
sleep(2)  # allow camera to start

# ==============================
# ALERT FUNCTION
# ==============================
def alert_buzzer_led(beeps=2, beep_time=0.4, pause_time=0.2):
    for _ in range(beeps):
        led.on()
        buzzer.on()
        sleep(beep_time)
        led.off()
        buzzer.off()
        sleep(pause_time)

# ==============================
# MAIN LOOP
# ==============================
while True:
    frame = vs.read()
    if frame is None:
        continue

    frame_count +=1
    roi = frame[ROI_TOP:RESIZE_HEIGHT,:]

    # IMAGE PROCESSING
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray,GAUSSIAN_BLUR,0)
    edges = cv2.Canny(blur,CANNY_THRESH_LOW,CANNY_THRESH_HIGH)
    lap = cv2.Laplacian(blur,cv2.CV_64F)
    lap = cv2.convertScaleAbs(lap)
    combined = cv2.bitwise_or(edges,lap)

    # CONTOUR DETECTION
    contours,_ = cv2.findContours(combined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    anomaly_detected = False
    current_anomalies = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < CONTOUR_AREA_MIN:
            continue

        x,y,w,h = cv2.boundingRect(cnt)
        aspect_ratio = w/float(h)

        if not (ASPECT_RATIO_MIN < aspect_ratio < ASPECT_RATIO_MAX):
            continue

        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        solidity = float(area)/hull_area if hull_area > 0 else 0
        extent = float(area)/(w*h)

        # Average intensity check (darker regions)
        mask = np.zeros(gray.shape,np.uint8)
        cv2.drawContours(mask,[cnt],-1,255,-1)
        mean_val = cv2.mean(gray,mask=mask)[0]

        if solidity < SOLIDITY_MIN or extent < EXTENT_MIN or mean_val > DARKNESS_THRESH:
            continue
p1
        # Only central part of ROI
        if RESIZE_WIDTH*0.1 < x < RESIZE_WIDTH*0.9:
            cv2.rectangle(frame,(x,y+ROI_TOP),(x+w,y+h+ROI_TOP),(0,0,255),2)
            anomaly_detected=True
            current_anomalies.append((x,y+ROI_TOP,w,h))

    # HISTORY & ALERT
    anomaly_history.append(anomaly_detected)
    if len(anomaly_history) > DETECTION_FRAMES:
        anomaly_history.pop(0)

    if anomaly_history.count(True) >= DETECTION_FRAMES:
        cv2.putText(frame,"POTHOLE DETECTED",(20,40),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),3)
        alert_buzzer_led()
        for x,y,w,h in current_anomalies:
            print(f"Pothole at x={x}, y={y}, w={w}, h={h}")
            with open(CSV_FILE,"a",newline="") as f:
                writer = csv.writer(f)
                writer.writerow([frame_count,x,y,w,h])
        if SAVE_FRAMES:
            cv2.imwrite(os.path.join(SAVE_DIR,f"frame_{frame_count:04d}.jpg"),frame)
    else:
        led.off()
        buzzer.off()

    cv2.imshow("Road Anomaly Detection",frame)
    if cv2.waitKey(1)&0xFF==27:
        break

# CLEANUP
vs.stop()
cv2.destroyAllWindows()
led.off()
buzzer.off()
