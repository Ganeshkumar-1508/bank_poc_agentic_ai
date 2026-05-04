import os
import sys

# Add parent directory to path for imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath('bank_app/views.py'))))
print(f"BASE_DIR: {BASE_DIR}")

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Model paths
INDIAN_MODEL_PATH = os.path.join(BASE_DIR, 'models', 'credit_risk', 'indian', 'loan_model.pkl')
INDIAN_SCALER_PATH = os.path.join(BASE_DIR, 'models', 'credit_risk', 'indian', 'scaler.pkl')
US_MODEL_PATH = os.path.join(BASE_DIR, 'models', 'credit_risk', 'xgb_model.pkl')

print(f"INDIAN_MODEL_PATH: {INDIAN_MODEL_PATH}")
print(f"INDIAN_SCALER_PATH: {INDIAN_SCALER_PATH}")
print(f"US_MODEL_PATH: {US_MODEL_PATH}")

# Check if paths exist
print(f"\nINDIAN_MODEL_PATH exists: {os.path.exists(INDIAN_MODEL_PATH)}")
print(f"INDIAN_SCALER_PATH exists: {os.path.exists(INDIAN_SCALER_PATH)}")
print(f"US_MODEL_PATH exists: {os.path.exists(US_MODEL_PATH)}")

# Check if the models directory exists
models_dir = os.path.join(BASE_DIR, 'models')
print(f"\nmodels directory exists: {os.path.exists(models_dir)}")
if os.path.exists(models_dir):
    print(f"Contents of models directory: {os.listdir(models_dir)}")

# Check the credit_risk directory
credit_risk_dir = os.path.join(models_dir, 'credit_risk')
print(f"\ncredit_risk directory exists: {os.path.exists(credit_risk_dir)}")
if os.path.exists(credit_risk_dir):
    print(f"Contents of credit_risk directory: {os.listdir(credit_risk_dir)}")

# Check the indian directory
indian_dir = os.path.join(credit_risk_dir, 'indian')
print(f"\nindian directory exists: {os.path.exists(indian_dir)}")
if os.path.exists(indian_dir):
    print(f"Contents of indian directory: {os.listdir(indian_dir)}")
