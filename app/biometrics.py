
import cv2
import numpy as np

def match_face(certificate_image_path, user_image_path, threshold=0.8):
    try:
        cert_img = cv2.imread(certificate_image_path, cv2.IMREAD_GRAYSCALE)
        user_img = cv2.imread(user_image_path, cv2.IMREAD_GRAYSCALE)
        
        if cert_img is None or user_img is None:
            raise ValueError("One or both images could not be loaded.")
        
        cert_img = cv2.resize(cert_img, (300, 300))
        user_img = cv2.resize(user_img, (300, 300))
        
        res = cv2.matchTemplate(cert_img, user_img, cv2.TM_CCOEFF_NORMED)
        max_confidence = np.max(res)
        
        return max_confidence > threshold
    except Exception as e:
        raise RuntimeError(f"Biometric matching failed: {str(e)}")
