
import flwr as fl
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from torchvision.transforms import ToTensor
import numpy as np
from typing import Dict, List, Tuple

class Net(nn.Module):
    def __init__(self, num_classes=10):
        super(Net, self).__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, num_classes)

    def forward(self, x):
        x = self.pool(torch.relu(self.conv1(x)))
        x = self.pool(torch.relu(self.conv2(x)))
        x = torch.flatten(x, 1)
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = self.fc3(x)
        return x

def train(net: nn.Module, trainloader: DataLoader, epochs: int = 2) -> None:
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(net.parameters(), lr=0.01)
    net.train()
    for _ in range(epochs):
        for data in trainloader:
            inputs, labels = data
            optimizer.zero_grad()
            outputs = net(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

class FlowerClient(fl.client.NumPyClient):
    def __init__(self, net: nn.Module, trainloader: DataLoader):
        self.net = net
        self.trainloader = trainloader

    def get_parameters(self, config: Dict) -> List[np.ndarray]:
        return [val.cpu().numpy() for _, val in self.net.state_dict().items()]

    def fit(self, parameters: List[np.ndarray], config: Dict) -> Tuple[List[np.ndarray], int, Dict]:
        state_dict = {k: torch.tensor(v) for k, v in zip(self.net.state_dict().keys(), parameters)}
        self.net.load_state_dict(state_dict)
        train(self.net, self.trainloader)
        return self.get_parameters({}), len(self.trainloader.dataset), {}

def simulate_federated_learning(mock_mode: bool = True):
    dummy_images = torch.randn(100, 3, 32, 32)
    dummy_labels = torch.randint(0, 10, (100,))
    dataset = TensorDataset(dummy_images, dummy_labels)
    trainloader = DataLoader(dataset, batch_size=32, shuffle=True)
    
    net = Net()
    client = FlowerClient(net, trainloader)
    
    if mock_mode:
        print("Mock federated learning: Training locally...")
        train(net, trainloader)
        print("Mock aggregation complete.")
    else:
        fl.client.start_numpy_client(server_address="localhost:8080", client=client)
