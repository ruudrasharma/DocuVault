#!/usr/bin/env python3
"""
scripts/fl_client.py
====================
Standalone Flower (flwr) client node for an institution server.
Connects to central DocuVault FL server and trains locally on local document shard.
"""

import os
import sys
import glob
import logging
import torch
from torch.utils.data import DataLoader, TensorDataset
import flwr as fl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.federated_learning import DocumentAutoencoder, AutoencoderFlowerClient, preprocess_image_tensor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    server_addr = os.environ.get('FL_SERVER', '127.0.0.1:8080')
    data_dir = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data'))

    logger.info(f"Connecting Flower FL Client to server at {server_addr} using data from {data_dir}...")

    file_paths = glob.glob(os.path.join(data_dir, '*.*'))
    tensors = []
    for fp in file_paths:
        t = preprocess_image_tensor(fp)
        if t is not None:
            tensors.append(t)

    if not tensors:
        logger.info("No documents found in data_dir. Generating synthetic client tensors...")
        for _ in range(15):
            tensors.append(torch.rand(1, 1, 64, 64) * 0.8 + 0.1)

    all_data = torch.cat(tensors, dim=0)
    dataset = TensorDataset(all_data)
    trainloader = DataLoader(dataset, batch_size=4, shuffle=True)

    model = DocumentAutoencoder()
    client = AutoencoderFlowerClient(model, trainloader)

    fl.client.start_numpy_client(server_address=server_addr, client=client)

if __name__ == '__main__':
    main()
