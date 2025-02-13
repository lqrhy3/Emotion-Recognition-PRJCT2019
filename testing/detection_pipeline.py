import argparse
import cv2
import os

import sys
module_path = os.path.abspath(os.getcwd() + '\\..')
if module_path not in sys.path:
    sys.path.append(module_path)
import torch
import numpy as np
from utils.utils import xywh2xyxy, from_yolo_target, bbox_resize
from utils.show_targets import draw_rectangles
from utils.transforms import ImageToTensor
import time


def run_eval():
    model = torch.load(os.path.join(PATH_TO_MODEL, 'model.pt'), map_location='cpu')
    load = torch.load(os.path.join(PATH_TO_MODEL, 'checkpoint.pt'), map_location='cpu')
    model.load_state_dict(load['model_state_dict'])
    # model = torch.jit.load(os.path.join(PATH_TO_MODEL, 'model_quantized.pt'))
    model.to(DEVICE).eval()

    cap = cv2.VideoCapture(0)
    while cap.isOpened():  # Capturing video
        ret, image = cap.read()
        orig_shape = image.shape[:2]
        start = time.time()

        with torch.no_grad():
            # Image preprocessing for format and shape required by model
            detection_image = cv2.resize(image, DETECTION_SIZE)
            detection_image = ImageToTensor()(detection_image).to(DEVICE)
            detection_image = detection_image.unsqueeze(0)
            output = model(detection_image)  # Prediction

            listed_output = from_yolo_target(output[:, :10, :, :], detection_image.size(2), grid_size=GRID_SIZE, num_bboxes=NUM_BBOXES)  # Converting from tensor format to list
            pred_output = listed_output[:, np.argmax(listed_output[:, :, 4]).item(), :]  # Selecting most confident cell
            if pred_output[:, 4].item() > DETECTION_THRESHOLD:
                draw_rectangles(image,
                                np.expand_dims(np.array(bbox_resize(xywh2xyxy(pred_output[:, :4]), DETECTION_SIZE, orig_shape[::-1])), axis=0),
                                '', #[str(pred_output[:, 4].item())[:5]],
                                name='detection pipeline')  # Painting bbox
            else:
                cv2.imshow('detection pipeline', image)
        fps = 1. / (time.time() - start)
        print(fps)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script to evaluate detection model',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--path_to_model', type=str, default='log/detection/20.03.31_11-56', help='path to model')
    parser.add_argument('--grid_size', type=int, default=9, help='grid size')
    parser.add_argument('--num_bboxes', type=int, default=2, help='number of bboxes')
    parser.add_argument('--image_size', type=int, default=288, help='image size')
    parser.add_argument('--detection_threshold', type=float, default=0.3, help='detection threshold')
    parser.add_argument('--device', type=str, default='cpu',
                        choices=['cpu', 'cuda:0'])
    opt = parser.parse_args()
    # Initialising detection model
    PATH_TO_MODEL = os.path.join('..', opt.path_to_model)
    GRID_SIZE = opt.grid_size
    NUM_BBOXES = opt.num_bboxes
    DETECTION_SIZE = (opt.image_size, opt.image_size)
    DETECTION_THRESHOLD = opt.detection_threshold
    DEVICE = opt.device

    run_eval()
