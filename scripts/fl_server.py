#!/usr/bin/env python3
"""
scripts/fl_server.py
====================
Standalone Flower (flwr) gRPC Federated Learning Aggregation Server.
Runs FedAvg across connecting institution client nodes.
"""

import os
import sys
import logging
import flwr as fl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.federated_learning import DocumentAutoencoder

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    port = int(os.environ.get('FL_PORT', '8080'))
    rounds = int(os.environ.get('FL_ROUNDS', '3'))
    
    logger.info(f"Starting DocuVault Federated Learning Server on 0.0.0.0:{port} ({rounds} rounds)...")

    strategy = fl.server.strategy.FedAvg(
        fraction_fit=1.0,
        fraction_evaluate=1.0,
        min_fit_clients=2,
        min_evaluate_clients=2,
        min_available_clients=2,
    )

    fl.server.start_server(
        server_address=f"0.0.0.0:{port}",
        config=fl.server.ServerConfig(num_rounds=rounds),
        strategy=strategy,
    )

if __name__ == '__main__':
    main()
