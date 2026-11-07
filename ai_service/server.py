import os
import sys
from pathlib import Path

# Safe UTF-8 output handling for cross-platform terminals (Windows/Linux)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import grpc
from concurrent import futures
import time
import io
import torch
import torchvision
from torchvision import models, transforms
from PIL import Image

# Import the generated gRPC code (Now in the same folder!)
import plant_pb2
import plant_pb2_grpc
from disease_info import DISEASE_INFO

# --- CONFIGURATION ---
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = BASE_DIR / "plant_disease_resnet18.pth"
MODEL_PATH = Path(os.environ.get("MODEL_PATH", str(DEFAULT_MODEL_PATH)))

# class names b mn A l Z hit model kaybdl tritb b alphabet
CLASS_NAMES = [
    'Apple___Apple_scab', 'Apple___Black_rot', 'Apple___Cedar_apple_rust', 'Apple___healthy', 
    'Blueberry___healthy', 'Cherry_(including_sour)___Powdery_mildew', 
    'Cherry_(including_sour)___healthy', 'Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot', 
    'Corn_(maize)___Common_rust_', 'Corn_(maize)___Northern_Leaf_Blight', 'Corn_(maize)___healthy', 
    'Grape___Black_rot', 'Grape___Esca_(Black_Measles)', 'Grape___Leaf_blight_(Isariopsis_Leaf_Spot)', 
    'Grape___healthy', 'Orange___Haunglongbing_(Citrus_greening)', 'Peach___Bacterial_spot', 
    'Peach___healthy', 'Pepper,_bell___Bacterial_spot', 'Pepper,_bell___healthy', 
    'Potato___Early_blight', 'Potato___Late_blight', 'Potato___healthy', 'Raspberry___healthy', 
    'Soybean___healthy', 'Squash___Powdery_mildew', 'Strawberry___Leaf_scorch', 
    'Strawberry___healthy', 'Tomato___Bacterial_spot', 'Tomato___Early_blight', 
    'Tomato___Late_blight', 'Tomato___Leaf_Mold', 'Tomato___Septoria_leaf_spot', 
    'Tomato___Spider_mites Two-spotted_spider_mite', 'Tomato___Target_Spot', 
    'Tomato___Tomato_Yellow_Leaf_Curl_Virus', 'Tomato___Tomato_mosaic_virus', 'Tomato___healthy'
]

def load_model():
    print(f"🚀 Loading model on {DEVICE}...")
    # hna kangado skeleton or body d model
    model = models.resnet18(weights=None)
    # hna db had resnet recognize bzaf d lhwayj(dogs,cats....) kandiro hadi bash redoh kaydiha ha f dok 38 diseases dialna
    model.fc = torch.nn.Linear(model.fc.in_features, len(CLASS_NAMES))
    
    # hna katlo7 dak model li gadina f dak lbody b7ala glti katlo7 brain 
    try:
        model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
        print("✅ Model loaded successfully!")
    except FileNotFoundError:
        print(f"❌ ERROR: Could not find {MODEL_PATH}. Make sure it is in the ai_service folder!")
        exit(1)
        
    # hadi katbdl model mn learning l testing
    return model.to(DEVICE).eval()

# Load the model once when script starts
model = load_model()

# hna ha katgad image kima model kan kayshufha fash traina
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

class PlantService(plant_pb2_grpc.PlantServiceServicer):
    def PredictDisease(self, request, context):
        try:
            print("Received request... Processing image.")
            # django kaysift tswira bytes walakin image library kaytsna file
            # haka lash bytes.IO kadir l3ba dial trd had bytes b7ala physical file f disk
            image = Image.open(io.BytesIO(request.image)).convert("RGB")
            
            # hna ai models kaytsnaw batches of images(32 ula ma3rt) walakin 7na endna whda 
            # dik unsqueeze hya l7el bash redoh 9abl image whda
            input_tensor = transform(image).unsqueeze(0).to(DEVICE)
            
            # hna we tell pytorch rah 7na makant3lmosh db mais kantestiw matcalculi walo
            # dik softmax katbdl output d model l probabilites(70%,20%,10%)=100%
            with torch.no_grad():
                output = model(input_tensor)
                probabilities = torch.nn.functional.softmax(output[0], dim=0)
            
            # hna kanjbdo akbar probability ou index dialha bash nsifto proba ou index il9a classname
            # ou nsiftohom l django
            confidence, index = torch.max(probabilities, 0)
            
            prediction_text = CLASS_NAMES[index.item()]
            confidence_score = confidence.item()
            
            # Fetch disease info
            disease_info = DISEASE_INFO.get(prediction_text, {'type': 'Unknown', 'treatment': 'No recommendation available.'})
            disease_type = disease_info['type']
            treatment = disease_info['treatment']
            
            print(f"Prediction: {prediction_text} ({confidence_score:.2f}), Type: {disease_type}")

            return plant_pb2.PlantResponse(
                prediction=prediction_text, 
                confidence=confidence_score,
                disease_type=disease_type,
                treatment=treatment
            )
        except Exception as e:
            print(f"❌ Error processing request: {e}")
            return plant_pb2.PlantResponse(prediction="Error", confidence=0.0, disease_type="Unknown", treatment="None")

    def PredictWaterNeed(self, request, context):
        print(f"Received Water Prediction Request: Temp={request.avg_temperature}, Hum={request.avg_humidity}, Soil={request.avg_soil_moisture}")
        
        # Simple heuristic ML simulation for predicting water needs in Liters per week
        # In a real scenario, this would be a loaded scikit-learn or PyTorch model
        # Base water need: 5L. High temp increases need, high humidity decreases, high moisture decreases.
        base_water = 5.0
        temp_factor = request.avg_temperature * 0.2
        humidity_factor = request.avg_humidity * 0.05
        moisture_factor = request.avg_soil_moisture * 0.1
        
        predicted_water = base_water + temp_factor - humidity_factor - moisture_factor
        
        # Ensure it doesn't drop below 0
        predicted_water = max(0.0, round(predicted_water, 2))
        
        print(f"Predicted water need: {predicted_water} L")
        return plant_pb2.WaterResponse(predicted_water_liters=predicted_water)

def serve():
    port = int(os.environ.get("PORT", 50051))
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
        ]
    )
    plant_pb2_grpc.add_PlantServiceServicer_to_server(PlantService(), server)
    
    # Listen on all IPv4 and IPv6 network interfaces
    bind_address = f"0.0.0.0:{port}"
    server.add_insecure_port(bind_address)
    server.start()
    print(f"🚀 gRPC Server successfully started and listening on {bind_address} (PORT={port})...")
    print("👉 Ready to accept incoming plant analysis requests.")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        print("\nStopping gRPC Server...")
        server.stop(0)

if __name__ == "__main__":
    serve()