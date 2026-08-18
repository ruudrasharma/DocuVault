
import os
import glob
import logging
from typing import Dict, List, Tuple
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import cv2
from pdf2image import convert_from_path
import flwr as fl

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DocumentAutoencoder(nn.Module):
    """
    Convolutional Autoencoder for document structure anomaly detection.
    Trains unsupervised on genuine document images to learn normal pixel reconstruction.
    Anomalous or tampered regions exhibit high reconstruction loss.
    """
    def __init__(self):
        super(DocumentAutoencoder, self).__init__()
        # Input: (B, 1, 64, 64)
        self.encoder = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=3, stride=1, padding=1),  # -> (B, 16, 64, 64)
            nn.ReLU(True),
            nn.MaxPool2d(2, 2),                                    # -> (B, 16, 32, 32)
            nn.Conv2d(16, 8, kernel_size=3, stride=1, padding=1),  # -> (B, 8, 32, 32)
            nn.ReLU(True),
            nn.MaxPool2d(2, 2)                                     # -> (B, 8, 16, 16)
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(8, 16, kernel_size=2, stride=2),   # -> (B, 16, 32, 32)
            nn.ReLU(True),
            nn.ConvTranspose2d(16, 1, kernel_size=2, stride=2),   # -> (B, 1, 64, 64)
            nn.Sigmoid()
        )

    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded


def preprocess_image_tensor(file_path: str) -> torch.Tensor | None:
    """Preprocesses a single PDF/image file into a normalized (1, 1, 64, 64) PyTorch Tensor."""
    try:
        if not file_path or not os.path.exists(file_path):
            return None
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path)
            if not images:
                return None
            img = np.array(images[0].convert('L'))
        else:
            img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return None
        img_resized = cv2.resize(img, (64, 64))
        img_norm = img_resized.astype(np.float32) / 255.0
        return torch.tensor(img_norm).unsqueeze(0).unsqueeze(0)  # (1, 1, 64, 64)
    except Exception as e:
        logger.debug(f"Failed to convert {file_path} to tensor: {e}")
        return None


def train_autoencoder(model: nn.Module, trainloader: DataLoader, epochs: int = 3, lr: float = 0.001) -> float:
    """Trains the DocumentAutoencoder using MSE loss."""
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    model.train()
    total_loss = 0.0
    steps = 0
    for _ in range(epochs):
        for data in trainloader:
            inputs = data[0] if isinstance(data, (tuple, list)) else data
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, inputs)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            steps += 1
    return total_loss / max(steps, 1)


def evaluate_image_autoencoder(model: nn.Module, file_path: str, threshold: float = 0.45) -> Tuple[bool, float]:
    """
    Evaluates a document against trained Autoencoder.
    Returns (is_anomalous, reconstruction_loss).
    """
    try:
        tensor = preprocess_image_tensor(file_path)
        if tensor is None:
            return False, 0.0
        model.eval()
        with torch.no_grad():
            reconstructed = model(tensor)
            loss = float(nn.MSELoss()(reconstructed, tensor).item())
        is_anomalous = loss > threshold
        return is_anomalous, loss
    except Exception as e:
        logger.error(f"Autoencoder evaluation failed for {file_path}: {e}")
        return False, 0.0


class AutoencoderFlowerClient(fl.client.NumPyClient):
    """Flower NumPyClient for federated Autoencoder weight updates across institution nodes."""
    def __init__(self, model: nn.Module, trainloader: DataLoader):
        self.model = model
        self.trainloader = trainloader

    def get_parameters(self, config: Dict) -> List[np.ndarray]:
        return [val.cpu().numpy() for _, val in self.model.state_dict().items()]

    def fit(self, parameters: List[np.ndarray], config: Dict) -> Tuple[List[np.ndarray], int, Dict]:
        state_dict = {k: torch.tensor(v) for k, v in zip(self.model.state_dict().keys(), parameters)}
        self.model.load_state_dict(state_dict)
        loss = train_autoencoder(self.model, self.trainloader, epochs=2)
        return self.get_parameters({}), len(self.trainloader.dataset), {"loss": float(loss)}

    def evaluate(self, parameters: List[np.ndarray], config: Dict) -> Tuple[float, int, Dict]:
        state_dict = {k: torch.tensor(v) for k, v in zip(self.model.state_dict().keys(), parameters)}
        self.model.load_state_dict(state_dict)
        self.model.eval()
        criterion = nn.MSELoss()
        total_loss = 0.0
        total_samples = 0
        with torch.no_grad():
            for data in self.trainloader:
                inputs = data[0] if isinstance(data, (tuple, list)) else data
                outputs = self.model(inputs)
                loss = criterion(outputs, inputs)
                total_loss += loss.item() * len(inputs)
                total_samples += len(inputs)
        avg_loss = total_loss / max(total_samples, 1)
        return float(avg_loss), total_samples, {"loss": float(avg_loss)}


def simulate_federated_learning(data_dir: str = None, num_clients: int = 3, mock_mode: bool = True) -> DocumentAutoencoder:
    """
    Simulates multi-institution Federated Learning (FedAvg) on local document corpus.
    Shards document dataset into num_clients institutions and performs FL training rounds.
    """
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

    file_paths = glob.glob(os.path.join(data_dir, '*.*'))
    tensors = []
    for fp in file_paths:
        t = preprocess_image_tensor(fp)
        if t is not None:
            tensors.append(t)

    if not tensors:
        # Generate baseline synthetic document tensors if no real PDFs present
        logger.info("No documents found in data_dir. Using baseline synthetic document tensors for FL.")
        for _ in range(30):
            syn = torch.rand(1, 1, 64, 64) * 0.8 + 0.1
            tensors.append(syn)

    all_data = torch.cat(tensors, dim=0)  # (N, 1, 64, 64)
    shard_size = max(len(all_data) // num_clients, 1)
    
    clients = []
    global_model = DocumentAutoencoder()

    for i in range(num_clients):
        start_idx = i * shard_size
        end_idx = (i + 1) * shard_size if i < num_clients - 1 else len(all_data)
        client_data = all_data[start_idx:end_idx]
        dataset = TensorDataset(client_data)
        loader = DataLoader(dataset, batch_size=4, shuffle=True)
        client_model = DocumentAutoencoder()
        client_model.load_state_dict(global_model.state_dict())
        clients.append((client_model, loader))

    logger.info(f"Starting Federated Learning simulation across {num_clients} institution nodes ({len(all_data)} samples)...")
    
    # Simulate 3 rounds of FedAvg
    for round_idx in range(1, 4):
        client_weights = []
        round_losses = []
        for idx, (c_model, c_loader) in enumerate(clients):
            c_model.load_state_dict(global_model.state_dict())
            loss = train_autoencoder(c_model, c_loader, epochs=2)
            round_losses.append(loss)
            client_weights.append([val.cpu() for val in c_model.state_dict().values()])

        # FedAvg: Average parameters across clients
        avg_dict = {}
        for key_idx, key in enumerate(global_model.state_dict().keys()):
            avg_tensor = torch.stack([weights[key_idx] for weights in client_weights], dim=0).mean(dim=0)
            avg_dict[key] = avg_tensor

        global_model.load_state_dict(avg_dict)
    avg_round_loss = sum(round_losses) / len(round_losses)
    logger.info(f"FL Round 3/3 Complete — Average Reconstruction Loss: {avg_round_loss:.4f}")

    return global_model


def export_global_model_to_anomaly_format(global_model: DocumentAutoencoder, output_path: str = "app/models/anomaly_models.pkl") -> bool:
    """
    Exports federated global model into anomaly_models.pkl bundle for live inference.
    Preserves text vectorizer, text model, and image model while hot-swapping the Autoencoder.
    """
    import joblib
    from app.ml_anomaly import load_models

    current_models = load_models()
    updated_models = dict(current_models)
    updated_models['autoencoder'] = global_model

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    temp_file = f"{output_path}.fl_tmp"

    try:
        with open(temp_file, 'wb') as f:
            joblib.dump(updated_models, f)
        os.replace(temp_file, output_path)
        logger.info(f"Federated model exported successfully to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to export federated model: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False


# ── CLI entry point ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    import signal
    import time as _time

    parser = argparse.ArgumentParser(description='DocuVault Federated Learning')
    parser.add_argument('--server', action='store_true',
                        help='Start a persistent Flower FL aggregation server (listens for institution clients)')
    parser.add_argument('--simulate', action='store_true',
                        help='Run a local FedAvg simulation across synthetic institution shards')
    parser.add_argument('--port', type=int, default=8080,
                        help='Port for the FL server (default: 8080)')
    parser.add_argument('--rounds', type=int, default=3,
                        help='Number of FL rounds (default: 3)')
    parser.add_argument('--min-clients', type=int, default=1,
                        help='Minimum FL clients required per round (default: 1)')
    args = parser.parse_args()

    if args.server:
        logger.info(f"Starting DocuVault Federated Learning server on 0.0.0.0:{args.port} ...")
        strategy = fl.server.strategy.FedAvg(
            fraction_fit=1.0,
            fraction_evaluate=1.0,
            min_fit_clients=args.min_clients,
            min_evaluate_clients=args.min_clients,
            min_available_clients=args.min_clients,
        )

        def _on_shutdown(sig, frame):
            logger.info("FL server shutting down gracefully.")
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _on_shutdown)
        signal.signal(signal.SIGINT, _on_shutdown)

        fl.server.start_server(
            server_address=f"0.0.0.0:{args.port}",
            config=fl.server.ServerConfig(num_rounds=args.rounds),
            strategy=strategy,
        )

    elif args.simulate:
        logger.info("Running local FL simulation...")
        global_model = simulate_federated_learning()
        success = export_global_model_to_anomaly_format(global_model)
        logger.info(f"Simulation complete. Model exported: {success}")

    else:
        parser.print_help()
